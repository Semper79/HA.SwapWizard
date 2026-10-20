from pathlib import Path

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from sample_config import AUTOMATIONS, SCRIPTS

DOMAIN = "swap_wizard"


async def _setup(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _phone(hass, name, app_device_id, webhook):
    """Crea un telefono finto: config entry mobile_app + dispositivo + entita'."""
    entry = MockConfigEntry(
        domain="mobile_app",
        data={"device_name": name, "device_id": app_device_id, "webhook_id": webhook},
        title=name,
    )
    entry.add_to_hass(hass)
    dev = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("mobile_app", app_device_id)},
        name=name,
        manufacturer="Google",
        model="Pixel",
    )
    reg = er.async_get(hass)
    slug = name.lower().replace(" ", "_")
    for key, dom, dc in (("battery_level", "sensor", "battery"), ("charging", "binary_sensor", "battery_charging")):
        reg.async_get_or_create(
            dom,
            "mobile_app",
            f"{app_device_id}_{key}",
            suggested_object_id=f"{slug}_{key}",
            device_id=dev.id,
            config_entry=entry,
            original_device_class=dc,
        )
    return entry, dev


async def test_panel_and_commands_registered(hass, hass_ws_client):
    await _setup(hass)
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "swap_wizard/devices"})
    res = await client.receive_json()
    assert res["success"], res
    await client.send_json({"id": 2, "type": "swap_wizard/history"})
    assert (await client.receive_json())["result"] == []
    assert "swap-wizard" in hass.data["frontend_panels"]


async def test_propose_phone_swap_pairs_entities_and_service(hass, hass_ws_client):
    await _setup(hass)
    _, old = _phone(hass, "Pixel Vecchio", "APPOLD", "wh_old")
    _, new = _phone(hass, "Pixel Nuovo", "APPNEW", "wh_new")
    hass.services.async_register("notify", "mobile_app_pixel_vecchio", lambda c: None)
    hass.services.async_register("notify", "mobile_app_pixel_nuovo", lambda c: None)

    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "swap_wizard/devices"})
    devices = (await client.receive_json())["result"]
    phones = [d for d in devices if d["mobile"]]
    assert {d["notify"] for d in phones} == {
        "notify.mobile_app_pixel_vecchio",
        "notify.mobile_app_pixel_nuovo",
    }

    await client.send_json(
        {"id": 2, "type": "swap_wizard/propose_device", "old_device_id": old.id, "new_device_id": new.id}
    )
    res = (await client.receive_json())["result"]
    got = {(m["kind"], m["old"], m["new"]) for m in res["mappings"]}
    assert ("device", old.id, new.id) in got
    assert ("service", "notify.mobile_app_pixel_vecchio", "notify.mobile_app_pixel_nuovo") in got
    assert ("entity", "sensor.pixel_vecchio_battery_level", "sensor.pixel_nuovo_battery_level") in got
    assert ("entity", "binary_sensor.pixel_vecchio_charging", "binary_sensor.pixel_nuovo_charging") in got
    assert res["unpaired_old"] == []


async def test_full_flow_preview_apply_rollback(hass, hass_ws_client):
    await _setup(hass)
    _, old = _phone(hass, "Pixel Vecchio", "APPOLD", "wh_old")
    _, new = _phone(hass, "Pixel Nuovo", "APPNEW", "wh_new")
    hass.services.async_register("notify", "mobile_app_pixel_vecchio", lambda c: None)
    hass.services.async_register("notify", "mobile_app_pixel_nuovo", lambda c: None)

    cfg = Path(hass.config.path())
    text = AUTOMATIONS.replace("0123456789abcdef0123456789abcdef", old.id)
    (cfg / "automations.yaml").write_text(text)
    (cfg / "scripts.yaml").write_text(SCRIPTS)

    client = await hass_ws_client(hass)
    await client.send_json(
        {"id": 1, "type": "swap_wizard/propose_device", "old_device_id": old.id, "new_device_id": new.id}
    )
    proposal = (await client.receive_json())["result"]
    mappings = [{k: m[k] for k in ("kind", "old", "new", "note")} for m in proposal["mappings"]]

    await client.send_json({"id": 2, "type": "swap_wizard/preview", "mappings": mappings})
    preview = (await client.receive_json())["result"]
    assert [f["path"] for f in preview["files"]] == ["automations.yaml", "scripts.yaml"]
    assert preview["totals"]["lines"] >= 7

    # token sbagliato -> rifiutato
    await client.send_json(
        {"id": 3, "type": "swap_wizard/apply", "mappings": mappings, "token": "x" * 24,
         "files": ["automations.yaml"], "backup": True}
    )
    bad = await client.receive_json()
    assert not bad["success"] and bad["error"]["code"] == "swap_error"

    await client.send_json(
        {"id": 4, "type": "swap_wizard/apply", "mappings": mappings, "token": preview["token"],
         "files": ["automations.yaml", "scripts.yaml"], "backup": True, "title": "Test"}
    )
    applied = await client.receive_json()
    assert applied["success"], applied
    result = applied["result"]
    assert result["ok"], result
    after = (cfg / "automations.yaml").read_text()
    assert "pixel_vecchio_battery_level" not in after
    assert new.id in after and old.id not in after
    assert "# commento da conservare" in after
    assert (cfg / "swap_wizard" / "backups" / result["operation"] / "automations.yaml").read_text() == text

    await client.send_json({"id": 5, "type": "swap_wizard/history"})
    hist = (await client.receive_json())["result"]
    assert hist[0]["id"] == result["operation"] and hist[0]["status"] == "applied"

    await client.send_json({"id": 6, "type": "swap_wizard/operation", "operation_id": result["operation"]})
    detail = (await client.receive_json())["result"]
    assert detail["rollback_preview"]["conflicts"] == []

    await client.send_json({"id": 7, "type": "swap_wizard/rollback", "operation_id": result["operation"]})
    rb = (await client.receive_json())["result"]
    assert rb["ok"], rb
    assert (cfg / "automations.yaml").read_text() == text
    assert (cfg / "scripts.yaml").read_text() == SCRIPTS


async def test_entity_swap_without_backup(hass, hass_ws_client):
    await _setup(hass)
    cfg = Path(hass.config.path())
    (cfg / "automations.yaml").write_text(AUTOMATIONS)
    client = await hass_ws_client(hass)
    await client.send_json(
        {"id": 1, "type": "swap_wizard/propose_entity", "old": "sensor.lavatrice_stato", "new": "sensor.lavatrice_nuova"}
    )
    prop = (await client.receive_json())["result"]
    mappings = [{k: m[k] for k in ("kind", "old", "new", "note")} for m in prop["mappings"]]
    await client.send_json({"id": 2, "type": "swap_wizard/preview", "mappings": mappings})
    pv = (await client.receive_json())["result"]
    await client.send_json(
        {"id": 3, "type": "swap_wizard/apply", "mappings": mappings, "token": pv["token"],
         "files": ["automations.yaml"], "backup": False}
    )
    res = (await client.receive_json())["result"]
    assert res["ok"] and not (cfg / "swap_wizard" / "backups").exists()
    await client.send_json({"id": 4, "type": "swap_wizard/rollback", "operation_id": res["operation"]})
    assert (await client.receive_json())["result"]["ok"]
    assert (cfg / "automations.yaml").read_text() == AUTOMATIONS


async def test_non_admin_is_refused(hass, hass_ws_client, hass_read_only_access_token):
    await _setup(hass)
    client = await hass_ws_client(hass, hass_read_only_access_token)
    await client.send_json({"id": 1, "type": "swap_wizard/history"})
    res = await client.receive_json()
    assert not res["success"] and res["error"]["code"] == "unauthorized"


async def test_check_config_runs_for_real_and_is_reported(hass, hass_ws_client):
    await _setup(hass)
    reloads = []

    async def _reload(call):
        reloads.append(call.service)

    hass.services.async_register("automation", "reload", _reload)
    cfg = Path(hass.config.path())
    (cfg / "automations.yaml").write_text(AUTOMATIONS)
    client = await hass_ws_client(hass)
    mappings = [{"kind": "entity", "old": "sensor.lavatrice_stato", "new": "sensor.lavatrice_nuova", "note": ""}]
    await client.send_json({"id": 1, "type": "swap_wizard/preview", "mappings": mappings})
    pv = (await client.receive_json())["result"]
    await client.send_json(
        {"id": 2, "type": "swap_wizard/apply", "mappings": mappings, "token": pv["token"],
         "files": ["automations.yaml"], "backup": True}
    )
    res = (await client.receive_json())["result"]
    assert res["ok"] and res["check_available"] is True, res
    assert res["reload"]["done"] == ["automation.reload"] and reloads == ["reload"], res


async def test_new_config_error_triggers_automatic_rollback(hass, hass_ws_client, monkeypatch):
    from custom_components.swap_wizard.manager import SwapManager

    await _setup(hass)
    cfg = Path(hass.config.path())
    (cfg / "automations.yaml").write_text(AUTOMATIONS)
    answers = iter([(True, None), (True, "Invalid config for [automation]: finto")])

    async def fake_check(self):
        return next(answers)

    monkeypatch.setattr(SwapManager, "_check_config", fake_check)
    client = await hass_ws_client(hass)
    mappings = [{"kind": "entity", "old": "sensor.lavatrice_stato", "new": "sensor.lavatrice_nuova", "note": ""}]
    await client.send_json({"id": 1, "type": "swap_wizard/preview", "mappings": mappings})
    pv = (await client.receive_json())["result"]
    await client.send_json(
        {"id": 2, "type": "swap_wizard/apply", "mappings": mappings, "token": pv["token"],
         "files": ["automations.yaml"], "backup": False}
    )
    res = (await client.receive_json())["result"]
    assert res["ok"] is False and res["auto_rolled_back"] is True
    assert "finto" in res["error"]
    assert (cfg / "automations.yaml").read_text() == AUTOMATIONS
    await client.send_json({"id": 3, "type": "swap_wizard/history"})
    hist = (await client.receive_json())["result"]
    assert hist[0]["status"] == "rolled_back"


# ------------------------------------------------------------------ Node-RED
import json

from sample_config import FLOWS_COMPACT, FLOWS_PRETTY, OLD_DEV

NR_MAPPINGS = [
    {"kind": "service", "old": "notify.mobile_app_pixel_vecchio", "new": "notify.mobile_app_pixel_nuovo", "note": ""},
    {"kind": "entity", "old": "sensor.pixel_vecchio_battery_level", "new": "sensor.pixel_nuovo_battery_level", "note": ""},
    {"kind": "device", "old": OLD_DEV, "new": "fedcba9876543210fedcba9876543210", "note": ""},
]


def _flows(hass, text=FLOWS_PRETTY):
    nr = Path(hass.config.path("node-red"))
    nr.mkdir(parents=True, exist_ok=True)
    (nr / "flows.json").write_text(text)
    (nr / "flows_cred.json").write_text('{"$": "x"}')
    return nr


async def _call(client, i, payload):
    await client.send_json({"id": i, **payload})
    return await client.receive_json()


async def test_nodered_detect_preview_apply_rollback(hass, hass_ws_client):
    await _setup(hass)
    nr = _flows(hass)
    client = await hass_ws_client(hass)

    det = (await _call(client, 1, {"type": "swap_wizard/nodered_detect"}))["result"]
    found = [c for c in det["candidates"] if c["path"] == str(nr)]
    assert found and found[0]["files"] == ["flows.json"] and found[0]["allowed"] is True

    pv = (await _call(client, 2, {"type": "swap_wizard/preview", "mappings": NR_MAPPINGS,
                                  "branch": "nodered", "nodered_path": str(nr)}))["result"]
    assert [f["path"] for f in pv["files"]] == ["flows.json"] and pv["files"][0]["role"] == "nodered"
    assert any(h["label"] == "Notifiche › Notifica batteria" for h in pv["files"][0]["hits"])

    res = (await _call(client, 3, {"type": "swap_wizard/apply", "mappings": NR_MAPPINGS, "branch": "nodered",
                                   "nodered_path": str(nr), "token": pv["token"], "files": ["flows.json"],
                                   "backup": True, "title": "Cambio telefono"}))["result"]
    assert res["ok"] and res["branch"] == "nodered" and res["restart"] == {"requested": False}, res
    nodes = {n["id"]: n for n in json.loads((nr / "flows.json").read_text())}
    assert nodes["n2"]["service"] == "mobile_app_pixel_nuovo"
    assert nodes["n5"]["service"] == "mobile_app_pixel_vecchio_altro"
    backup = nr.parent / "swap_wizard" / "nodered" / "backups" / res["operation"] / "flows.json"
    assert backup.read_text() == FLOWS_PRETTY
    # le impostazioni vengono ricordate
    det2 = (await _call(client, 4, {"type": "swap_wizard/nodered_detect"}))["result"]
    assert det2["settings"]["nodered_path"] == str(nr)

    hist = (await _call(client, 5, {"type": "swap_wizard/history"}))["result"]
    assert hist[0]["branch"] == "nodered" and hist[0]["status"] == "applied"
    op = (await _call(client, 6, {"type": "swap_wizard/operation", "operation_id": res["operation"],
                                  "branch": "nodered"}))["result"]
    assert op["rollback_preview"]["conflicts"] == []

    rb = (await _call(client, 7, {"type": "swap_wizard/rollback", "operation_id": res["operation"],
                                  "branch": "nodered"}))["result"]
    assert rb["ok"] and rb["branch"] == "nodered"
    assert (nr / "flows.json").read_text() == FLOWS_PRETTY


async def test_nodered_restart_calls_addon_restart(hass, hass_ws_client):
    await _setup(hass)
    nr = _flows(hass)
    calls = []

    async def _restart(call):
        calls.append(dict(call.data))

    hass.services.async_register("hassio", "addon_restart", _restart)
    client = await hass_ws_client(hass)
    pv = (await _call(client, 1, {"type": "swap_wizard/preview", "mappings": NR_MAPPINGS,
                                  "branch": "nodered", "nodered_path": str(nr)}))["result"]
    res = (await _call(client, 2, {"type": "swap_wizard/apply", "mappings": NR_MAPPINGS, "branch": "nodered",
                                   "nodered_path": str(nr), "token": pv["token"], "files": ["flows.json"],
                                   "backup": False, "restart_nodered": True}))["result"]
    assert res["ok"] and res["restart"]["done"] is True
    assert calls == [{"addon": "a0d7b954_nodered"}]


async def test_nodered_compact_file_requires_backup(hass, hass_ws_client):
    await _setup(hass)
    big = FLOWS_COMPACT.replace('"info":""', '"info":"' + "x" * 4200 + '"', 1)
    nr = _flows(hass, big)
    client = await hass_ws_client(hass)
    pv = (await _call(client, 1, {"type": "swap_wizard/preview", "mappings": NR_MAPPINGS,
                                  "branch": "nodered", "nodered_path": str(nr)}))["result"]
    assert pv["files"][0]["line_revert_ok"] is False
    base = {"type": "swap_wizard/apply", "mappings": NR_MAPPINGS, "branch": "nodered", "nodered_path": str(nr),
            "token": pv["token"], "files": ["flows.json"]}
    refused = await _call(client, 2, {**base, "backup": False})
    assert not refused["success"] and "backup" in refused["error"]["message"].lower()
    assert (nr / "flows.json").read_text() == big
    ok = (await _call(client, 3, {**base, "backup": True}))["result"]
    assert ok["ok"]
    rb = (await _call(client, 4, {"type": "swap_wizard/rollback", "operation_id": ok["operation"],
                                  "branch": "nodered"}))["result"]
    assert rb["ok"] and (nr / "flows.json").read_text() == big


async def test_nodered_path_errors(hass, hass_ws_client, tmp_path):
    await _setup(hass)
    client = await hass_ws_client(hass)
    base = {"type": "swap_wizard/preview", "mappings": NR_MAPPINGS, "branch": "nodered"}
    for i, (path, expected) in enumerate((
        ("", "Indica la cartella"),
        ("relativo/dir", "assoluto"),
        (str(Path(hass.config.path("manca"))), "non trovata"),
        (str(tmp_path), "allowlist_external_dirs"),
    ), start=10):
        tmp_path.mkdir(exist_ok=True)
        res = await _call(client, i, {**base, "nodered_path": path})
        assert not res["success"] and expected in res["error"]["message"], (path, res)
    empty = Path(hass.config.path("node-red"))
    empty.mkdir(parents=True, exist_ok=True)
    res = await _call(client, 20, {**base, "nodered_path": str(empty)})
    assert res["result"]["no_flow_files"] is True and res["result"]["files"] == []


async def test_history_mixes_both_branches(hass, hass_ws_client):
    await _setup(hass)
    nr = _flows(hass)
    cfg = Path(hass.config.path())
    (cfg / "automations.yaml").write_text(AUTOMATIONS)
    client = await hass_ws_client(hass)
    ha_map = [{"kind": "entity", "old": "sensor.lavatrice_stato", "new": "sensor.lavatrice_nuova", "note": ""}]
    pv = (await _call(client, 1, {"type": "swap_wizard/preview", "mappings": ha_map}))["result"]
    await _call(client, 2, {"type": "swap_wizard/apply", "mappings": ha_map, "token": pv["token"],
                            "files": ["automations.yaml"], "backup": True})
    pv = (await _call(client, 3, {"type": "swap_wizard/preview", "mappings": NR_MAPPINGS,
                                  "branch": "nodered", "nodered_path": str(nr)}))["result"]
    await _call(client, 4, {"type": "swap_wizard/apply", "mappings": NR_MAPPINGS, "branch": "nodered",
                            "nodered_path": str(nr), "token": pv["token"], "files": ["flows.json"], "backup": True})
    hist = (await _call(client, 5, {"type": "swap_wizard/history"}))["result"]
    assert [h["branch"] for h in hist] == ["nodered", "ha"]
