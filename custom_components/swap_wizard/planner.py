"""Costruisce le proposte di sostituzione leggendo i registri di Home Assistant.

Qui si decide COSA cambiare (quali identificatori vecchi diventano quali nuovi);
il motore (engine.py) si occupa poi di COME cambiarli nei file.
"""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify

from .engine import ENTITY_RE

MOBILE_DOMAIN = "mobile_app"


class PlanError(Exception):
    """Errore gestito, mostrabile all'utente."""


def _mobile_entries(hass: HomeAssistant) -> dict[str, Any]:
    return {e.entry_id: e for e in hass.config_entries.async_entries(MOBILE_DOMAIN)}


def _mobile_entry_for(device: dr.DeviceEntry, entries: dict[str, Any]):
    return next((entries[c] for c in device.config_entries if c in entries), None)


def _device_name(device: dr.DeviceEntry) -> str:
    return device.name_by_user or device.name or device.id


def notify_service_for(hass: HomeAssistant, device: dr.DeviceEntry, entry) -> str | None:
    """Nome del servizio notify.mobile_app_<nome> del telefono (se e' un telefono)."""
    candidates: list[str] = []
    if entry is not None:
        device_name = entry.data.get("device_name")
        if device_name:
            candidates.append(slugify(device_name))
    for name in (device.name, device.name_by_user):
        if name:
            candidates.append(slugify(name))
    candidates = [c for c in dict.fromkeys(candidates) if c]
    services = hass.services.async_services().get("notify", {})
    for cand in candidates:
        if f"mobile_app_{cand}" in services:
            return f"notify.mobile_app_{cand}"
    return f"notify.mobile_app_{candidates[0]}" if candidates else None


def list_devices(hass: HomeAssistant) -> list[dict]:
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    entries = _mobile_entries(hass)
    result: list[dict] = []
    for dev in dev_reg.devices.values():
        entry = _mobile_entry_for(dev, entries)
        ents = er.async_entries_for_device(ent_reg, dev.id, include_disabled_entities=True)
        if not ents and entry is None:
            continue
        result.append(
            {
                "id": dev.id,
                "name": _device_name(dev),
                "manufacturer": dev.manufacturer,
                "model": dev.model,
                "mobile": entry is not None,
                "notify": notify_service_for(hass, dev, entry) if entry is not None else None,
                "entities": len(ents),
                "disabled": bool(dev.disabled_by),
            }
        )
    result.sort(key=lambda d: (not d["mobile"], d["name"].lower()))
    return result


# --------------------------------------------------------------------------- #
# Abbinamento delle entita' tra vecchio e nuovo dispositivo
# --------------------------------------------------------------------------- #
def _domain(entity_id: str) -> str:
    return entity_id.split(".", 1)[0]


def _key(ent: er.RegistryEntry, entry) -> str | None:
    uid = ent.unique_id
    if entry is not None:
        prefix = entry.data.get("device_id")
        if prefix and isinstance(uid, str) and uid.startswith(f"{prefix}_"):
            return uid[len(prefix) + 1 :]
    if ent.translation_key:
        return ent.translation_key
    if ent.original_name:
        return slugify(ent.original_name)
    return None


def _device_class(ent: er.RegistryEntry) -> str | None:
    return ent.device_class or ent.original_device_class


def pair_entities(old_ents, new_ents, old_entry, new_entry) -> tuple[list[dict], list[str], list[str]]:
    pairs: list[dict] = []
    used_old: set[str] = set()
    used_new: set[str] = set()

    def add(old, new, confidence: str) -> None:
        pairs.append({"old": old.entity_id, "new": new.entity_id, "confidence": confidence})
        used_old.add(old.entity_id)
        used_new.add(new.entity_id)

    # 1) stessa "chiave" (unique_id senza prefisso / translation_key / nome originale)
    new_by_key: dict[tuple[str, str], list] = {}
    for ent in new_ents:
        key = _key(ent, new_entry)
        if key:
            new_by_key.setdefault((_domain(ent.entity_id), key), []).append(ent)
    for ent in old_ents:
        key = _key(ent, old_entry)
        if not key:
            continue
        cands = [
            c
            for c in new_by_key.get((_domain(ent.entity_id), key), [])
            if c.entity_id not in used_new
        ]
        if len(cands) == 1:
            add(ent, cands[0], "high")

    # 2) stesso dominio e stessa classe (es. sensor + battery), uno a uno
    def group(ents, used):
        out: dict[tuple[str, str | None], list] = {}
        for e in ents:
            if e.entity_id not in used:
                out.setdefault((_domain(e.entity_id), _device_class(e)), []).append(e)
        return out

    old_g, new_g = group(old_ents, used_old), group(new_ents, used_new)
    for key, olds in old_g.items():
        news = new_g.get(key, [])
        if key[1] is not None and len(olds) == 1 and len(news) == 1:
            add(olds[0], news[0], "medium")

    # 3) unico candidato rimasto per dominio, uno a uno (incerto)
    old_g, new_g = group(old_ents, used_old), group(new_ents, used_new)
    old_d: dict[str, list] = {}
    new_d: dict[str, list] = {}
    for (dom, _), ents in old_g.items():
        old_d.setdefault(dom, []).extend(ents)
    for (dom, _), ents in new_g.items():
        new_d.setdefault(dom, []).extend(ents)
    for dom, olds in old_d.items():
        news = new_d.get(dom, [])
        if len(olds) == 1 and len(news) == 1:
            add(olds[0], news[0], "low")

    unpaired_old = sorted(e.entity_id for e in old_ents if e.entity_id not in used_old)
    unpaired_new = sorted(e.entity_id for e in new_ents if e.entity_id not in used_new)
    pairs.sort(key=lambda p: p["old"])
    return pairs, unpaired_old, unpaired_new


# --------------------------------------------------------------------------- #
# Proposte
# --------------------------------------------------------------------------- #
def propose_device_swap(hass: HomeAssistant, old_id: str, new_id: str) -> dict:
    if old_id == new_id:
        raise PlanError("il dispositivo vecchio e quello nuovo sono lo stesso")
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    old = dev_reg.async_get(old_id)
    new = dev_reg.async_get(new_id)
    if old is None or new is None:
        raise PlanError("dispositivo non trovato nel registro di Home Assistant")
    entries = _mobile_entries(hass)
    old_entry = _mobile_entry_for(old, entries)
    new_entry = _mobile_entry_for(new, entries)

    mappings: list[dict] = [
        {
            "kind": "device",
            "old": old.id,
            "new": new.id,
            "note": f"{_device_name(old)} → {_device_name(new)}",
            "confidence": "high",
        }
    ]
    warnings: list[str] = []
    hints: list[str] = []

    if old_entry is not None and new_entry is not None:
        old_svc = notify_service_for(hass, old, old_entry)
        new_svc = notify_service_for(hass, new, new_entry)
        if old_svc and new_svc and old_svc != new_svc:
            mappings.append(
                {
                    "kind": "service",
                    "old": old_svc,
                    "new": new_svc,
                    "note": "servizio di notifica del telefono",
                    "confidence": "high",
                }
            )
    elif (old_entry is None) != (new_entry is None):
        warnings.append(
            "Uno dei due dispositivi e' un telefono con l'app Home Assistant e l'altro no: "
            "i servizi di notifica non vengono sostituiti."
        )

    old_ents = er.async_entries_for_device(ent_reg, old.id, include_disabled_entities=True)
    new_ents = er.async_entries_for_device(ent_reg, new.id, include_disabled_entities=True)
    pairs, unpaired_old, unpaired_new = pair_entities(old_ents, new_ents, old_entry, new_entry)
    for pair in pairs:
        if _domain(pair["old"]) != _domain(pair["new"]):
            continue
        mappings.append({"kind": "entity", **pair, "note": ""})

    if unpaired_old:
        warnings.append(
            f"{len(unpaired_old)} entita' del vecchio dispositivo non hanno una corrispondente "
            "sul nuovo: se sono usate in automazioni le trovi nell'anteprima, tra le righe "
            "'da controllare'."
        )
        hints.extend(unpaired_old)
    return {
        "old": {"id": old.id, "name": _device_name(old)},
        "new": {"id": new.id, "name": _device_name(new)},
        "mappings": mappings,
        "unpaired_old": unpaired_old,
        "unpaired_new": unpaired_new,
        "hints": hints,
        "warnings": warnings,
    }


def propose_entity_swap(hass: HomeAssistant, old: str, new: str) -> dict:
    old, new = old.strip().lower(), new.strip().lower()
    for value in (old, new):
        if not ENTITY_RE.match(value):
            raise PlanError(f"'{value}' non sembra un entity_id valido (esempio: sensor.cucina_temperatura)")
    if old == new:
        raise PlanError("l'entita' vecchia e quella nuova sono uguali")
    ent_reg = er.async_get(hass)
    warnings: list[str] = []
    if _domain(old) != _domain(new):
        warnings.append(
            f"Il tipo cambia ({_domain(old)} → {_domain(new)}): i servizi usati nelle "
            "automazioni (per esempio light.turn_on) potrebbero non funzionare piu'."
        )
    known_new = hass.states.get(new) is not None or ent_reg.async_get(new) is not None
    if not known_new:
        warnings.append(f"'{new}' non esiste ancora in Home Assistant: la sostituzione si puo' fare lo stesso.")
    if hass.states.get(old) is not None or ent_reg.async_get(old) is not None:
        warnings.append(f"'{old}' esiste ancora: dopo la sostituzione non sara' piu' usata dalle automazioni.")
    return {
        "mappings": [{"kind": "entity", "old": old, "new": new, "note": "", "confidence": "high"}],
        "unpaired_old": [],
        "unpaired_new": [],
        "hints": [],
        "warnings": warnings,
    }
