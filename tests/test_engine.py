import pytest
from swc import engine
from swc.engine import Mapping, normalize_mappings, scan_config_dir, scan_text

from sample_config import AUTOMATIONS, NEW_DEV, OLD_DEV, PACKAGE, SCRIPTS, UNRELATED

PHONE_MAPPINGS = [
    Mapping("service", "notify.mobile_app_pixel_vecchio", "notify.mobile_app_pixel_nuovo"),
    Mapping("entity", "sensor.pixel_vecchio_battery_level", "sensor.pixel_nuovo_battery_level"),
    Mapping("device", OLD_DEV, NEW_DEV),
]


def test_replaces_only_identifiers_and_keeps_formatting():
    result = scan_text(AUTOMATIONS, PHONE_MAPPINGS)
    expected = (
        AUTOMATIONS.replace("notify.mobile_app_pixel_vecchio\n", "notify.mobile_app_pixel_nuovo\n")
        .replace("sensor.pixel_vecchio_battery_level", "sensor.pixel_nuovo_battery_level")
        .replace(OLD_DEV, NEW_DEV)
    )
    assert result.new_text == expected
    # il commento e le virgolette sono intatti
    assert "# commento da conservare" in result.new_text
    assert "'Batteria {{ states(\"sensor.pixel_nuovo_battery_level\") }}%'" in result.new_text
    # solo le righe con identificatori cambiano
    old_lines = AUTOMATIONS.splitlines()
    new_lines = result.new_text.splitlines()
    assert len(old_lines) == len(new_lines)
    changed = [i + 1 for i, (a, b) in enumerate(zip(old_lines, new_lines)) if a != b]
    assert changed == [h.line for h in result.hits]


def test_does_not_touch_longer_identifiers():
    result = scan_text(AUTOMATIONS, PHONE_MAPPINGS)
    assert "notify.mobile_app_pixel_vecchio_altro" in result.new_text
    text = "sensor.x_pixel_vecchio_battery_level binary_sensor.pixel_vecchio_battery_level_2"
    assert scan_text(text, PHONE_MAPPINGS).hits == []


def test_template_dot_notation_and_end_of_sentence():
    m = [Mapping("entity", "sensor.vecchio", "sensor.nuovo")]
    out = scan_text("{{ states.sensor.vecchio.state }} e sensor.vecchio.", m).new_text
    assert out == "{{ states.sensor.nuovo.state }} e sensor.nuovo."


def test_labels_point_to_the_enclosing_automation_not_action_alias():
    result = scan_text(AUTOMATIONS, PHONE_MAPPINGS)
    labels = {h.line: h.label for h in result.hits}
    # la riga con il device_id sta in "Avviso lavatrice finita", non nell'alias dell'azione
    dev_line = next(h for h in result.hits if OLD_DEV in h.before)
    assert dev_line.label == "Avviso lavatrice finita"
    assert {h.label for h in result.hits} == {
        "Avviso lavatrice finita",
        "Batteria telefono scarica",
        "Con blueprint",
    }
    assert all(labels.values())


def test_labels_for_scripts_and_packages():
    s = scan_text(SCRIPTS, PHONE_MAPPINGS)
    assert [h.label for h in s.hits] == ["Invia avviso"]
    p = scan_text(PACKAGE, PHONE_MAPPINGS)
    assert [h.label for h in p.hits] == ["Da package"]


def test_swap_two_entities_in_one_pass():
    m = normalize_mappings(
        [
            {"kind": "entity", "old": "sensor.a", "new": "sensor.b"},
            {"kind": "entity", "old": "sensor.b", "new": "sensor.a"},
        ]
    )
    assert scan_text("sensor.a sensor.b", m).new_text == "sensor.b sensor.a"


def test_crlf_is_preserved():
    text = "- action: notify.mobile_app_pixel_vecchio\r\n  data: {}\r\n"
    out = scan_text(text, PHONE_MAPPINGS).new_text
    assert out == "- action: notify.mobile_app_pixel_nuovo\r\n  data: {}\r\n"


def test_device_id_case_insensitive_and_boundaries():
    m = [Mapping("device", OLD_DEV, NEW_DEV)]
    assert scan_text(f"id: {OLD_DEV.upper()}", m).new_text == f"id: {NEW_DEV}"
    assert scan_text(f"id: {OLD_DEV}ab", m).hits == []


def test_leftovers_flag_unpaired_references():
    text = "entity_id: sensor.pixel_vecchio_solo_vecchio\nentity_id: sensor.altro\n"
    result = scan_text(text, PHONE_MAPPINGS, hints=["sensor.pixel_vecchio_solo_vecchio"])
    assert result.hits == []
    assert [(x["line"], x["token"]) for x in result.leftovers] == [
        (1, "sensor.pixel_vecchio_solo_vecchio")
    ]


@pytest.mark.parametrize(
    "raw",
    [
        {"kind": "entity", "old": "sensor.a", "new": "sensor.a"},
        {"kind": "entity", "old": "sensor", "new": "sensor.b"},
        {"kind": "device", "old": "xyz", "new": NEW_DEV},
        {"kind": "boh", "old": "sensor.a", "new": "sensor.b"},
        {"kind": "entity", "old": "", "new": "sensor.b"},
    ],
)
def test_invalid_mappings_rejected(raw):
    with pytest.raises(ValueError):
        normalize_mappings([raw])


def test_conflicting_mappings_rejected_and_duplicates_merged():
    ok = normalize_mappings(
        [
            {"kind": "entity", "old": "sensor.a", "new": "sensor.b"},
            {"kind": "entity", "old": "sensor.a", "new": "sensor.b"},
        ]
    )
    assert len(ok) == 1
    with pytest.raises(ValueError):
        normalize_mappings(
            [
                {"kind": "entity", "old": "sensor.a", "new": "sensor.b"},
                {"kind": "service", "old": "sensor.a", "new": "sensor.c"},
            ]
        )


def test_scan_config_dir_walks_expected_files(tmp_path):
    (tmp_path / "automations.yaml").write_text(AUTOMATIONS)
    (tmp_path / "scripts.yaml").write_text(SCRIPTS)
    (tmp_path / "packages").mkdir()
    (tmp_path / "packages" / "porta.yaml").write_text(PACKAGE)
    (tmp_path / "configuration.yaml").write_text(UNRELATED)
    (tmp_path / "secrets.yaml").write_text("k: notify.mobile_app_pixel_vecchio\n")
    (tmp_path / "custom_components").mkdir()
    (tmp_path / "custom_components" / "x.yaml").write_text("a: notify.mobile_app_pixel_vecchio\n")
    (tmp_path / ".storage").mkdir()
    (tmp_path / ".storage" / "lovelace").write_text(
        '{"data": {"entity": "sensor.pixel_vecchio_battery_level"}}'
    )
    (tmp_path / "bad.yaml").write_bytes(b"\xff\xfe notify.mobile_app_pixel_vecchio")

    scan = scan_config_dir(tmp_path, PHONE_MAPPINGS)
    assert [f.rel for f in scan.files] == ["automations.yaml", "scripts.yaml", "packages/porta.yaml"]
    assert [s["path"] for s in scan.skipped] == ["bad.yaml"]

    with_dash = scan_config_dir(tmp_path, PHONE_MAPPINGS, include_dashboards=True)
    assert with_dash.files[-1].rel == ".storage/lovelace"
    assert with_dash.files[-1].role == "dashboard"


def test_plan_token_changes_with_content_and_mappings(tmp_path):
    f = tmp_path / "automations.yaml"
    f.write_text(AUTOMATIONS)
    a = scan_config_dir(tmp_path, PHONE_MAPPINGS)
    t1 = engine.plan_token(PHONE_MAPPINGS, a.files)
    assert t1 == engine.plan_token(PHONE_MAPPINGS, a.files)
    f.write_text(AUTOMATIONS + "# x\n")
    b = scan_config_dir(tmp_path, PHONE_MAPPINGS)
    assert engine.plan_token(PHONE_MAPPINGS, b.files) != t1
    assert engine.plan_token(PHONE_MAPPINGS[:1], b.files) != engine.plan_token(PHONE_MAPPINGS, b.files)


# ------------------------------------------------------------------ Node-RED
import json

from sample_config import FLOWS_COMPACT, FLOWS_PRETTY


def _flow_hits(text):
    return scan_text(text, PHONE_MAPPINGS, mode="flows")


def test_flows_replaces_action_split_service_entities_and_device():
    result = _flow_hits(FLOWS_PRETTY)
    nodes = {n["id"]: n for n in json.loads(result.new_text)}  # resta JSON valido
    assert nodes["n2"]["service"] == "mobile_app_pixel_nuovo"
    assert nodes["n2"]["domain"] == "notify"
    assert nodes["n3"]["action"] == "notify.mobile_app_pixel_nuovo"
    assert nodes["n3"]["targets"]["entity_id"] == ["sensor.pixel_nuovo_battery_level"]
    assert nodes["n3"]["targets"]["device_id"] == [NEW_DEV + "#"]
    assert nodes["n1"]["entityidfilter"] == "sensor.pixel_nuovo_battery_level"
    # il nodo con servizio simile non va toccato
    assert nodes["n5"]["service"] == "mobile_app_pixel_vecchio_altro"


def test_flows_identifier_after_json_newline_escape_is_replaced():
    result = _flow_hits(FLOWS_PRETTY)
    func = next(n for n in json.loads(result.new_text) if n["id"] == "n4")["func"]
    assert func == "var a = 'sensor.altro';\nsensor.pixel_nuovo_battery_level\nreturn msg;"


def test_flows_labels_are_flow_and_node_names():
    labels = {h.label for h in _flow_hits(FLOWS_PRETTY).hits}
    assert labels == {
        "Notifiche › Batteria bassa",
        "Notifiche › Notifica batteria",
        "Notifiche › Notifica con azione",
        "Notifiche › Calcolo",
    }


def test_flows_only_formatting_untouched():
    result = _flow_hits(FLOWS_PRETTY)
    old_lines, new_lines = FLOWS_PRETTY.splitlines(), result.new_text.splitlines()
    assert len(old_lines) == len(new_lines)
    assert all(h.line - 1 < len(old_lines) for h in result.hits)


def test_flows_compact_single_line_file_gets_one_hit_per_replacement():
    big = FLOWS_COMPACT.replace('"info":""', '"info":"' + "x" * 4200 + '"', 1)
    assert "\n" not in big and len(big) > engine.LONG_LINE
    result = _flow_hits(big)
    assert len(result.hits) == 6
    assert all(h.truncated for h in result.hits)
    assert [h.label for h in result.hits][:2] == ["Notifiche › Batteria bassa", "Notifiche › Notifica batteria"]
    assert json.loads(result.new_text)  # valido
    old_vals = {n["id"]: n for n in json.loads(big)}
    new_vals = {n["id"]: n for n in json.loads(result.new_text)}
    assert new_vals["n2"]["service"] == "mobile_app_pixel_nuovo" and old_vals["n5"] == new_vals["n5"]


def test_flows_service_with_different_domain_is_not_split_replaced():
    m = [Mapping("service", "notify.mobile_app_pixel_vecchio", "script.mobile_app_pixel_nuovo")]
    result = scan_text(FLOWS_PRETTY, m, mode="flows")
    assert json.loads(result.new_text)  # niente di strano
    nodes = {n["id"]: n for n in json.loads(result.new_text)}
    assert nodes["n2"]["service"] == "mobile_app_pixel_vecchio"


def test_scan_nodered_dir_finds_only_flow_files(tmp_path):
    (tmp_path / "flows.json").write_text(FLOWS_PRETTY)
    (tmp_path / "flows_cred.json").write_text('{"$": "abc"}')
    (tmp_path / "package.json").write_text('{"name": "x"}')
    (tmp_path / "settings.js").write_text("module.exports = {}")
    (tmp_path / "altro.json").write_text(json.dumps({"a": "notify.mobile_app_pixel_vecchio"}))
    scan = engine.scan_nodered_dir(tmp_path, PHONE_MAPPINGS)
    assert [f.rel for f in scan.files] == ["flows.json"]
    assert scan.files[0].role == "nodered" and scan.scanned == 1
    assert engine.nodered_flow_files(tmp_path / "manca") == []


def test_dashboard_json_replaces_after_newline_escape():
    text = '{"a": "x\\nsensor.pixel_vecchio_battery_level"}'
    out = scan_text(text, PHONE_MAPPINGS, mode="json").new_text
    assert json.loads(out)["a"] == "x\nsensor.pixel_nuovo_battery_level"
