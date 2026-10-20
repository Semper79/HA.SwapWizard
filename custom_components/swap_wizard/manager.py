"""Orchestrazione: anteprima, applicazione con controlli, rollback.

Due rami con la stessa logica (anteprima -> backup facoltativo -> modifica -> controllo
-> rollback):
  ha       file di configurazione di Home Assistant (automazioni, script, scene, ...)
  nodered  file dei flow di Node-RED (flows.json)
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DATA_DIR_NAME,
    DEFAULT_NODERED_ADDON,
    NODERED_DIR_NAME,
    OPT_NODERED_ADDON,
    OPT_NODERED_PATH,
)
from .engine import (
    DirScan,
    nodered_flow_files,
    normalize_mappings,
    plan_token,
    scan_config_dir,
    scan_nodered_dir,
)
from .journal import Journal

_LOGGER = logging.getLogger(__name__)

_RELOAD_BY_ROLE: dict[str, list[tuple[str, str]]] = {
    "automation": [("automation", "reload")],
    "script": [("script", "reload")],
    "scene": [("scene", "reload")],
    "blueprint": [("automation", "reload"), ("script", "reload")],
    "package": [("homeassistant", "reload_all")],
    "config": [("homeassistant", "reload_all")],
    "other": [("homeassistant", "reload_all")],
}

_NEEDS_BACKUP = (
    "Alcuni file hanno righe molto lunghe (per esempio flow compatti su una sola riga o "
    "dashboard): il solo registro riga per riga non basta, per questi serve il backup."
)


class SwapError(Exception):
    """Errore gestito, mostrabile all'utente."""


class SwapManager:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry | None = None) -> None:
        self.hass = hass
        self.entry = entry
        self.config_dir = Path(hass.config.path())
        self.data_dir = self.config_dir / DATA_DIR_NAME
        self.journal = Journal(self.data_dir, self.config_dir)  # ramo Home Assistant
        self._nr_base = self.data_dir / NODERED_DIR_NAME
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------ impostazioni
    def settings(self) -> dict:
        opts = dict(self.entry.options) if self.entry else {}
        return {
            "nodered_path": opts.get(OPT_NODERED_PATH, ""),
            "nodered_addon": opts.get(OPT_NODERED_ADDON, DEFAULT_NODERED_ADDON),
        }

    def _save_settings(self, path: str, addon: str) -> None:
        if self.entry is None:
            return
        new = {**self.entry.options, OPT_NODERED_PATH: path, OPT_NODERED_ADDON: addon or DEFAULT_NODERED_ADDON}
        if new != dict(self.entry.options):
            self.hass.config_entries.async_update_entry(self.entry, options=new)

    # --------------------------------------------------------------- Node-RED
    def _path_allowed(self, path: Path) -> bool:
        """Dentro la cartella di configurazione sempre; fuori solo se autorizzata da HA."""
        try:
            path.resolve().relative_to(self.config_dir.resolve())
            return True
        except ValueError:
            return bool(self.hass.config.is_allowed_path(str(path)))

    def _detect_sync(self) -> list[dict]:
        bases = [
            self.config_dir / "node-red",
            self.config_dir / "nodered",
            self.config_dir / ".node-red",
            Path("/share/node-red"),
            Path("/share/nodered"),
        ]
        addon_configs = Path("/addon_configs")
        if addon_configs.is_dir():
            bases += sorted(addon_configs.glob("*node*red*"))
        seen: set[str] = set()
        found: list[dict] = []
        for base in bases:
            key = str(base)
            if key in seen or not base.is_dir():
                continue
            seen.add(key)
            files = nodered_flow_files(base)
            if files:
                found.append(
                    {
                        "path": key,
                        "files": [f.name for f in files],
                        "allowed": self._path_allowed(base),
                    }
                )
        return found

    async def async_nodered_detect(self) -> dict:
        candidates = await self.hass.async_add_executor_job(self._detect_sync)
        return {"candidates": candidates, "settings": self.settings()}

    def _nodered_root_sync(self, path_str: str) -> Path:
        path_str = (path_str or "").strip()
        if not path_str:
            raise SwapError("Indica la cartella di Node-RED (quella che contiene flows.json).")
        path = Path(path_str)
        if not path.is_absolute():
            raise SwapError("Il percorso deve essere assoluto, per esempio /config/node-red")
        if not path.is_dir():
            raise SwapError(
                f"Cartella non trovata: {path}. Home Assistant deve poterla vedere "
                "(con il componente aggiuntivo di solito e' /config/node-red)."
            )
        if not self._path_allowed(path):
            raise SwapError(
                f"Home Assistant non e' autorizzato a usare {path}: aggiungila a "
                "allowlist_external_dirs in configuration.yaml e riavvia."
            )
        return path.resolve()

    async def _nodered_root(self, path_str: str) -> Path:
        return await self.hass.async_add_executor_job(self._nodered_root_sync, path_str)

    @staticmethod
    def _validate_flows(root: Path, selected) -> str | None:
        for change in selected:
            try:
                json.loads((root / change.rel).read_text(encoding="utf-8"))
            except (OSError, ValueError) as err:
                return f"{change.rel}: {err}"
        return None

    async def _restart_nodered(self, addon: str) -> dict:
        addon = (addon or DEFAULT_NODERED_ADDON).strip()
        if not self.hass.services.has_service("hassio", "addon_restart"):
            return {
                "done": False,
                "error": "Il riavvio automatico richiede Home Assistant OS o Supervised: "
                "riavvia Node-RED a mano.",
            }
        try:
            await self.hass.services.async_call("hassio", "addon_restart", {"addon": addon}, blocking=True)
        except HomeAssistantError as err:
            return {"done": False, "error": f"Riavvio di '{addon}' non riuscito: {err}"}
        return {"done": True, "addon": addon}

    def _journal_for(self, op_id: str, branch: str) -> Journal:
        if branch != "nodered":
            return self.journal
        manifest = Journal(self._nr_base, self.config_dir).get(op_id)
        root = Path(manifest.get("root") or "")
        if not root.is_dir():
            raise SwapError(f"La cartella di Node-RED di questa operazione non esiste piu': {root}")
        return Journal(self._nr_base, root)

    # ------------------------------------------------------------- anteprima
    async def _scan(self, raw_mappings, hints, include_dashboards, branch, nodered_path):
        mappings = normalize_mappings(raw_mappings)
        if branch == "nodered":
            root = await self._nodered_root(nodered_path)
            scan: DirScan = await self.hass.async_add_executor_job(
                scan_nodered_dir, root, mappings, list(hints or [])
            )
            return mappings, scan, root
        scan = await self.hass.async_add_executor_job(
            scan_config_dir, self.config_dir, mappings, list(hints or []), bool(include_dashboards)
        )
        return mappings, scan, self.config_dir

    async def async_preview(
        self, raw_mappings, hints, include_dashboards, branch="ha", nodered_path=""
    ) -> dict:
        mappings, scan, root = await self._scan(raw_mappings, hints, include_dashboards, branch, nodered_path)
        backup_dir = (
            f"{DATA_DIR_NAME}/{NODERED_DIR_NAME}/backups" if branch == "nodered" else f"{DATA_DIR_NAME}/backups"
        )
        return {
            "branch": branch,
            "root": str(root),
            "token": plan_token(mappings, scan.files),
            "mappings": [m.to_dict() for m in mappings],
            "files": [f.to_dict() for f in scan.files],
            "leftovers": scan.leftovers,
            "skipped": scan.skipped,
            "scanned": scan.scanned,
            "no_flow_files": branch == "nodered" and scan.scanned == 0,
            "totals": {
                "files": len(scan.files),
                "lines": sum(len(f.hits) for f in scan.files),
            },
            "backup_dir": backup_dir,
        }

    # ------------------------------------------------------------- controllo
    async def _check_config(self) -> tuple[bool, str | None]:
        """(controllo_disponibile, errori). errori None = configurazione valida."""
        try:
            from homeassistant.config import async_check_ha_config_file  # type: ignore

            return True, await async_check_ha_config_file(self.hass)
        except ImportError:
            pass
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Controllo configurazione non riuscito: %s", err)
            return False, None
        try:
            from homeassistant.helpers.check_config import (  # type: ignore
                async_check_ha_config_file as helper_check,
            )

            result = await helper_check(self.hass)
            errors = [str(getattr(e, "message", e)) for e in result.errors]
            return True, "; ".join(errors) if errors else None
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Controllo configurazione non disponibile: %s", err)
            return False, None

    async def _reload(self, roles) -> dict:
        calls: list[tuple[str, str]] = []
        for role in roles:
            for call in _RELOAD_BY_ROLE.get(role, []):
                if call not in calls:
                    calls.append(call)
        if ("homeassistant", "reload_all") in calls:
            calls = [c for c in calls if c[0] not in ("automation", "script", "scene")]
        done: list[str] = []
        errors: list[str] = []
        for domain, service in calls:
            name = f"{domain}.{service}"
            if not self.hass.services.has_service(domain, service):
                continue
            try:
                await self.hass.services.async_call(domain, service, blocking=True)
                done.append(name)
            except HomeAssistantError as err:
                errors.append(f"{name}: {err}")
        return {
            "done": done,
            "errors": errors,
            "restart_required": "dashboard" in set(roles),
        }

    # ------------------------------------------------------------ applicazione
    async def async_apply(
        self,
        raw_mappings,
        hints,
        include_dashboards,
        token: str,
        files: list[str],
        backup: bool,
        title: str = "",
        note: str = "",
        branch: str = "ha",
        nodered_path: str = "",
        restart_nodered: bool = False,
        nodered_addon: str = "",
    ) -> dict:
        async with self._lock:
            mappings, scan, root = await self._scan(raw_mappings, hints, include_dashboards, branch, nodered_path)
            if plan_token(mappings, scan.files) != token:
                raise SwapError(
                    "I file sono cambiati dopo l'anteprima (o le sostituzioni sono diverse): "
                    "torna indietro e rigenera l'anteprima."
                )
            chosen = set(files)
            selected = [f for f in scan.files if f.rel in chosen]
            if not selected:
                raise SwapError("Nessun file selezionato.")
            if not backup and any(not f.line_revert_ok for f in selected):
                raise SwapError(_NEEDS_BACKUP)
            if branch == "nodered":
                return await self._apply_nodered(
                    mappings, selected, root, backup, title, note, restart_nodered, nodered_addon
                )
            return await self._apply_ha(mappings, selected, backup, title, note)

    async def _apply_ha(self, mappings, selected, backup, title, note) -> dict:
        available, errors_before = await self._check_config()
        manifest = await self.hass.async_add_executor_job(
            self.journal.apply, mappings, selected, backup, title, note
        )
        roles = [f.role for f in selected]
        available_after, errors_after = await self._check_config()

        if errors_after and errors_after != errors_before:
            rollback = await self.hass.async_add_executor_job(self.journal.rollback, manifest["id"])
            if rollback["ok"]:
                await self.hass.async_add_executor_job(
                    lambda: self.journal.mark(manifest["id"], auto_rollback_reason=errors_after)
                )
                await self._reload(roles)
            return {
                "ok": False,
                "branch": "ha",
                "auto_rolled_back": rollback["ok"],
                "error": errors_after,
                "operation": manifest["id"],
            }

        reload_result = await self._reload(roles)
        return {
            "ok": True,
            "branch": "ha",
            "operation": manifest["id"],
            "files": len(selected),
            "lines": sum(len(f.hits) for f in selected),
            "backup": backup,
            "check_available": available and available_after,
            "config_already_invalid": bool(errors_before),
            "reload": reload_result,
        }

    async def _apply_nodered(
        self, mappings, selected, root: Path, backup, title, note, restart, addon
    ) -> dict:
        addon = (addon or DEFAULT_NODERED_ADDON).strip()
        self._save_settings(str(root), addon)
        journal = Journal(self._nr_base, root)
        manifest = await self.hass.async_add_executor_job(
            journal.apply, mappings, selected, backup, title, note, {"branch": "nodered", "root": str(root)}
        )
        problem = await self.hass.async_add_executor_job(self._validate_flows, root, selected)
        if problem:
            rollback = await self.hass.async_add_executor_job(journal.rollback, manifest["id"])
            if rollback["ok"]:
                await self.hass.async_add_executor_job(
                    lambda: journal.mark(manifest["id"], auto_rollback_reason=problem)
                )
            return {
                "ok": False,
                "branch": "nodered",
                "auto_rolled_back": rollback["ok"],
                "error": problem,
                "operation": manifest["id"],
            }
        result = {
            "ok": True,
            "branch": "nodered",
            "operation": manifest["id"],
            "files": len(selected),
            "lines": sum(len(f.hits) for f in selected),
            "backup": backup,
            "restart": {"requested": bool(restart)},
        }
        if restart:
            result["restart"].update(await self._restart_nodered(addon))
        return result

    # ---------------------------------------------------------------- storico
    async def async_history(self) -> list[dict]:
        def collect() -> list[dict]:
            items = self.journal.history() + Journal(self._nr_base, self.config_dir).history()
            items.sort(key=lambda x: x.get("created") or "", reverse=True)
            return items

        return await self.hass.async_add_executor_job(collect)

    async def async_operation(self, op_id: str, branch: str = "ha") -> dict:
        def load() -> dict:
            journal = self._journal_for(op_id, branch)
            manifest = journal.get(op_id)
            return {"operation": manifest, "rollback_preview": self._rollback_preview(journal, op_id, manifest)}

        return await self.hass.async_add_executor_job(load)

    @staticmethod
    def _rollback_preview(journal: Journal, op_id: str, manifest: dict) -> dict | None:
        if manifest.get("status") == "rolled_back":
            return None
        info = journal.plan_rollback(op_id, force=False)
        return {
            "files": [{k: v for k, v in p.items() if k != "bytes"} for p in info["plan"]],
            "conflicts": [{k: v for k, v in p.items() if k != "bytes"} for p in info["conflicts"]],
        }

    async def async_rollback(
        self,
        op_id: str,
        force: bool = False,
        branch: str = "ha",
        restart_nodered: bool = False,
        nodered_addon: str = "",
    ) -> dict:
        async with self._lock:
            journal = await self.hass.async_add_executor_job(self._journal_for, op_id, branch)
            result = await self.hass.async_add_executor_job(journal.rollback, op_id, force)
            if not result["ok"]:
                return {"ok": False, "conflicts": result["conflicts"], "files": result["files"]}
            manifest = await self.hass.async_add_executor_job(journal.get, op_id)
            if branch == "nodered":
                restart = {"requested": bool(restart_nodered)}
                if restart_nodered:
                    restart.update(await self._restart_nodered(nodered_addon))
                return {"ok": True, "branch": "nodered", "files": result["files"], "restart": restart}
            changed = {f["path"] for f in result["files"] if f["action"] != "already_original"}
            roles = [f["role"] for f in manifest["files"] if f["path"] in changed]
            reload_result = await self._reload(roles)
            _, errors = await self._check_config()
            return {
                "ok": True,
                "branch": "ha",
                "files": result["files"],
                "reload": reload_result,
                "config_error": errors,
            }
