/* Swap Wizard – pannello per Home Assistant (nessuna dipendenza esterna). */

const ROLE = {
  automation: "Automazioni (editor grafico)",
  script: "Script",
  scene: "Scene",
  blueprint: "Blueprint",
  package: "Package",
  config: "configuration.yaml",
  other: "Altro file YAML",
  dashboard: "Dashboard (serve riavvio)",
  nodered: "Flow di Node-RED",
};
const DEFAULT_ADDON = "a0d7b954_nodered";
const KIND = { device: "Dispositivo", service: "Servizio notifica", entity: "Entità" };
const CONF = { high: "sicuro", medium: "probabile", low: "da verificare" };
const STATUS = {
  applied: ["Applicata", "ok"],
  rolled_back: ["Annullata", "muted"],
  failed: ["Fallita", "err"],
  applying: ["Interrotta", "warn"],
};
const ACTION = {
  restored_full: "ripristinato dal backup",
  restored_lines: "ripristinato riga per riga",
  restored_full_forced: "ripristinato dal backup (forzato)",
  already_original: "già com'era",
  conflict: "conflitto",
};

const esc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const reEsc = (v) => v.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const fmtDate = (iso) => {
  try {
    return new Date(iso).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" });
  } catch (e) {
    return iso || "";
  }
};
const hl = (line, tokens, cls) => {
  const safe = esc(line);
  const list = [...new Set(tokens.filter(Boolean))].sort((a, b) => b.length - a.length);
  if (!list.length) return safe;
  return safe.replace(new RegExp(list.map((t) => reEsc(esc(t))).join("|"), "gi"), (m) => `<mark class="${cls}">${m}</mark>`);
};

const CSS = `
:host { display:block; height:100%; background:var(--primary-background-color); color:var(--primary-text-color);
  font-family:var(--paper-font-body1_-_font-family, Roboto, sans-serif); }
* { box-sizing:border-box; }
.toolbar { display:flex; align-items:center; gap:8px; height:56px; padding:0 12px; background:var(--app-header-background-color, var(--primary-color));
  color:var(--app-header-text-color, #fff); font-size:20px; position:sticky; top:0; z-index:5; }
.toolbar .title { flex:1; }
.tabs { display:flex; gap:4px; }
.tab { background:transparent; border:0; color:inherit; opacity:.75; font-size:14px; padding:8px 12px; cursor:pointer; border-bottom:3px solid transparent; }
.tab.on { opacity:1; border-bottom-color:currentColor; font-weight:500; }
.wrap { max-width:960px; margin:0 auto; padding:16px; }
.card { background:var(--card-background-color); border-radius:12px; padding:16px; margin-bottom:16px;
  box-shadow:var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.2)); }
h2 { margin:0 0 4px; font-size:20px; font-weight:500; }
h3 { margin:16px 0 8px; font-size:15px; font-weight:500; }
.sub { color:var(--secondary-text-color); font-size:14px; margin:0 0 12px; line-height:1.4; }
.steps { display:flex; align-items:center; gap:0; margin:4px 0 18px; }
.step { display:flex; align-items:center; gap:8px; color:var(--secondary-text-color); font-size:13px; }
.step .n { width:26px; height:26px; border-radius:50%; display:grid; place-items:center; border:2px solid var(--divider-color); font-weight:500; }
.step.on { color:var(--primary-text-color); font-weight:500; }
.step.on .n { background:var(--primary-color); border-color:var(--primary-color); color:#fff; }
.step.done .n { background:var(--success-color,#43a047); border-color:var(--success-color,#43a047); color:#fff; }
.bar { flex:1; height:2px; background:var(--divider-color); margin:0 8px; min-width:12px; }
.modes { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; }
.mode { text-align:left; background:var(--secondary-background-color); border:2px solid transparent; border-radius:12px; padding:14px; cursor:pointer; color:inherit; font:inherit; }
.mode.on { border-color:var(--primary-color); }
.mode ha-icon { --mdc-icon-size:28px; color:var(--primary-color); }
.mode b { display:block; margin:6px 0 4px; font-size:15px; }
.mode span { font-size:13px; color:var(--secondary-text-color); line-height:1.35; }
.grid2 { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
@media (max-width:640px){ .grid2 { grid-template-columns:1fr; } }
label.f { display:block; font-size:13px; color:var(--secondary-text-color); margin-bottom:4px; }
select, input[type=text] { width:100%; padding:10px; border-radius:8px; border:1px solid var(--divider-color);
  background:var(--card-background-color); color:var(--primary-text-color); font:inherit; }
.sg { position:relative; }
.sugg { position:absolute; left:0; right:0; top:100%; z-index:20; margin:2px 0 0; padding:4px 0; list-style:none; max-height:260px; overflow:auto;
  background:var(--card-background-color); border:1px solid var(--divider-color); border-radius:8px; box-shadow:0 4px 16px rgba(0,0,0,.25); }
.sugg[hidden] { display:none; }
.sugg li { padding:6px 10px; cursor:pointer; font-size:13px; display:flex; flex-direction:column; }
.sugg li:hover, .sugg li.on { background:var(--secondary-background-color); }
.sugg li small { color:var(--secondary-text-color); font-size:11px; }
.sugg li.none { cursor:default; color:var(--secondary-text-color); }
.hint { font-size:12px; color:var(--secondary-text-color); margin-top:4px; }
.row { display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin-top:16px; }
.spacer { flex:1; }
button.b { border:0; border-radius:20px; padding:10px 20px; font:inherit; font-weight:500; cursor:pointer;
  background:var(--primary-color); color:var(--text-primary-color,#fff); }
button.b.sec { background:transparent; color:var(--primary-color); border:1px solid var(--divider-color); }
button.b.danger { background:var(--error-color,#db4437); }
button.b:disabled { opacity:.5; cursor:default; }
.alert { border-radius:8px; padding:10px 12px; margin:10px 0; font-size:14px; line-height:1.4; }
.alert.warn { background:color-mix(in srgb, var(--warning-color,#ffa600) 18%, transparent); border-left:4px solid var(--warning-color,#ffa600); }
.alert.err { background:color-mix(in srgb, var(--error-color,#db4437) 15%, transparent); border-left:4px solid var(--error-color,#db4437); }
.alert.ok { background:color-mix(in srgb, var(--success-color,#43a047) 15%, transparent); border-left:4px solid var(--success-color,#43a047); }
.alert.info { background:var(--secondary-background-color); border-left:4px solid var(--primary-color); }
table { width:100%; border-collapse:collapse; font-size:14px; }
th { text-align:left; font-weight:500; color:var(--secondary-text-color); font-size:12px; padding:6px 8px; }
td { padding:6px 8px; border-top:1px solid var(--divider-color); vertical-align:middle; }
td input[type=text] { padding:6px 8px; font-family:monospace; font-size:13px; }
.mono { font-family:monospace; font-size:13px; word-break:break-all; }
.chip { display:inline-block; font-size:11px; border-radius:10px; padding:2px 8px; background:var(--secondary-background-color); color:var(--secondary-text-color); white-space:nowrap; }
.chip.ok { background:color-mix(in srgb, var(--success-color,#43a047) 20%, transparent); color:var(--success-color,#2e7d32); }
.chip.warn { background:color-mix(in srgb, var(--warning-color,#ffa600) 25%, transparent); }
.chip.err { background:color-mix(in srgb, var(--error-color,#db4437) 20%, transparent); color:var(--error-color,#c62828); }
.chip.muted { opacity:.8; }
details.file { border:1px solid var(--divider-color); border-radius:10px; margin:8px 0; }
details.file > summary { list-style:none; cursor:pointer; padding:10px 12px; display:flex; gap:10px; align-items:center; }
details.file > summary::-webkit-details-marker { display:none; }
.hit { border-top:1px solid var(--divider-color); padding:8px 12px; font-size:13px; }
.hit .meta { color:var(--secondary-text-color); margin-bottom:4px; display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
.ln { font-family:monospace; font-size:12px; white-space:pre-wrap; word-break:break-all; padding:2px 6px; border-radius:4px; }
.ln.b { background:color-mix(in srgb, var(--error-color,#db4437) 10%, transparent); }
.ln.a { background:color-mix(in srgb, var(--success-color,#43a047) 12%, transparent); margin-top:2px; }
mark.del { background:color-mix(in srgb, var(--error-color,#db4437) 35%, transparent); color:inherit; }
mark.add { background:color-mix(in srgb, var(--success-color,#43a047) 40%, transparent); color:inherit; }
.radio { display:flex; gap:10px; align-items:flex-start; padding:10px; border:2px solid var(--divider-color); border-radius:10px; margin:8px 0; cursor:pointer; }
.radio.on { border-color:var(--primary-color); }
.radio input { margin-top:3px; }
.cb { display:flex; gap:8px; align-items:flex-start; margin:8px 0; font-size:14px; }
.overlay { position:fixed; inset:0; background:rgba(0,0,0,.5); display:grid; place-items:center; z-index:20; padding:16px; }
.dialog { background:var(--card-background-color); border-radius:14px; padding:20px; max-width:480px; width:100%; }
.spin { display:inline-block; width:16px; height:16px; border:2px solid currentColor; border-right-color:transparent; border-radius:50%; animation:sp 0.8s linear infinite; vertical-align:-3px; margin-right:6px; }
@keyframes sp { to { transform:rotate(360deg); } }
ul.plain { margin:6px 0; padding-left:20px; } ul.plain li { margin:3px 0; }
`;

class SwapWizardPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._s = this._initial();
    this.shadowRoot.addEventListener("click", (e) => {
      const el = e.target.closest("[data-action]");
      if (el && !el.disabled) this._act(el.dataset.action, el.dataset);
    });
    const onField = (e) => {
      const el = e.target.closest("[data-bind],[data-map]");
      if (el) this._bind(el, e.type === "change");
    };
    this.shadowRoot.addEventListener("input", onField);
    this.shadowRoot.addEventListener("change", onField);
    this.shadowRoot.addEventListener("input", (e) => this._suggest(e.target));
    this.shadowRoot.addEventListener("focusin", (e) => this._suggest(e.target));
    this.shadowRoot.addEventListener("focusout", (e) => { const u = e.target.closest?.(".sg")?.querySelector(".sugg"); if (u) u.hidden = true; });
    this.shadowRoot.addEventListener("mousedown", (e) => {
      const li = e.target.closest?.(".sugg li[data-v]");
      if (!li) return;
      e.preventDefault();
      const box = li.closest(".sg"), inp = box.querySelector("input");
      inp.value = li.dataset.v;
      box.querySelector(".sugg").hidden = true;
      this._bind(inp, true);
    });
  }

  _suggest(el) {
    if (!el || !el.dataset || el.dataset.suggest === undefined) return;
    const ul = el.closest(".sg")?.querySelector(".sugg");
    if (!ul) return;
    const q = el.value.trim().toLowerCase();
    const st = this._hass?.states || {};
    const out = [];
    for (const id of Object.keys(st).sort()) {
      const name = st[id]?.attributes?.friendly_name || "";
      if (!q || id.toLowerCase().includes(q) || name.toLowerCase().includes(q)) {
        out.push(`<li data-v="${esc(id)}">${esc(id)}${name ? `<small>${esc(name)}</small>` : ""}</li>`);
        if (out.length >= 40) break;
      }
    }
    ul.innerHTML = out.length ? out.join("") : `<li class="none">Nessuna entità trovata: puoi scriverla a mano</li>`;
    ul.hidden = false;
  }

  _initial() {
    return {
      tab: "wizard", step: 1, mode: "phone", devices: null,
      branch: "ha", noderedPath: "", noderedAddon: DEFAULT_ADDON, restartNodered: false, detect: null, detailBranch: "ha", forcedShown: false,
      oldDev: "", newDev: "", oldEnt: "", newEnt: "",
      mappings: [], hints: [], warnings: [], unpairedOld: [], unpairedNew: [],
      includeDash: false, manual: { kind: "entity", old: "", new: "" },
      preview: null, sent: null, selected: new Set(), backup: true, note: "", title: "",
      confirm: null, busy: "", error: "", result: null,
      history: null, detail: null, force: false, rbResult: null,
    };
  }

  set hass(h) {
    const first = !this._hass;
    this._hass = h;
    if (first) this._start();
  }
  set narrow(v) { this._narrow = v; this._toolbarSync(); }
  set panel(v) { this._panel = v; }

  async _start() {
    this._render();
    try {
      this._s.devices = await this._ws({ type: "swap_wizard/devices" });
    } catch (e) {
      this._s.error = this._msg(e);
    }
    this._render();
  }

  _toolbarSync() {
    const m = this.shadowRoot.querySelector("ha-menu-button");
    if (m) { m.hass = this._hass; m.narrow = this._narrow; }
  }

  _ws(msg) { return this._hass.callWS(msg); }
  _msg(e) { return (e && (e.message || e.error || e.code)) || String(e); }

  // ------------------------------------------------------------------ azioni
  async _run(label, fn) {
    this._s.busy = label; this._s.error = ""; this._render();
    try { await fn(); } catch (e) { this._s.error = this._msg(e); }
    this._s.busy = ""; this._render();
  }

  _act(a, d) {
    const s = this._s;
    switch (a) {
      case "tab": s.tab = d.v; s.error = ""; if (d.v === "history") this._loadHistory(); this._render(); break;
      case "mode": s.mode = d.v; s.error = ""; this._render(); break;
      case "branch": s.branch = d.v; s.error = ""; if (d.v === "nodered" && !s.detect) this._detect(); this._render(); break;
      case "restart": Object.assign(s, this._initial(), { devices: s.devices, branch: s.branch, noderedPath: s.noderedPath, noderedAddon: s.noderedAddon, detect: s.detect }); this._render(); break;
      case "back": s.error = ""; s.step = Math.max(1, s.step - 1); this._render(); break;
      case "propose": this._propose(); break;
      case "addrow": this._addRow(); break;
      case "delrow": s.mappings.splice(+d.i, 1); this._render(); break;
      case "preview": this._preview(); break;
      case "askapply": s.confirm = { type: "apply" }; this._render(); break;
      case "cancelconfirm": s.confirm = null; this._render(); break;
      case "apply": this._apply(); break;
      case "detail": this._openDetail(d.id, d.branch); break;
      case "closedetail": s.detail = null; s.rbResult = null; this._render(); break;
      case "askrollback": s.confirm = { type: "rollback", id: d.id, branch: d.branch || "ha" }; this._render(); break;
      case "rollback": this._rollback(d.id, d.branch || "ha"); break;
      case "gohistory": s.tab = "history"; this._loadHistory(); this._render(); break;
      default: break;
    }
  }

  _bind(el, isChange) {
    const s = this._s;
    if (el.dataset.map !== undefined) {
      const m = s.mappings[+el.dataset.map];
      if (!m) return;
      if (el.dataset.field === "on") { m.on = el.checked; } else { m[el.dataset.field] = el.value.trim(); }
      return;
    }
    const k = el.dataset.bind;
    let v = el.type === "checkbox" ? el.checked : el.value;
    if (el.type === "radio") { if (!el.checked) return; v = el.value === "true"; }
    if (k.startsWith("manual.")) { s.manual[k.slice(7)] = v; }
    else if (k === "file") {
      if (v) s.selected.add(el.dataset.path); else s.selected.delete(el.dataset.path);
      const forced = this._forced();
      if (forced !== s.forcedShown) { s.forcedShown = forced; if (forced) s.backup = true; this._render(); return; }
      this._updateApplyButton();
      return;
    } else if (k === "force") { s.force = v; return; }
    else { s[k] = v; }
    if (isChange && el.dataset.rerender) this._render();
  }

  _forced() {
    const pv = this._s.preview;
    return !!pv && pv.files.some((f) => !f.line_revert_ok && this._s.selected.has(f.path));
  }

  async _detect() {
    const s = this._s;
    try {
      const r = await this._ws({ type: "swap_wizard/nodered_detect" });
      s.detect = r;
      if (!s.noderedPath) s.noderedPath = r.settings.nodered_path || (r.candidates.find((c) => c.allowed) || {}).path || "";
      s.noderedAddon = r.settings.nodered_addon || DEFAULT_ADDON;
    } catch (e) { s.error = this._msg(e); s.detect = { candidates: [], settings: {} }; }
    this._render();
  }

  _updateApplyButton() {
    const b = this.shadowRoot.querySelector("[data-action=askapply]");
    if (b) b.disabled = this._s.selected.size === 0;
    const c = this.shadowRoot.querySelector("#selcount");
    if (c) c.textContent = String(this._s.selected.size);
  }

  _addRow() {
    const s = this._s, m = s.manual;
    if (!m.old || !m.new) { s.error = "Per aggiungere una riga compila sia il valore vecchio sia quello nuovo."; this._render(); return; }
    s.error = "";
    s.mappings.push({ kind: m.kind, old: m.old.trim(), new: m.new.trim(), note: "manuale", confidence: "high", on: true });
    s.manual = { kind: m.kind, old: "", new: "" };
    this._render();
  }

  async _propose() {
    const s = this._s;
    await this._run("Preparo le sostituzioni…", async () => {
      let p;
      if (s.mode === "entity") {
        if (!s.oldEnt || !s.newEnt) throw new Error("Indica sia l'entità vecchia sia quella nuova.");
        p = await this._ws({ type: "swap_wizard/propose_entity", old: s.oldEnt, new: s.newEnt });
        s.title = `Sostituzione entità: ${s.oldEnt} → ${s.newEnt}`;
      } else {
        if (!s.oldDev || !s.newDev) throw new Error("Scegli sia il vecchio sia il nuovo dispositivo.");
        p = await this._ws({ type: "swap_wizard/propose_device", old_device_id: s.oldDev, new_device_id: s.newDev });
        s.title = `${s.mode === "phone" ? "Cambio telefono" : "Sostituzione dispositivo"}: ${p.old.name} → ${p.new.name}`;
      }
      s.mappings = p.mappings.map((m) => ({ ...m, on: true }));
      s.hints = p.hints || [];
      s.warnings = p.warnings || [];
      s.unpairedOld = p.unpaired_old || [];
      s.unpairedNew = p.unpaired_new || [];
      s.step = 2;
    });
  }

  _active() {
    return this._s.mappings.filter((m) => m.on).map((m) => ({ kind: m.kind, old: m.old, new: m.new, note: m.note || "" }));
  }

  async _preview() {
    const s = this._s;
    const mappings = this._active();
    if (!mappings.length) { s.error = "Seleziona almeno una sostituzione."; this._render(); return; }
    await this._run("Cerco nei file di configurazione…", async () => {
      const pv = await this._ws({ type: "swap_wizard/preview", mappings, hints: s.hints, include_dashboards: s.includeDash, branch: s.branch, nodered_path: s.noderedPath });
      s.preview = pv; s.sent = mappings;
      s.selected = new Set(pv.files.map((f) => f.path));
      s.forcedShown = this._forced();
      if (s.forcedShown) s.backup = true;
      s.step = 3;
    });
  }

  async _apply() {
    const s = this._s;
    s.confirm = null;
    await this._run(s.backup ? "Backup e modifica in corso…" : "Modifica in corso…", async () => {
      s.result = await this._ws({
        type: "swap_wizard/apply", mappings: s.sent, hints: s.hints, include_dashboards: s.includeDash,
        token: s.preview.token, files: [...s.selected], backup: s.backup, title: s.title, note: s.note,
        branch: s.branch, nodered_path: s.noderedPath, restart_nodered: s.restartNodered, nodered_addon: s.noderedAddon,
      });
      s.step = 4;
    });
  }

  async _loadHistory() {
    try { this._s.history = await this._ws({ type: "swap_wizard/history" }); } catch (e) { this._s.error = this._msg(e); }
    this._render();
  }

  async _openDetail(id, branch) {
    await this._run("Carico i dettagli…", async () => {
      this._s.detailBranch = branch || "ha";
      this._s.detail = await this._ws({ type: "swap_wizard/operation", operation_id: id, branch: this._s.detailBranch });
      this._s.rbResult = null; this._s.force = false;
    });
  }

  async _rollback(id, branch) {
    const s = this._s;
    s.confirm = null;
    await this._run("Ripristino in corso…", async () => {
      const r = await this._ws({ type: "swap_wizard/rollback", operation_id: id, force: s.force, branch, restart_nodered: branch === "nodered" && s.restartNodered, nodered_addon: s.noderedAddon });
      s.detailBranch = branch;
      s.detail = await this._ws({ type: "swap_wizard/operation", operation_id: id, branch });
      s.history = await this._ws({ type: "swap_wizard/history" });
      s.rbResult = r;
      s.tab = "history";
    });
  }

  // ---------------------------------------------------------------- disegno
  _render() {
    const root = this.shadowRoot;
    const prev = root.querySelector(".scroller");
    const top = prev ? prev.scrollTop : 0;
    const s = this._s;
    root.innerHTML = `<style>${CSS}</style>
      <div class="scroller" style="height:100%;overflow:auto">
        <div class="toolbar">
          <ha-menu-button></ha-menu-button>
          <div class="title">Swap Wizard</div>
          <div class="tabs">
            <button class="tab ${s.tab === "wizard" ? "on" : ""}" data-action="tab" data-v="wizard">Sostituzione guidata</button>
            <button class="tab ${s.tab === "history" ? "on" : ""}" data-action="tab" data-v="history">Cronologia e rollback</button>
          </div>
        </div>
        <div class="wrap">
          ${s.busy ? `<div class="alert info"><span class="spin"></span>${esc(s.busy)}</div>` : ""}
          ${s.error ? `<div class="alert err">${esc(s.error)}</div>` : ""}
          ${s.tab === "wizard" ? this._wizard() : this._history()}
        </div>
        ${this._confirmDialog()}
      </div>`;
    this._toolbarSync();
    const sc = root.querySelector(".scroller");
    if (sc) sc.scrollTop = top;
  }

  _stepper() {
    const names = ["Cosa sostituire", "Controlla", "Anteprima e backup", "Fatto"];
    return `<div class="steps">${names
      .map((n, i) => {
        const k = i + 1, cls = k === this._s.step ? "on" : k < this._s.step ? "done" : "";
        return `${i ? '<div class="bar"></div>' : ""}<div class="step ${cls}"><div class="n">${k < this._s.step ? "✓" : k}</div><span>${n}</span></div>`;
      })
      .join("")}</div>`;
  }

  _wizard() {
    const s = this._s;
    return `<div class="card">${this._stepper()}${[this._step1, this._step2, this._step3, this._step4][s.step - 1].call(this)}</div>`;
  }

  // ---- passo 1
  _step1() {
    const s = this._s, busy = !!s.busy;
    const modes = [
      ["phone", "mdi:cellphone-sync", "Ho cambiato telefono", "Sostituisce i servizi di notifica, le azioni «dispositivo» e i sensori del telefono."],
      ["device", "mdi:swap-horizontal", "Sostituisco un dispositivo", "Un sensore, una presa, una luce guasti: le entità vengono abbinate in automatico."],
      ["entity", "mdi:target", "Sostituisco una sola entità", "Scegli l'entità vecchia e quella nuova, niente altro."],
    ];
    let form = "";
    if (s.devices === null) {
      form = `<p class="sub"><span class="spin"></span>Leggo i dispositivi…</p>`;
    } else if (s.mode === "entity") {
      form = `
        <div class="grid2">
          <div><label class="f">Entità vecchia (guasta o da sostituire)</label>
            <div class="sg"><input type="text" data-suggest data-bind="oldEnt" value="${esc(s.oldEnt)}" placeholder="Scrivi o scegli: sensor.sensore_guasto" autocomplete="off"/><ul class="sugg" hidden></ul></div>
            <div class="hint">Puoi anche scriverla a mano se non esiste più.</div></div>
          <div><label class="f">Entità nuova</label>
            <div class="sg"><input type="text" data-suggest data-bind="newEnt" value="${esc(s.newEnt)}" placeholder="Scrivi o scegli: sensor.sensore_nuovo" autocomplete="off"/><ul class="sugg" hidden></ul></div></div>
        </div>`;
    } else {
      const list = s.devices.filter((d) => (s.mode === "phone" ? d.mobile : true));
      const opt = (sel) =>
        `<option value="">— scegli —</option>` +
        list.map((d) => `<option value="${esc(d.id)}" ${d.id === sel ? "selected" : ""}>${esc(d.name)}${d.model ? " · " + esc(d.model) : ""}${d.disabled ? " (disabilitato)" : ""}</option>`).join("");
      const info = (id) => { const d = list.find((x) => x.id === id); return d && d.notify ? `Servizio notifica: <span class="mono">${esc(d.notify)}</span>` : ""; };
      form = `<div class="grid2">
          <div><label class="f">${s.mode === "phone" ? "Vecchio telefono" : "Dispositivo vecchio"}</label>
            <select data-bind="oldDev" data-rerender="1">${opt(s.oldDev)}</select><div class="hint">${info(s.oldDev)}</div></div>
          <div><label class="f">${s.mode === "phone" ? "Nuovo telefono" : "Dispositivo nuovo"}</label>
            <select data-bind="newDev" data-rerender="1">${opt(s.newDev)}</select><div class="hint">${info(s.newDev)}</div></div>
        </div>
        ${s.mode === "phone" && !list.length ? `<div class="alert warn">Nessun telefono con l'app Home Assistant trovato.</div>` : ""}
        ${s.mode === "phone" ? `<p class="hint">Il nuovo telefono deve già avere l'app Home Assistant installata e collegata, altrimenti non compare nell'elenco.</p>` : ""}`;
    }
    const branches = [
      ["ha", "mdi:home-assistant", "Home Assistant", "Automazioni, script, scene, blueprint e (se vuoi) dashboard."],
      ["nodered", "mdi:sitemap", "Node-RED", "I flow di Node-RED (flows.json): servizi di notifica, dispositivi ed entità dentro i nodi."],
    ];
    return `<h2>Dove vuoi sostituire?</h2>
      <p class="sub">Prima di modificare qualsiasi file ti mostro l'elenco e ti chiedo se vuoi il backup. Ogni modifica viene registrata e si può annullare.</p>
      <div class="modes">${branches
        .map(([k, ic, tt, d]) => `<button class="mode ${s.branch === k ? "on" : ""}" data-action="branch" data-v="${k}"><ha-icon icon="${ic}"></ha-icon><b>${tt}</b><span>${d}</span></button>`)
        .join("")}</div>
      <h3>Cosa vuoi sostituire?</h3>
      <div class="modes">${modes
        .map(([k, ic, t, d]) => `<button class="mode ${s.mode === k ? "on" : ""}" data-action="mode" data-v="${k}"><ha-icon icon="${ic}"></ha-icon><b>${t}</b><span>${d}</span></button>`)
        .join("")}</div>
      <h3>${s.mode === "entity" ? "Quali entità?" : "Quali dispositivi?"}</h3>
      ${form}
      <div class="row"><div class="spacer"></div><button class="b" data-action="propose" ${busy ? "disabled" : ""}>Avanti</button></div>`;
  }

  // ---- passo 2
  _step2() {
    const s = this._s;
    const rows = s.mappings.map((m, i) => {
      const long = m.kind === "device";
      return `<tr>
        <td><input type="checkbox" data-map="${i}" data-field="on" ${m.on ? "checked" : ""}/></td>
        <td><span class="chip">${KIND[m.kind] || m.kind}</span></td>
        <td class="mono" title="${esc(m.old)}">${long ? esc(m.note || m.old.slice(0, 8) + "…") : esc(m.old)}</td>
        <td><input type="text" data-map="${i}" data-field="new" value="${esc(m.new)}" ${long ? "readonly" : ""} title="${esc(m.new)}"/></td>
        <td>${m.confidence ? `<span class="chip ${m.confidence === "high" ? "ok" : "warn"}">${CONF[m.confidence] || ""}</span>` : ""}</td>
        <td>${m.note === "manuale" ? `<button class="b sec" style="padding:4px 10px" data-action="delrow" data-i="${i}">✕</button>` : ""}</td>
      </tr>`;
    }).join("");
    return `<h2>Controlla cosa verrà sostituito</h2>
      <p class="sub">Questi identificatori vecchi saranno cambiati con i nuovi in tutte le automazioni, script e scene. Togli la spunta a ciò che non vuoi toccare; le righe «da verificare» sono abbinamenti incerti.</p>
      ${s.warnings.map((w) => `<div class="alert warn">${esc(w)}</div>`).join("")}
      <table><thead><tr><th></th><th>Tipo</th><th>Vecchio</th><th>Nuovo</th><th>Abbinamento</th><th></th></tr></thead><tbody>${rows}</tbody></table>
      ${s.unpairedOld.length ? `<details style="margin-top:10px"><summary class="hint" style="cursor:pointer">Entità del vecchio dispositivo senza corrispondente (${s.unpairedOld.length})</summary>
        <ul class="plain mono">${s.unpairedOld.map((e) => `<li>${esc(e)}</li>`).join("")}</ul></details>` : ""}
      <h3>Aggiungi una sostituzione a mano</h3>
      <div class="grid2" style="grid-template-columns:140px 1fr 1fr auto;align-items:end">
        <div><label class="f">Tipo</label><select data-bind="manual.kind" data-rerender="0">
          ${Object.entries(KIND).map(([k, v]) => `<option value="${k}" ${s.manual.kind === k ? "selected" : ""}>${v}</option>`).join("")}</select></div>
        <div><label class="f">Vecchio</label><div class="sg"><input type="text" ${s.manual.kind === "entity" ? "data-suggest" : ""} data-bind="manual.old" value="${esc(s.manual.old)}" placeholder="sensor.vecchio" autocomplete="off"/><ul class="sugg" hidden></ul></div></div>
        <div><label class="f">Nuovo</label><div class="sg"><input type="text" ${s.manual.kind === "entity" ? "data-suggest" : ""} data-bind="manual.new" value="${esc(s.manual.new)}" placeholder="sensor.nuovo" autocomplete="off"/><ul class="sugg" hidden></ul></div></div>
        <button class="b sec" data-action="addrow">Aggiungi</button>
      </div>
      ${s.branch === "nodered" ? this._noderedFolder() : `<div class="cb"><input type="checkbox" id="dash" data-bind="includeDash" ${s.includeDash ? "checked" : ""}/><label for="dash">Cerca anche nelle dashboard salvate dall'interfaccia (richiede un riavvio di Home Assistant)</label></div>`}
      <div class="row"><button class="b sec" data-action="back">Indietro</button><div class="spacer"></div>
        <button class="b" data-action="preview" ${s.busy ? "disabled" : ""}>Cerca nei file</button></div>`;
  }

  _noderedFolder() {
    const s = this._s, cands = (s.detect && s.detect.candidates) || [];
    return `<h3>Cartella di Node-RED</h3>
      <datalist id="nrdirs">${cands.map((c) => `<option value="${esc(c.path)}"></option>`).join("")}</datalist>
      <input type="text" list="nrdirs" data-bind="noderedPath" value="${esc(s.noderedPath)}" placeholder="/config/node-red" autocomplete="off"/>
      <div class="hint">La cartella che contiene <span class="mono">flows.json</span>, vista da Home Assistant.</div>
      ${s.detect === null ? `<div class="hint"><span class="spin"></span>Cerco Node-RED…</div>` : ""}
      ${s.detect && !cands.length ? `<div class="alert warn">Non ho trovato <span class="mono">flows.json</span> nelle posizioni abituali. Scrivi il percorso a mano; se Node-RED gira su un altro dispositivo, Home Assistant non può modificarlo da qui.</div>` : ""}
      ${cands.filter((c) => !c.allowed).map((c) => `<div class="alert warn"><span class="mono">${esc(c.path)}</span> è fuori dalle cartelle consentite a Home Assistant: aggiungila a <span class="mono">allowlist_external_dirs</span> in configuration.yaml e riavvia.</div>`).join("")}
      ${cands.length ? `<div class="hint">Trovate: ${cands.map((c) => `<span class="mono">${esc(c.path)}</span> (${c.files.map(esc).join(", ")})`).join(" · ")}</div>` : ""}`;
  }

  // ---- passo 3
  _hit(h) {
    const olds = h.pairs.map((p) => p[0]), news = h.pairs.map((p) => p[1]);
    return `<div class="hit"><div class="meta"><span>riga ${h.line}</span>${h.label ? `<span class="chip">${esc(h.label)}</span>` : ""}</div>
      <div class="ln b">${hl(h.before, olds, "del")}</div><div class="ln a">${hl(h.after, news, "add")}</div></div>`;
  }

  _fileCard(f, selectable) {
    const s = this._s;
    return `<details class="file"><summary>
        ${selectable ? `<input type="checkbox" data-bind="file" data-path="${esc(f.path)}" ${s.selected.has(f.path) ? "checked" : ""} onclick="event.stopPropagation()"/>` : ""}
        <span class="mono" style="flex:1">${esc(f.path)}</span>
        <span class="chip">${ROLE[f.role] || f.role}</span><span class="chip">${f.hits.length} ${f.hits.length === 1 ? "riga" : "righe"}</span>
      </summary>${f.hits.map((h) => this._hit(h)).join("")}</details>`;
  }

  _step3() {
    const s = this._s, pv = s.preview;
    if (!pv.files.length) {
      return `<h2>Nessun riferimento trovato</h2>
        <p class="sub">${pv.no_flow_files ? `In <span class="mono">${esc(pv.root)}</span> non ho trovato nessun file di flow di Node-RED: controlla la cartella.` : `Ho controllato ${pv.scanned} file e non ho trovato nulla da sostituire: non serve modificare niente.`}</p>
        ${this._leftovers()}
        <div class="row"><button class="b sec" data-action="back">Indietro</button><div class="spacer"></div><button class="b" data-action="restart">Nuova sostituzione</button></div>`;
    }
    const dash = pv.files.some((f) => f.role === "dashboard");
    return `<h2>Anteprima e conferma</h2>
      <p class="sub">Trovate <b>${pv.totals.lines}</b> righe in <b>${pv.totals.files}</b> file (controllati ${pv.scanned}). Questi sono i file che verranno modificati: apri un file per vedere ogni riga prima/dopo.</p>
      ${pv.files.map((f) => this._fileCard(f, true)).join("")}
      ${dash ? `<div class="alert warn">Le dashboard modificate si vedranno dopo un riavvio di Home Assistant. Fino ad allora non modificarle dall'editor, altrimenti verrebbero sovrascritte.</div>` : ""}
      ${this._leftovers()}
      ${pv.skipped.length ? `<details><summary class="hint" style="cursor:pointer">File ignorati (${pv.skipped.length})</summary><ul class="plain mono">${pv.skipped.map((x) => `<li>${esc(x.path)} — ${esc(x.reason)}</li>`).join("")}</ul></details>` : ""}
      <h3>Vuoi fare il backup dei file prima di modificarli?</h3>
      ${this._forced() ? `<div class="alert info">Per alcuni file selezionati (righe molto lunghe, come i flow salvati su una sola riga) il backup è obbligatorio: il solo registro riga per riga non basterebbe a ripristinarli.</div>` : ""}
      <label class="radio ${s.backup ? "on" : ""}"><input type="radio" name="bk" data-bind="backup" data-rerender="1" value="true" ${s.backup ? "checked" : ""}/>
        <span><b>Sì, crea il backup (consigliato)</b><br><span class="hint">Copia di ogni file in <span class="mono">/config/${esc(pv.backup_dir)}/</span> prima di toccarlo. Il rollback ripristina i file originali identici.</span></span></label>
      <label class="radio ${!s.backup ? "on" : ""}" ${this._forced() ? 'style="opacity:.5;pointer-events:none"' : ""}><input type="radio" name="bk" data-bind="backup" data-rerender="1" value="false" ${!s.backup ? "checked" : ""} ${this._forced() ? "disabled" : ""}/>
        <span><b>No, solo registro delle modifiche</b><br><span class="hint">Ogni riga cambiata viene comunque registrata e il rollback funziona riga per riga, ma non resta una copia dei file.</span></span></label>
      ${s.branch === "nodered" ? `<h3>Node-RED</h3>
        <div class="alert info">Node-RED legge i flow solo quando parte: finché non lo riavvii la modifica non è attiva e un «Deploy» dall'editor la sovrascriverebbe.</div>
        <div class="cb"><input type="checkbox" id="rst" data-bind="restartNodered" ${s.restartNodered ? "checked" : ""}/><label for="rst">Riavvia Node-RED dopo la modifica (serve Home Assistant OS o Supervised)</label></div>
        <label class="f">Componente aggiuntivo di Node-RED</label><input type="text" data-bind="noderedAddon" value="${esc(s.noderedAddon)}" style="max-width:320px"/>` : ""}
      <div style="margin-top:10px"><label class="f">Nota per la cronologia (facoltativa)</label><input type="text" data-bind="note" value="${esc(s.note)}" placeholder="Es. cambio telefono ottobre 2026"/></div>
      <div class="row"><button class="b sec" data-action="back">Indietro</button><div class="spacer"></div>
        <button class="b" data-action="askapply" ${s.selected.size === 0 || s.busy ? "disabled" : ""}>Applica a <span id="selcount">${s.selected.size}</span> file…</button></div>`;
  }

  _leftovers() {
    const l = this._s.preview?.leftovers || [];
    if (!l.length) return "";
    return `<div class="alert warn"><b>Da controllare a mano (${l.length}):</b> righe che usano entità del vecchio dispositivo senza corrispondente sul nuovo. Non vengono modificate.
      <ul class="plain mono" style="font-size:12px">${l.slice(0, 40).map((x) => `<li>${esc(x.path)}:${x.line} ${x.label ? "· " + esc(x.label) : ""} — ${esc(x.token)}</li>`).join("")}${l.length > 40 ? `<li>… e altre ${l.length - 40}</li>` : ""}</ul></div>`;
  }

  // ---- passo 4
  _step4() {
    const r = this._s.result;
    if (!r.ok) {
      return `<h2>Modifica annullata automaticamente</h2>
        <div class="alert err">${r.branch === "nodered" ? "Dopo la modifica il file dei flow non risultava valido:" : "Dopo la modifica Home Assistant ha segnalato un errore di configurazione:"}<br><span class="mono">${esc(r.error)}</span></div>
        <div class="alert ${r.auto_rolled_back ? "ok" : "err"}">${r.auto_rolled_back
          ? "Ho ripristinato subito i file originali: la tua configurazione è com'era prima."
          : "Il ripristino automatico non è riuscito: apri la cronologia e annulla l'operazione da lì."}</div>
        <div class="row"><button class="b sec" data-action="gohistory">Cronologia</button><div class="spacer"></div><button class="b" data-action="restart">Nuova sostituzione</button></div>`;
    }
    const rl = r.reload || {};
    return `<h2>Fatto</h2>
      <div class="alert ok">Modificate <b>${r.lines}</b> righe in <b>${r.files}</b> file. ${r.backup ? "Backup eseguito prima della modifica." : "Nessun backup: modifiche registrate, rollback riga per riga."}</div>
      ${r.config_already_invalid ? `<div class="alert warn">La configurazione conteneva già degli errori prima della modifica: non ho potuto verificare che il risultato sia valido.</div>` : ""}
      ${r.check_available === false ? `<div class="alert warn">Il controllo automatico della configurazione non è disponibile su questa versione di Home Assistant: verifica da Strumenti per sviluppatori → Controlla configurazione.</div>` : ""}
      ${(rl.done || []).length ? `<p class="sub">Ricaricato: ${rl.done.map((x) => `<span class="chip">${esc(x)}</span>`).join(" ")}</p>` : ""}
      ${(rl.errors || []).length ? `<div class="alert warn">Ricarica non riuscita: ${rl.errors.map(esc).join("; ")}. Riavvia Home Assistant per applicare tutto.</div>` : ""}
      ${rl.restart_required ? `<div class="alert warn">Per vedere le dashboard modificate riavvia Home Assistant.</div>` : ""}
      ${r.branch === "nodered" ? this._noderedResult(r.restart) : ""}
      <p class="sub">Codice operazione: <span class="mono">${esc(r.operation)}</span></p>
      <div class="row">
        <button class="b sec danger" style="color:#fff" data-action="askrollback" data-id="${esc(r.operation)}" data-branch="${esc(r.branch || "ha")}">Annulla questa modifica</button>
        <button class="b sec" data-action="gohistory">Cronologia</button><div class="spacer"></div>
        <button class="b" data-action="restart">Nuova sostituzione</button></div>`;
  }

  _noderedResult(rs) {
    if (rs && rs.done) return `<div class="alert ok">Node-RED riavviato (<span class="mono">${esc(rs.addon)}</span>): i flow modificati sono attivi.</div>`;
    if (rs && rs.requested) return `<div class="alert warn">${esc(rs.error || "Riavvio non riuscito.")} Riavvia Node-RED a mano per attivare la modifica.</div>`;
    return `<div class="alert warn">Per attivare i flow modificati riavvia Node-RED. Fino ad allora non fare «Deploy» dall'editor: sovrascriverebbe la modifica.</div>`;
  }

  // ---- cronologia
  _history() {
    const s = this._s;
    if (s.detail) return this._detail();
    if (s.history === null) return `<div class="card"><span class="spin"></span>Carico la cronologia…</div>`;
    if (!s.history.length) return `<div class="card"><h2>Cronologia</h2><p class="sub">Non hai ancora fatto nessuna sostituzione.</p></div>`;
    return `<div class="card"><h2>Cronologia e rollback</h2>
      <p class="sub">Ogni sostituzione è registrata. Apri una voce per vedere le righe modificate e annullarla.</p>
      <table><thead><tr><th>Data</th><th>Dove</th><th>Operazione</th><th>File / righe</th><th>Backup</th><th>Stato</th><th></th></tr></thead><tbody>
      ${s.history.map((h) => {
        const [lab, cls] = STATUS[h.status] || [h.status, "muted"];
        return `<tr><td>${esc(fmtDate(h.created))}</td><td><span class="chip">${h.branch === "nodered" ? "Node-RED" : "Home Assistant"}</span></td><td>${esc(h.title || h.id)}${h.note ? `<div class="hint">${esc(h.note)}</div>` : ""}</td>
          <td>${h.files} / ${h.lines}</td><td>${h.backup ? "sì" : "no"}</td><td><span class="chip ${cls}">${lab}</span></td>
          <td><button class="b sec" style="padding:6px 14px" data-action="detail" data-id="${esc(h.id)}" data-branch="${esc(h.branch || "ha")}">Apri</button></td></tr>`;
      }).join("")}</tbody></table></div>`;
  }

  _detail() {
    const s = this._s, op = s.detail.operation, rp = s.detail.rollback_preview;
    const [lab, cls] = STATUS[op.status] || [op.status, "muted"];
    const conflicts = rp ? rp.conflicts : [];
    const canForce = conflicts.length && op.backup;
    const rb = s.rbResult;
    return `<div class="card"><div class="row" style="margin-top:0"><button class="b sec" data-action="closedetail">← Cronologia</button></div>
      <h2 style="margin-top:12px">${esc(op.title || op.id)}</h2>
      <p class="sub">${esc(fmtDate(op.created))} · <span class="chip ${cls}">${lab}</span> · backup: ${op.backup ? "sì" : "no"}${op.note ? " · " + esc(op.note) : ""}<br>Codice: <span class="mono">${esc(op.id)}</span></p>
      ${op.auto_rollback_reason ? `<div class="alert warn">Annullata automaticamente: <span class="mono">${esc(op.auto_rollback_reason)}</span></div>` : ""}
      ${op.error ? `<div class="alert err">${esc(op.error)}</div>` : ""}
      <h3>Sostituzioni</h3>
      <table><tbody>${op.mappings.map((m) => `<tr><td><span class="chip">${KIND[m.kind] || m.kind}</span></td><td class="mono">${esc(m.kind === "device" ? (m.note || m.old.slice(0, 8) + "…") : m.old)}</td><td>→</td><td class="mono">${esc(m.kind === "device" ? m.new.slice(0, 8) + "…" : m.new)}</td></tr>`).join("")}</tbody></table>
      <h3>File modificati</h3>${op.files.map((f) => this._fileCard(f, false)).join("")}
      ${rb ? this._rbResult(rb) : ""}
      ${rp && !rb ? `${conflicts.length ? `<div class="alert warn"><b>Rollback bloccato da conflitti:</b> alcuni file sono stati modificati dopo la sostituzione.<ul class="plain">${conflicts.map((c) => `<li><span class="mono">${esc(c.path)}</span> — ${esc(c.detail)}</li>`).join("")}</ul></div>` : `<div class="alert ok">Il rollback è possibile senza conflitti.</div>`}
        ${canForce ? `<div class="cb"><input type="checkbox" id="frc" data-bind="force" ${s.force ? "checked" : ""}/><label for="frc">Forza il ripristino dal backup (le modifiche fatte dopo a quei file andranno perse; ne tengo una copia)</label></div>` : ""}
        ${s.detailBranch === "nodered" ? `<div class="cb"><input type="checkbox" id="rst2" data-bind="restartNodered" ${s.restartNodered ? "checked" : ""}/><label for="rst2">Riavvia Node-RED dopo il ripristino (serve Home Assistant OS o Supervised)</label></div>` : ""}
        <div class="row"><div class="spacer"></div><button class="b danger" data-action="askrollback" data-id="${esc(op.id)}" data-branch="${esc(s.detailBranch)}">Ripristina (rollback)</button></div>` : ""}
      </div>`;
  }

  _rbResult(r) {
    if (r.ok) {
      return `<div class="alert ok"><b>Rollback completato.</b>${r.branch === "nodered" ? " " + this._noderedResult(r.restart).replace(/<\/?div[^>]*>/g, "") : ""}<ul class="plain">${r.files.map((f) => `<li><span class="mono">${esc(f.path)}</span> — ${esc(ACTION[f.action] || f.action)}</li>`).join("")}</ul>
        ${r.config_error ? `<div class="alert err">Attenzione: la configurazione risulta con errori: <span class="mono">${esc(r.config_error)}</span></div>` : ""}</div>`;
    }
    return `<div class="alert err"><b>Rollback non eseguito, nessun file toccato.</b><ul class="plain">${(r.conflicts || []).map((c) => `<li><span class="mono">${esc(c.path)}</span> — ${esc(c.detail)}</li>`).join("")}</ul></div>`;
  }

  _confirmDialog() {
    const c = this._s.confirm;
    if (!c) return "";
    if (c.type === "apply") {
      const s = this._s;
      return `<div class="overlay"><div class="dialog"><h2>Confermi la modifica?</h2>
        <p class="sub">Verranno modificati <b>${s.selected.size}</b> file. ${s.backup ? "Prima ne faccio una copia di backup." : "<b>Senza backup</b>: potrai annullare solo riga per riga."}
        Poi controllo la configurazione e, se Home Assistant segnala errori, ripristino tutto da solo.</p>
        <div class="row"><div class="spacer"></div><button class="b sec" data-action="cancelconfirm">Annulla</button><button class="b" data-action="apply">${s.backup ? "Backup e applica" : "Applica"}</button></div></div></div>`;
    }
    return `<div class="overlay"><div class="dialog"><h2>Annullare questa modifica?</h2>
      <p class="sub">I file torneranno com'erano prima della sostituzione. Se qualcosa è cambiato nel frattempo, controllo prima che non ci siano conflitti.</p>
      <div class="row"><div class="spacer"></div><button class="b sec" data-action="cancelconfirm">No</button><button class="b danger" data-action="rollback" data-id="${esc(c.id)}" data-branch="${esc(c.branch || "ha")}">Sì, ripristina</button></div></div></div>`;
  }
}

customElements.define("swap-wizard-panel", SwapWizardPanel);
