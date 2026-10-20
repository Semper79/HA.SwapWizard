"""Registro delle modifiche, backup e rollback di Swap Wizard.

Nessuna dipendenza da Home Assistant.

Su disco (dentro <config>/swap_wizard/):
  operations/<id>.json         registro dell'operazione: mappature, file, righe
                               modificate (prima/dopo), checksum
  backups/<id>/<percorso>      copia originale di ogni file modificato
  backups/<id>/_pre_rollback/  stato dei file subito prima di un rollback
                               (cosi' anche il rollback si puo' annullare a mano)

Garanzie:
  * il registro viene scritto PRIMA di toccare i file: se qualcosa si interrompe
    a meta' resta traccia di cosa stava succedendo;
  * le scritture sono atomiche (file temporaneo + os.replace);
  * se una scrittura fallisce, i file gia' scritti vengono ripristinati subito;
  * senza backup il rollback funziona comunque, riga per riga, grazie al registro;
  * il rollback non tocca nulla se rileva conflitti (a meno di "forza").
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .engine import FileChange, Mapping, sha256_bytes

SCHEMA = 1


class JournalError(Exception):
    """Errore gestito: il messaggio e' pensato per essere mostrato all'utente."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".swap_tmp")
    try:
        with open(tmp, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            shutil.copymode(path, tmp)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def _split_eol(line: str) -> tuple[str, str]:
    stripped = line.rstrip("\r\n")
    return stripped, line[len(stripped) :]


class Journal:
    def __init__(self, base: Path, config_dir: Path) -> None:
        self.base = Path(base)
        self.config_dir = Path(config_dir)
        self.ops_dir = self.base / "operations"
        self.backups_dir = self.base / "backups"

    # ------------------------------------------------------------------ util
    def _manifest_path(self, op_id: str) -> Path:
        if not op_id or any(c in op_id for c in "/\\.") or len(op_id) > 64:
            raise JournalError("identificativo operazione non valido")
        return self.ops_dir / f"{op_id}.json"

    def _save(self, manifest: dict) -> None:
        _atomic_write(
            self._manifest_path(manifest["id"]),
            json.dumps(manifest, ensure_ascii=False, indent=1).encode("utf-8"),
        )

    def get(self, op_id: str) -> dict:
        path = self._manifest_path(op_id)
        if not path.exists():
            raise JournalError("operazione non trovata")
        return json.loads(path.read_text(encoding="utf-8"))

    def history(self) -> list[dict]:
        items: list[dict] = []
        if not self.ops_dir.is_dir():
            return items
        for path in self.ops_dir.glob("*.json"):
            try:
                m = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            items.append(
                {
                    "id": m.get("id"),
                    "created": m.get("created"),
                    "title": m.get("title", ""),
                    "note": m.get("note", ""),
                    "status": m.get("status"),
                    "branch": m.get("branch", "ha"),
                    "backup": m.get("backup", False),
                    "mappings": m.get("mappings", []),
                    "files": len(m.get("files", [])),
                    "lines": sum(len(f.get("hits", [])) for f in m.get("files", [])),
                    "rolled_back_at": m.get("rolled_back_at"),
                    "restart_required": m.get("restart_required", False),
                }
            )
        items.sort(key=lambda x: x.get("created") or "", reverse=True)
        return items

    # ----------------------------------------------------------------- apply
    def apply(
        self,
        mappings: list[Mapping],
        changes: list[FileChange],
        backup: bool,
        title: str = "",
        note: str = "",
        meta: dict | None = None,
    ) -> dict:
        if not changes:
            raise JournalError("nessun file da modificare")
        op_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(2)

        # 1) rilettura e verifica: i file devono essere ancora quelli dell'anteprima
        originals: dict[str, bytes] = {}
        for change in changes:
            path = self.config_dir / change.rel
            try:
                data = path.read_bytes()
            except OSError as err:
                raise JournalError(f"{change.rel}: non leggibile ({err})") from err
            if sha256_bytes(data) != change.old_sha:
                raise JournalError(
                    f"{change.rel} e' cambiato dopo l'anteprima: rigenera l'anteprima e riprova"
                )
            originals[change.rel] = data

        # 2) backup (opzionale)
        if backup:
            try:
                for rel, data in originals.items():
                    target = self.backups_dir / op_id / rel
                    _atomic_write(target, data)
                    shutil.copystat(self.config_dir / rel, target)
            except OSError as err:
                shutil.rmtree(self.backups_dir / op_id, ignore_errors=True)
                raise JournalError(f"backup non riuscito, nessun file modificato: {err}") from err

        new_bytes = {c.rel: c.new_text.encode("utf-8") for c in changes}
        manifest = {
            "schema": SCHEMA,
            "id": op_id,
            "created": _now(),
            "title": title,
            "note": note,
            "branch": "ha",
            **(meta or {}),
            "status": "applying",
            "backup": backup,
            "mappings": [m.to_dict() for m in mappings],
            "files": [
                {
                    **c.to_dict(),
                    "sha_after": sha256_bytes(new_bytes[c.rel]),
                    "backup": backup,
                }
                for c in changes
            ],
        }
        # 3) registro scritto PRIMA delle modifiche
        try:
            self._save(manifest)
        except OSError as err:
            shutil.rmtree(self.backups_dir / op_id, ignore_errors=True)
            raise JournalError(f"impossibile scrivere il registro: {err}") from err

        # 4) scrittura atomica, tutto o niente
        written: list[str] = []
        try:
            for change in changes:
                _atomic_write(self.config_dir / change.rel, new_bytes[change.rel])
                written.append(change.rel)
        except OSError as err:
            for rel in written:
                try:
                    _atomic_write(self.config_dir / rel, originals[rel])
                except OSError:
                    pass
            manifest["status"] = "failed"
            manifest["error"] = str(err)
            self._save(manifest)
            raise JournalError(
                f"scrittura interrotta ({err}): i file gia' modificati sono stati ripristinati"
            ) from err

        manifest["status"] = "applied"
        manifest["restart_required"] = any(c.role == "dashboard" for c in changes)
        self._save(manifest)
        return manifest

    def mark(self, op_id: str, **fields) -> dict:
        manifest = self.get(op_id)
        manifest.update(fields)
        self._save(manifest)
        return manifest

    # -------------------------------------------------------------- rollback
    def _revert_lines(self, text: str, hits: list[dict]) -> str | None:
        """Ripristina riga per riga. None se anche una sola riga non e' ripristinabile."""
        lines = text.splitlines(keepends=True)
        plain = [_split_eol(line)[0] for line in lines]
        assigned: dict[int, dict] = {}
        pending: list[dict] = []
        # prima passata: la riga e' dove ci aspettiamo
        for hit in hits:
            idx = hit["line"] - 1
            if 0 <= idx < len(plain) and idx not in assigned and plain[idx] == hit["after"]:
                assigned[idx] = hit
            else:
                pending.append(hit)
        # seconda passata: il file si e' spostato. Raggruppo per testo: se le righe
        # candidate sono tanto quante le righe da ripristinare le abbino in ordine,
        # altrimenti non so quale sia quale e lascio il conflitto all'utente.
        groups: dict[str, list[dict]] = {}
        for hit in sorted(pending, key=lambda h: h["line"]):
            groups.setdefault(hit["after"], []).append(hit)
        for text_after, group in groups.items():
            candidates = [
                i for i, line in enumerate(plain) if line == text_after and i not in assigned
            ]
            if len(candidates) != len(group):
                return None
            for idx, hit in zip(candidates, group):
                assigned[idx] = hit
        for idx, hit in assigned.items():
            eol = _split_eol(lines[idx])[1]
            lines[idx] = hit["before"] + eol
        return "".join(lines)

    def plan_rollback(self, op_id: str, force: bool = False) -> dict:
        manifest = self.get(op_id)
        if manifest.get("status") == "rolled_back":
            raise JournalError("questa operazione e' gia' stata annullata")
        plan: list[dict] = []
        for entry in manifest["files"]:
            rel = entry["path"]
            path = self.config_dir / rel
            backup_path = self.backups_dir / op_id / rel
            has_backup = bool(entry.get("backup")) and backup_path.is_file()
            item = {"path": rel, "action": None, "bytes": None, "detail": ""}
            current = path.read_bytes() if path.is_file() else None
            sha = sha256_bytes(current) if current is not None else None

            if sha is not None and sha == entry["sha_before"]:
                item["action"] = "already_original"
            elif sha is not None and sha == entry["sha_after"] and has_backup:
                item["action"] = "restored_full"
                item["bytes"] = backup_path.read_bytes()
            else:
                reverted = None
                if current is not None and entry.get("line_revert_ok", True):
                    try:
                        reverted = self._revert_lines(current.decode("utf-8"), entry["hits"])
                    except UnicodeDecodeError:
                        reverted = None
                if reverted is not None:
                    item["action"] = "restored_lines"
                    item["bytes"] = reverted.encode("utf-8")
                elif force and has_backup:
                    item["action"] = "restored_full_forced"
                    item["bytes"] = backup_path.read_bytes()
                    item["detail"] = "il file era stato modificato dopo: ripristinato dalla copia di backup"
                else:
                    item["action"] = "conflict"
                    if current is None:
                        item["detail"] = "il file non esiste piu'"
                    elif has_backup:
                        item["detail"] = (
                            "il file e' stato modificato dopo la sostituzione e le righe non "
                            "sono piu' riconoscibili (e' possibile forzare dal backup)"
                        )
                    else:
                        item["detail"] = (
                            "il file e' stato modificato dopo la sostituzione e non c'e' un "
                            "backup per forzare"
                        )
            plan.append(item)
        return {
            "manifest": manifest,
            "plan": plan,
            "conflicts": [p for p in plan if p["action"] == "conflict"],
        }

    def rollback(self, op_id: str, force: bool = False) -> dict:
        info = self.plan_rollback(op_id, force)
        manifest, plan = info["manifest"], info["plan"]
        if info["conflicts"]:
            return {
                "ok": False,
                "files": [{k: v for k, v in p.items() if k != "bytes"} for p in plan],
                "conflicts": [{k: v for k, v in p.items() if k != "bytes"} for p in info["conflicts"]],
            }
        todo = [p for p in plan if p["bytes"] is not None]
        # istantanea dello stato attuale, cosi' anche il rollback e' reversibile a mano
        snap_dir = self.backups_dir / op_id / "_pre_rollback"
        for p in todo:
            current = self.config_dir / p["path"]
            if current.is_file():
                _atomic_write(snap_dir / p["path"], current.read_bytes())
        written: list[dict] = []
        try:
            for p in todo:
                target = self.config_dir / p["path"]
                before = target.read_bytes() if target.is_file() else None
                _atomic_write(target, p["bytes"])
                written.append({"path": target, "before": before})
        except OSError as err:
            for w in written:
                try:
                    if w["before"] is not None:
                        _atomic_write(w["path"], w["before"])
                except OSError:
                    pass
            raise JournalError(f"rollback interrotto ({err}): nessuna modifica lasciata a meta'") from err
        result_files = [{k: v for k, v in p.items() if k != "bytes"} for p in plan]
        self.mark(
            op_id,
            status="rolled_back",
            rolled_back_at=_now(),
            rollback_files=result_files,
        )
        return {"ok": True, "files": result_files, "conflicts": []}
