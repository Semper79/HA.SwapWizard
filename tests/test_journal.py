import json

import pytest
from swc import journal as journal_mod
from swc.engine import Mapping, scan_config_dir
from swc.journal import Journal, JournalError

from sample_config import AUTOMATIONS, NEW_DEV, OLD_DEV, SCRIPTS

MAPPINGS = [
    Mapping("service", "notify.mobile_app_pixel_vecchio", "notify.mobile_app_pixel_nuovo"),
    Mapping("entity", "sensor.pixel_vecchio_battery_level", "sensor.pixel_nuovo_battery_level"),
    Mapping("device", OLD_DEV, NEW_DEV),
]


@pytest.fixture
def env(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "automations.yaml").write_text(AUTOMATIONS)
    (cfg / "scripts.yaml").write_text(SCRIPTS)
    j = Journal(cfg / "swap_wizard", cfg)
    return cfg, j


def _apply(cfg, j, backup=True):
    scan = scan_config_dir(cfg, MAPPINGS)
    return j.apply(MAPPINGS, scan.files, backup=backup, title="Test")


def test_apply_with_backup_then_full_rollback(env):
    cfg, j = env
    manifest = _apply(cfg, j)
    assert manifest["status"] == "applied"
    assert "notify.mobile_app_pixel_nuovo" in (cfg / "automations.yaml").read_text()
    # backup identico all'originale
    assert (j.backups_dir / manifest["id"] / "automations.yaml").read_text() == AUTOMATIONS
    # il registro contiene le righe prima/dopo
    saved = json.loads((j.ops_dir / f"{manifest['id']}.json").read_text())
    hit = saved["files"][0]["hits"][0]
    assert "vecchio" in hit["before"] and "nuovo" in hit["after"]

    result = j.rollback(manifest["id"])
    assert result["ok"]
    assert {f["action"] for f in result["files"]} == {"restored_full"}
    assert (cfg / "automations.yaml").read_text() == AUTOMATIONS
    assert (cfg / "scripts.yaml").read_text() == SCRIPTS
    assert j.get(manifest["id"])["status"] == "rolled_back"
    with pytest.raises(JournalError):
        j.rollback(manifest["id"])


def test_no_backup_still_rolls_back_line_by_line(env):
    cfg, j = env
    manifest = _apply(cfg, j, backup=False)
    assert not (j.backups_dir / manifest["id"]).exists()
    result = j.rollback(manifest["id"])
    assert result["ok"]
    assert {f["action"] for f in result["files"]} == {"restored_lines"}
    assert (cfg / "automations.yaml").read_text() == AUTOMATIONS


def test_rollback_keeps_later_unrelated_edits(env):
    cfg, j = env
    manifest = _apply(cfg, j)
    path = cfg / "automations.yaml"
    # l'utente aggiunge righe all'inizio (le righe si spostano) e in fondo
    path.write_text("# nuova nota\n" + path.read_text() + "- id: 'x'\n  alias: Nuova\n")
    result = j.rollback(manifest["id"])
    assert result["ok"]
    restored = path.read_text()
    assert restored == "# nuova nota\n" + AUTOMATIONS + "- id: 'x'\n  alias: Nuova\n"


def test_conflict_changes_nothing_then_force_uses_backup(env):
    cfg, j = env
    manifest = _apply(cfg, j)
    path = cfg / "automations.yaml"
    edited = path.read_text().replace(
        "action: notify.mobile_app_pixel_nuovo\n    data:\n      title: Lavatrice",
        "action: notify.mobile_app_pixel_nuovo_ritoccato\n    data:\n      title: Lavatrice",
    )
    assert edited != path.read_text()
    path.write_text(edited)
    scripts_after = (cfg / "scripts.yaml").read_text()

    result = j.rollback(manifest["id"])
    assert not result["ok"]
    assert [c["path"] for c in result["conflicts"]] == ["automations.yaml"]
    # nessun file e' stato toccato, nemmeno quelli senza conflitto
    assert path.read_text() == edited
    assert (cfg / "scripts.yaml").read_text() == scripts_after
    assert j.get(manifest["id"])["status"] == "applied"

    forced = j.rollback(manifest["id"], force=True)
    assert forced["ok"]
    assert path.read_text() == AUTOMATIONS
    # la versione ritoccata e' salvata prima del ripristino
    snap = j.backups_dir / manifest["id"] / "_pre_rollback" / "automations.yaml"
    assert snap.read_text() == edited


def test_conflict_without_backup_cannot_be_forced(env):
    cfg, j = env
    manifest = _apply(cfg, j, backup=False)
    path = cfg / "automations.yaml"
    path.write_text(path.read_text().replace("pixel_nuovo", "pixel_boh"))
    result = j.rollback(manifest["id"], force=True)
    assert not result["ok"]
    assert result["conflicts"]


def test_apply_refuses_if_file_changed_after_preview(env):
    cfg, j = env
    scan = scan_config_dir(cfg, MAPPINGS)
    (cfg / "automations.yaml").write_text(AUTOMATIONS + "# modificato\n")
    with pytest.raises(JournalError, match="cambiato dopo l'anteprima"):
        j.apply(MAPPINGS, scan.files, backup=True)
    assert (cfg / "automations.yaml").read_text() == AUTOMATIONS + "# modificato\n"
    assert not j.ops_dir.exists() or not list(j.ops_dir.glob("*.json"))


def test_write_failure_restores_files_already_written(env, monkeypatch):
    cfg, j = env
    scan = scan_config_dir(cfg, MAPPINGS)
    real = journal_mod._atomic_write
    state = {"writes": 0}

    def flaky(path, data):
        # lascia passare backup e registro, fa fallire la seconda scrittura "vera" di config
        if path.parent == cfg and path.name.endswith(".yaml"):
            state["writes"] += 1
            if state["writes"] == 2:
                raise OSError("disco pieno")
        return real(path, data)

    monkeypatch.setattr(journal_mod, "_atomic_write", flaky)
    with pytest.raises(JournalError, match="ripristinati"):
        j.apply(MAPPINGS, scan.files, backup=True)
    monkeypatch.setattr(journal_mod, "_atomic_write", real)
    assert (cfg / "automations.yaml").read_text() == AUTOMATIONS
    assert (cfg / "scripts.yaml").read_text() == SCRIPTS
    history = j.history()
    assert history[0]["status"] == "failed"


def test_history_is_sorted_newest_first(env):
    cfg, j = env
    first = _apply(cfg, j)
    j.rollback(first["id"])
    second = _apply(cfg, j)
    ids = [h["id"] for h in j.history()]
    assert ids[0] == second["id"] and ids[1] == first["id"]
    assert j.history()[0]["files"] == 2


def test_invalid_operation_id(env):
    _, j = env
    with pytest.raises(JournalError):
        j.get("../../etc/passwd")
