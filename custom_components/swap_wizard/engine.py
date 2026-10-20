"""Motore di ricerca e sostituzione di Swap Wizard.

Nessuna dipendenza da Home Assistant: si puo' testare da solo.

Principio di base: le sostituzioni sono fatte sul TESTO dei file, senza mai
ri-scrivere (ri-serializzare) il YAML o il JSON. In questo modo commenti, ordine,
virgolette e formattazione restano identici e l'automazione (o il flow) non puo'
rompersi per colpa del formato: cambiano solo gli identificatori.

Tipi di riferimento gestiti:
  entity  -> entity_id            (sensor.vecchio -> sensor.nuovo)
  service -> servizio             (notify.mobile_app_vecchio -> notify.mobile_app_nuovo)
  device  -> device_id (32 hex)   (azioni/trigger "dispositivo" dell'editor grafico,
                                   input di blueprint, nodi dispositivo di Node-RED)

Modalita' di lettura del testo:
  yaml   automazioni, script, scene, package, blueprint (etichetta = nome automazione)
  json   file JSON salvati da Home Assistant (dashboard): nessuna etichetta
  flows  flow di Node-RED (etichetta = "Flow > Nodo"); riconosce anche il servizio
         scritto in due campi separati ("domain": "notify", "service": "mobile_app_x")
"""
from __future__ import annotations

import bisect
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

ENTITY_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
DEVICE_RE = re.compile(r"^[0-9a-f]{32}$")
KINDS = ("entity", "service", "device")
MODES = ("yaml", "json", "flows")

SCAN_SUFFIXES = {".yaml", ".yml", ".jinja"}
SKIP_DIRS = {
    "custom_components",
    "deps",
    "backups",
    "swap_wizard",
    "www",
    "node_modules",
    "__pycache__",
    "tts",
    "themes",
    "venv",
}
SKIP_FILES = {"secrets.yaml"}
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_FLOW_BYTES = 50 * 1024 * 1024
LONG_LINE = 4000  # oltre questa lunghezza la riga non e' ripristinabile "per riga"

_ID_BEFORE = r"(?<![A-Za-z0-9_])"
_ID_AFTER = r"(?![A-Za-z0-9_])"
# nel JSON "\nsensor.x" e' una "a capo" seguita da sensor.x, non una parola che finisce in n
_JSON_ID_BEFORE = r"(?:(?<![A-Za-z0-9_])|(?<=\\[ntrbf]))"
_HEX_BEFORE = r"(?<![0-9A-Fa-f])"
_HEX_AFTER = r"(?![0-9A-Fa-f])"


# --------------------------------------------------------------------------- #
# Mappature
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Mapping:
    kind: str
    old: str
    new: str
    note: str = ""

    @classmethod
    def from_dict(cls, raw: object) -> "Mapping":
        if not isinstance(raw, dict):
            raise ValueError("riga di sostituzione non valida")
        kind = str(raw.get("kind", "")).strip().lower()
        old = str(raw.get("old", "")).strip().lower()
        new = str(raw.get("new", "")).strip().lower()
        note = str(raw.get("note", "") or "")[:200]
        if kind not in KINDS:
            raise ValueError(f"tipo sconosciuto: {kind!r}")
        if not old or not new:
            raise ValueError("il valore vecchio e quello nuovo sono obbligatori")
        if old == new:
            raise ValueError(f"'{old}' e' uguale al valore nuovo")
        pattern = DEVICE_RE if kind == "device" else ENTITY_RE
        for value in (old, new):
            if not pattern.match(value):
                raise ValueError(f"valore non valido per il tipo '{kind}': {value!r}")
        return cls(kind, old, new, note)

    def to_dict(self) -> dict:
        return {"kind": self.kind, "old": self.old, "new": self.new, "note": self.note}


def normalize_mappings(raw_list: object) -> list[Mapping]:
    """Valida l'elenco, toglie i doppioni e blocca le contraddizioni."""
    if not isinstance(raw_list, list) or not raw_list:
        raise ValueError("nessuna sostituzione indicata")
    result: dict[str, Mapping] = {}
    for raw in raw_list:
        mapping = Mapping.from_dict(raw)
        # entity e service condividono lo stesso "spazio" nel testo
        key = ("device:" if mapping.kind == "device" else "id:") + mapping.old
        if key in result:
            if result[key].new != mapping.new:
                raise ValueError(
                    f"'{mapping.old}' e' sostituito con due valori diversi "
                    f"({result[key].new} e {mapping.new})"
                )
            continue
        result[key] = mapping
    return list(result.values())


@dataclass
class _Patterns:
    id_re: re.Pattern | None = None
    idmap: dict = field(default_factory=dict)
    dev_re: re.Pattern | None = None
    devmap: dict = field(default_factory=dict)
    svc_re: re.Pattern | None = None
    svcmap: dict = field(default_factory=dict)


def _build_patterns(mappings: list[Mapping], mode: str) -> _Patterns:
    pat = _Patterns()
    pat.idmap = {m.old: m.new for m in mappings if m.kind != "device"}
    pat.devmap = {m.old: m.new for m in mappings if m.kind == "device"}
    before = _ID_BEFORE if mode == "yaml" else _JSON_ID_BEFORE
    if pat.idmap:
        alt = "|".join(re.escape(k) for k in sorted(pat.idmap, key=len, reverse=True))
        pat.id_re = re.compile(f"{before}(?:{alt}){_ID_AFTER}")
    if pat.devmap:
        alt = "|".join(re.escape(k) for k in pat.devmap)
        pat.dev_re = re.compile(f"{_HEX_BEFORE}(?:{alt}){_HEX_AFTER}", re.IGNORECASE)
    if mode == "flows":
        for m in mappings:
            if m.kind != "service":
                continue
            dom_old, name_old = m.old.split(".", 1)
            dom_new, name_new = m.new.split(".", 1)
            if dom_old == dom_new:
                pat.svcmap[name_old] = name_new
        if pat.svcmap:
            alt = "|".join(re.escape(k) for k in sorted(pat.svcmap, key=len, reverse=True))
            pat.svc_re = re.compile(
                r'((?:\\)?"service(?:\\)?"\s*:\s*(?:\\)?")(' + alt + r')((?:\\)?")'
            )
    return pat


def _matches(line: str, pat: _Patterns) -> list[tuple[int, int, str, str]]:
    """Tutte le sostituzioni di una riga, con posizioni sul testo ORIGINALE."""
    found: list[tuple[int, int, str, str]] = []
    if pat.id_re is not None:
        for m in pat.id_re.finditer(line):
            found.append((m.start(), m.end(), m.group(0), pat.idmap[m.group(0)]))
    if pat.dev_re is not None:
        for m in pat.dev_re.finditer(line):
            found.append((m.start(), m.end(), m.group(0), pat.devmap[m.group(0).lower()]))
    if pat.svc_re is not None:
        for m in pat.svc_re.finditer(line):
            found.append((m.start(2), m.end(2), m.group(2), pat.svcmap[m.group(2)]))
    found.sort()
    result: list[tuple[int, int, str, str]] = []
    last_end = -1
    for item in found:
        if item[0] >= last_end:
            result.append(item)
            last_end = item[1]
    return result


# --------------------------------------------------------------------------- #
# Etichette (a quale automazione / script / nodo appartiene una riga)
# --------------------------------------------------------------------------- #
_KEY_LINE = re.compile(r"^(?P<k>[^\s#\-][^:#]*?):\s*(?:#.*)?$")
_NAME_LINE = re.compile(r"^\s*(?:- )?(?:alias|name):\s*(?P<v>.+?)\s*$")
_ALIAS_LINE = re.compile(r"^\s*(?:- )?alias:\s*(?P<v>.+?)\s*$")
_ID_LINE = re.compile(r"^\s*(?:- )?id:\s*(?P<v>.+?)\s*$")
_DOMAIN_KEYS = {"automation", "script", "scene"}


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


class _Labeler:
    """Etichette per file YAML."""

    def __init__(self, lines: list[str]) -> None:
        self.lines = lines
        self.content: list[bool] = []
        self.indent: list[int] = []
        for line in lines:
            stripped = line.strip()
            is_content = bool(stripped) and not stripped.startswith("#")
            self.content.append(is_content)
            self.indent.append(len(line) - len(line.lstrip(" ")) if is_content else -1)

    def _prev_with_indent(self, idx: int, indent: int, lower: int = 0) -> int | None:
        for i in range(idx, lower - 1, -1):
            if self.content[i] and self.indent[i] == indent:
                return i
        return None

    def _block_end(self, root: int, base: int) -> int:
        for i in range(root + 1, len(self.lines)):
            if self.content[i] and self.indent[i] <= base:
                return i
        return len(self.lines)

    def _name_in_block(self, root: int, base: int) -> str | None:
        end = self._block_end(root, base)
        found_alias = found_name = None
        for i in range(root, end):
            if not self.content[i]:
                continue
            if i != root and self.indent[i] != base + 2:
                continue
            m = _ALIAS_LINE.match(self.lines[i])
            if m and found_alias is None:
                found_alias = _unquote(m.group("v"))
                break
            m = _NAME_LINE.match(self.lines[i])
            if m and found_name is None:
                found_name = _unquote(m.group("v"))
        if found_alias or found_name:
            return found_alias or found_name
        return None

    def label(self, idx: int, col: int = 0) -> str | None:
        top = self._prev_with_indent(idx, 0)
        if top is None:
            return None
        base = 0
        root = top
        key_match = _KEY_LINE.match(self.lines[top].rstrip("\r\n"))
        if key_match and key_match.group("k").strip().strip("'\"") in _DOMAIN_KEYS:
            child_indent = None
            for i in range(top + 1, len(self.lines)):
                if self.content[i]:
                    child_indent = self.indent[i]
                    break
            if not child_indent:
                return key_match.group("k")
            item = self._prev_with_indent(idx, child_indent, top + 1)
            if item is None:
                return key_match.group("k")
            root, base = item, child_indent
        name = self._name_in_block(root, base)
        if name:
            return name
        line = self.lines[root].rstrip("\r\n")
        m = _ID_LINE.match(line)
        if m:
            return f"id {_unquote(m.group('v'))}"
        km = _KEY_LINE.match(line)
        if km:
            return km.group("k").strip().strip("'\"")
        return None


_JSON_TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|[{}\[\]]')


class _FlowLabeler:
    """Etichette per i flow di Node-RED: 'Nome del flow > Nome del nodo'.

    Lavora su posizioni esatte nel testo, quindi funziona sia con il file formattato
    (un nodo per blocco) sia con il file compatto su una sola riga.
    """

    def __init__(self, text: str) -> None:
        self.text = text
        self.spans: list[tuple[int, int]] = []
        depth = 0
        start = None
        for m in _JSON_TOKEN.finditer(text):
            tok = m.group(0)
            if tok == "{":
                if depth == 1:
                    start = m.start()
                depth += 1
            elif tok == "[":
                depth += 1
            elif tok in ("}", "]"):
                depth -= 1
                if tok == "}" and depth == 1 and start is not None:
                    self.spans.append((start, m.end()))
                    start = None
        self._starts = [s for s, _ in self.spans]
        self._cache: dict[int, dict | None] = {}
        self._tabs: dict[str, str] | None = None

    def _node(self, i: int) -> dict | None:
        if i not in self._cache:
            start, end = self.spans[i]
            try:
                node = json.loads(self.text[start:end])
            except ValueError:
                node = None
            self._cache[i] = node if isinstance(node, dict) else None
        return self._cache[i]

    def _tab_names(self) -> dict[str, str]:
        if self._tabs is None:
            self._tabs = {}
            for i, (start, end) in enumerate(self.spans):
                if '"tab"' in self.text[start:end]:
                    node = self._node(i)
                    if node and node.get("type") == "tab":
                        self._tabs[str(node.get("id"))] = str(node.get("label") or node.get("id"))
        return self._tabs

    def label_at(self, offset: int) -> str | None:
        i = bisect.bisect_right(self._starts, offset) - 1
        if i < 0 or offset >= self.spans[i][1]:
            return None
        node = self._node(i)
        if not node:
            return None
        name = str(node.get("name") or node.get("label") or node.get("type") or node.get("id"))
        flow = self._tab_names().get(str(node.get("z")))
        if node.get("type") == "tab":
            return name
        return f"{flow} › {name}" if flow else name


# --------------------------------------------------------------------------- #
# Scansione di un testo
# --------------------------------------------------------------------------- #
@dataclass
class Hit:
    line: int
    before: str
    after: str
    label: str | None
    pairs: list[tuple[str, str]]
    truncated: bool = False

    def to_dict(self) -> dict:
        return {
            "line": self.line,
            "before": self.before,
            "after": self.after,
            "label": self.label,
            "pairs": [list(p) for p in self.pairs],
            "truncated": self.truncated,
        }


@dataclass
class ScanResult:
    new_text: str
    hits: list[Hit] = field(default_factory=list)
    leftovers: list[dict] = field(default_factory=list)


def _snippet(line: str, around: str | None) -> tuple[str, bool]:
    if len(line) <= LONG_LINE:
        return line, False
    pos = line.find(around) if around else 0
    pos = max(pos, 0)
    start = max(0, pos - 150)
    return "…" + line[start : pos + 150] + "…", True


def scan_text(
    text: str,
    mappings: list[Mapping],
    hints: list[str] | None = None,
    mode: str = "yaml",
) -> ScanResult:
    if mode not in MODES:
        raise ValueError(f"modalita' sconosciuta: {mode}")
    pat = _build_patterns(mappings, mode)
    lines = text.splitlines(keepends=True)
    hits: list[Hit] = []
    new_lines: list[str] = []
    line_starts: list[int] = []
    pos = 0
    for line in lines:
        line_starts.append(pos)
        pos += len(line)

    lazy: dict = {}

    def label(idx: int, col: int) -> str | None:
        if mode == "json":
            return None
        if "l" not in lazy:
            lazy["l"] = _FlowLabeler(text) if mode == "flows" else _Labeler(lines)
        if mode == "flows":
            return lazy["l"].label_at(line_starts[idx] + col)
        return lazy["l"].label(idx)

    for idx, line in enumerate(lines):
        found = _matches(line, pat)
        if not found:
            new_lines.append(line)
            continue
        out: list[str] = []
        last = 0
        for start, end, old, new in found:
            out.append(line[last:start])
            out.append(new)
            last = end
        out.append(line[last:])
        new_line = "".join(out)
        new_lines.append(new_line)
        if mode == "flows" and len(line) > LONG_LINE:
            # flow compatto su una riga sola: una voce per ogni sostituzione, con il
            # solo tratto di testo attorno e l'etichetta del proprio nodo
            delta = 0
            for start, end, old, new in found:
                ns = start + delta
                hits.append(
                    Hit(
                        idx + 1,
                        "…" + line[max(0, start - 90) : end + 90] + "…",
                        "…" + new_line[max(0, ns - 90) : ns + len(new) + 90] + "…",
                        label(idx, start),
                        [(old, new)],
                        True,
                    )
                )
                delta += len(new) - (end - start)
            continue
        pairs = [(old, new) for _, _, old, new in found]
        before, trunc1 = _snippet(line.rstrip("\r\n"), pairs[0][0])
        after, trunc2 = _snippet(new_line.rstrip("\r\n"), pairs[0][1])
        hits.append(Hit(idx + 1, before, after, label(idx, found[0][0]), pairs, trunc1 or trunc2))

    new_text = "".join(new_lines)
    leftovers: list[dict] = []
    tokens = [h for h in (hints or []) if ENTITY_RE.match(h)]
    if tokens and any(t in new_text for t in tokens):
        alt = "|".join(re.escape(t) for t in sorted(tokens, key=len, reverse=True))
        hint_re = re.compile(
            f"{_ID_BEFORE if mode == 'yaml' else _JSON_ID_BEFORE}(?:{alt}){_ID_AFTER}"
        )
        for idx, line in enumerate(new_lines):
            m = hint_re.search(line)
            if m:
                snippet, _ = _snippet(line.rstrip("\r\n"), m.group(0))
                # le posizioni dei flow si riferiscono al testo originale: per una riga
                # non modificata coincidono, per una modificata l'errore e' di pochi caratteri
                leftovers.append(
                    {
                        "line": idx + 1,
                        "text": snippet,
                        "label": label(idx, m.start()),
                        "token": m.group(0),
                    }
                )
    return ScanResult(new_text, hits, leftovers)


# --------------------------------------------------------------------------- #
# Scansione della cartella di configurazione di Home Assistant
# --------------------------------------------------------------------------- #
def file_role(rel: str) -> str:
    if rel.startswith(".storage/"):
        return "dashboard"
    if rel == "automations.yaml":
        return "automation"
    if rel == "scripts.yaml":
        return "script"
    if rel == "scenes.yaml":
        return "scene"
    if rel == "configuration.yaml":
        return "config"
    if rel.startswith("blueprints/"):
        return "blueprint"
    if rel.startswith("packages/"):
        return "package"
    return "other"


_ROLE_ORDER = {
    "automation": 0,
    "script": 1,
    "scene": 2,
    "blueprint": 3,
    "package": 4,
    "config": 5,
    "other": 6,
    "dashboard": 7,
    "nodered": 0,
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class FileChange:
    rel: str
    role: str
    old_sha: str
    new_text: str
    hits: list[Hit]

    @property
    def line_revert_ok(self) -> bool:
        return not any(h.truncated for h in self.hits)

    def to_dict(self) -> dict:
        return {
            "path": self.rel,
            "role": self.role,
            "sha_before": self.old_sha,
            "hits": [h.to_dict() for h in self.hits],
            "line_revert_ok": self.line_revert_ok,
        }


@dataclass
class DirScan:
    files: list[FileChange] = field(default_factory=list)
    leftovers: list[dict] = field(default_factory=list)  # con chiave "path"
    skipped: list[dict] = field(default_factory=list)
    scanned: int = 0


def iter_candidate_files(config_dir: Path, include_dashboards: bool):
    """Genera (percorso assoluto, percorso relativo con '/') dei file da controllare."""
    for root, dirs, files in os.walk(config_dir, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS)
        for name in sorted(files):
            path = Path(root) / name
            if name in SKIP_FILES or path.suffix.lower() not in SCAN_SUFFIXES:
                continue
            if path.is_symlink():
                continue
            yield path, path.relative_to(config_dir).as_posix()
    if include_dashboards:
        storage = config_dir / ".storage"
        if storage.is_dir():
            for path in sorted(storage.iterdir()):
                if path.is_file() and not path.is_symlink() and (
                    path.name == "lovelace" or path.name.startswith("lovelace.")
                ):
                    yield path, f".storage/{path.name}"


def _read_text(path: Path, rel: str, limit: int, result: DirScan) -> tuple[bytes, str] | None:
    try:
        if path.stat().st_size > limit:
            result.skipped.append({"path": rel, "reason": "file troppo grande"})
            return None
        data = path.read_bytes()
    except OSError as err:
        result.skipped.append({"path": rel, "reason": f"non leggibile: {err}"})
        return None
    try:
        return data, data.decode("utf-8")
    except UnicodeDecodeError:
        result.skipped.append({"path": rel, "reason": "non e' testo UTF-8"})
        return None


def _scan_one(
    result: DirScan,
    rel: str,
    role: str,
    data: bytes,
    text: str,
    mappings: list[Mapping],
    hints: list[str] | None,
    mode: str,
    validate_json: bool,
) -> None:
    scan = scan_text(text, mappings, hints, mode)
    for item in scan.leftovers:
        result.leftovers.append({"path": rel, **item})
    if not scan.hits:
        return
    if validate_json:
        try:
            json.loads(scan.new_text)
        except ValueError as err:
            result.skipped.append({"path": rel, "reason": f"il risultato non sarebbe JSON valido: {err}"})
            return
    result.files.append(FileChange(rel, role, sha256_bytes(data), scan.new_text, scan.hits))


def scan_config_dir(
    config_dir: Path,
    mappings: list[Mapping],
    hints: list[str] | None = None,
    include_dashboards: bool = False,
) -> DirScan:
    result = DirScan()
    keys = [m.old for m in mappings] + [h for h in (hints or [])]
    for path, rel in iter_candidate_files(config_dir, include_dashboards):
        result.scanned += 1
        loaded = _read_text(path, rel, MAX_FILE_BYTES, result)
        if loaded is None:
            continue
        data, text = loaded
        lowered = text.lower()
        if not any(k in lowered for k in keys):
            continue
        is_json = rel.startswith(".storage/")
        _scan_one(
            result, rel, file_role(rel), data, text, mappings, hints,
            "json" if is_json else "yaml", is_json,
        )
    result.files.sort(key=lambda f: (_ROLE_ORDER.get(f.role, 9), f.rel))
    return result


# --------------------------------------------------------------------------- #
# Node-RED
# --------------------------------------------------------------------------- #
def nodered_flow_files(root: Path) -> list[Path]:
    """File dei flow nella cartella di Node-RED: JSON che sono elenchi di nodi."""
    found: list[Path] = []
    if not root.is_dir():
        return found
    for path in sorted(root.glob("*.json")):
        name = path.name
        if name.startswith(".") or name.endswith("_cred.json") or name.startswith("package"):
            continue
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FLOW_BYTES:
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (
            isinstance(data, list)
            and data
            and all(isinstance(n, dict) and "id" in n and "type" in n for n in data)
        ):
            found.append(path)
    return found


def scan_nodered_dir(root: Path, mappings: list[Mapping], hints: list[str] | None = None) -> DirScan:
    result = DirScan()
    keys = [m.old for m in mappings] + [h for h in (hints or [])]
    # i servizi possono comparire divisi (domain + service): cerco anche il solo nome
    keys += [m.old.split(".", 1)[1] for m in mappings if m.kind == "service"]
    for path in nodered_flow_files(root):
        rel = path.name
        result.scanned += 1
        loaded = _read_text(path, rel, MAX_FLOW_BYTES, result)
        if loaded is None:
            continue
        data, text = loaded
        lowered = text.lower()
        if not any(k in lowered for k in keys):
            continue
        _scan_one(result, rel, "nodered", data, text, mappings, hints, "flows", True)
    result.files.sort(key=lambda f: f.rel)
    return result


def plan_token(mappings: list[Mapping], files: list[FileChange]) -> str:
    payload = {
        "m": sorted([m.kind, m.old, m.new] for m in mappings),
        "f": [[f.rel, f.old_sha] for f in sorted(files, key=lambda f: f.rel)],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:24]
