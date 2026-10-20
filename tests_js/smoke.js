const { JSDOM } = require("jsdom");
const fs = require("fs");
const dom = new JSDOM("<!doctype html><body></body>", { runScripts: "outside-only", pretendToBeVisual: true });
const w = dom.window;
w.eval(fs.readFileSync(process.cwd() + "/custom_components/swap_wizard/frontend/panel.js", "utf8"));
const calls = [];
const hit = { line: 12, before: "  - action: notify.mobile_app_pixel_vecchio", after: "  - action: notify.mobile_app_pixel_nuovo", label: "Avviso <b>lavatrice</b>", pairs: [["notify.mobile_app_pixel_vecchio","notify.mobile_app_pixel_nuovo"]], truncated: false };
const ops = [{ id: "op1", created: "2026-10-20T10:00:00+00:00", title: "Cambio telefono", note: "", status: "applied", backup: true, files: 1, lines: 1, mappings: [{kind:"service",old:"notify.a",new:"notify.b",note:""}] }];
const hass = {
  states: { "sensor.a": {}, "sensor.b": {} },
  callWS: async (m) => {
    calls.push(m);
    switch (m.type) {
      case "swap_wizard/devices": return [
        { id: "d1", name: "Pixel Vecchio", model: "Pixel", mobile: true, notify: "notify.mobile_app_pixel_vecchio", entities: 3 },
        { id: "d2", name: "Pixel Nuovo", model: "Pixel", mobile: true, notify: "notify.mobile_app_pixel_nuovo", entities: 3 }];
      case "swap_wizard/propose_device": return { old:{id:"d1",name:"Pixel Vecchio"}, new:{id:"d2",name:"Pixel Nuovo"}, hints:["sensor.solo_vecchio"], warnings:["Una avvertenza"], unpaired_old:["sensor.solo_vecchio"], unpaired_new:[],
        mappings: [{kind:"device",old:"a".repeat(32),new:"b".repeat(32),note:"Pixel Vecchio → Pixel Nuovo",confidence:"high"},{kind:"service",old:"notify.mobile_app_pixel_vecchio",new:"notify.mobile_app_pixel_nuovo",confidence:"high"},{kind:"entity",old:"sensor.x_a",new:"sensor.x_b",confidence:"low"}] };
      case "swap_wizard/nodered_detect": return { candidates: [{ path: "/config/node-red", files: ["flows.json"], allowed: true }], settings: { nodered_path: "", nodered_addon: "a0d7b954_nodered" } };
      case "swap_wizard/preview": return { branch: m.branch, root: m.nodered_path, token:"tok", scanned: 9, backup_dir:"swap_wizard/backups", totals:{files:1,lines:1}, skipped:[{path:"x.yaml",reason:"boh"}], leftovers:[{path:"automations.yaml",line:3,label:"Altra",token:"sensor.solo_vecchio"}],
        files:[{path: m.branch === "nodered" ? "flows.json" : "automations.yaml", role: m.branch === "nodered" ? "nodered" : "automation", hits:[hit], line_revert_ok: m.branch !== "nodered"}], mappings:m.mappings };
      case "swap_wizard/apply": if (m.branch === "nodered") return { ok:true, branch:"nodered", operation:"op2", files:1, lines:1, backup:m.backup, restart:{ requested:m.restart_nodered, done:true, addon:m.nodered_addon } };
        return { ok:true, branch:"ha", operation:"op1", files:1, lines:1, backup:m.backup, check_available:true, config_already_invalid:false, reload:{done:["automation.reload"],errors:[],restart_required:false} };
      case "swap_wizard/history": return [...ops, { ...ops[0], id: "op2", title: "Cambio telefono (Node-RED)", branch: "nodered" }];
      case "swap_wizard/operation": return { operation: { ...ops[0], files:[{path:"automations.yaml",role:"automation",hits:[hit]}] }, rollback_preview: { files:[], conflicts:[{path:"automations.yaml",detail:"modificato dopo"}] } };
      case "swap_wizard/rollback": return { ok:true, branch:m.branch, restart:{ requested:m.restart_nodered, done:true, addon:m.nodered_addon }, files:[{path:"automations.yaml",action:"restored_full"}], reload:{done:[],errors:[]}, config_error:null };
    }
    throw new Error("unexpected " + m.type);
  },
};
const el = w.document.createElement("swap-wizard-panel");
w.document.body.appendChild(el);
el.hass = hass;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const q = (s) => el.shadowRoot.querySelector(s);
const click = async (sel) => { const n = q(sel); if (!n) throw new Error("manca " + sel); n.click(); await sleep(20); };
const ok = (c, m) => { if (!c) { console.error("FAIL:", m); process.exit(1); } console.log("ok  -", m); };
(async () => {
  await sleep(30);
  ok(q("[data-action=propose]"), "passo 1 disegnato");
  await click("[data-action=mode][data-v=entity]");
  const oe = q("input[data-bind=oldEnt]");
  oe.dispatchEvent(new w.FocusEvent("focusin", { bubbles: true }));
  ok(el.shadowRoot.querySelectorAll(".sugg li[data-v]").length === 2, "elenco entità proposto al clic");
  oe.value = "sensor.b"; oe.dispatchEvent(new w.Event("input", { bubbles: true }));
  const li = q(".sugg li[data-v]");
  ok(li && li.dataset.v === "sensor.b", "elenco filtrato mentre scrivi");
  li.dispatchEvent(new w.MouseEvent("mousedown", { bubbles: true, cancelable: true }));
  ok(oe.value === "sensor.b" && el._s.oldEnt === "sensor.b", "scelta dall'elenco salvata");
  await click("[data-action=mode][data-v=phone]");
  const sels = el.shadowRoot.querySelectorAll("select");
  sels[0].value = "d1"; sels[0].dispatchEvent(new w.Event("change", { bubbles: true })); await sleep(5);
  const sels2 = el.shadowRoot.querySelectorAll("select");
  sels2[1].value = "d2"; sels2[1].dispatchEvent(new w.Event("change", { bubbles: true })); await sleep(5);
  await click("[data-action=propose]");
  ok(el.shadowRoot.textContent.includes("Controlla cosa verrà sostituito"), "passo 2 raggiunto");
  ok(el.shadowRoot.textContent.includes("Una avvertenza") && el.shadowRoot.querySelectorAll("tbody tr").length >= 3, "tabella e avvertenze");
  await click("[data-action=preview]");
  ok(calls.at(-1).type === "swap_wizard/preview" && calls.at(-1).mappings.length === 3 && calls.at(-1).hints[0] === "sensor.solo_vecchio", "anteprima con 3 sostituzioni e hint");
  const txt = el.shadowRoot.textContent;
  ok(txt.includes("Vuoi fare il backup") && txt.includes("automations.yaml") && txt.includes("Da controllare a mano"), "passo 3: backup, file, da controllare");
  ok(!el.shadowRoot.innerHTML.includes("<b>lavatrice</b>"), "etichetta HTML sottoposta a escape");
  ok(q("mark.del") && q("mark.add"), "evidenziazione prima/dopo");
  const no = el.shadowRoot.querySelector("input[name=bk][value=false]");
  no.checked = true; no.dispatchEvent(new w.Event("change", { bubbles: true })); await sleep(5);
  await click("[data-action=askapply]");
  ok(q(".overlay") && q(".overlay").textContent.includes("Senza backup"), "conferma senza backup");
  await click("[data-action=apply]");
  const ap = calls.at(-1);
  ok(ap.type === "swap_wizard/apply" && ap.backup === false && ap.files[0] === "automations.yaml" && ap.token === "tok", "apply con backup=false");
  ok(el.shadowRoot.textContent.includes("Fatto") && el.shadowRoot.textContent.includes("op1"), "passo 4");
  await click("[data-action=gohistory]");
  ok(el.shadowRoot.textContent.includes("Cambio telefono"), "cronologia");
  await click("[data-action=detail]");
  ok(el.shadowRoot.textContent.includes("Rollback bloccato da conflitti"), "dettaglio con conflitti");
  const frc = q("#frc"); frc.checked = true; frc.dispatchEvent(new w.Event("change", { bubbles: true }));
  await click("[data-action=askrollback]");
  await click("[data-action=rollback]");
  const rb = calls.filter((c) => c.type === "swap_wizard/rollback").at(-1);
  ok(rb.operation_id === "op1" && rb.force === true && !("id" in rb), "rollback con operation_id e force");
  ok(el.shadowRoot.textContent.includes("Rollback completato"), "esito rollback");
  // ------------------------------------------------ ramo Node-RED
  await click("[data-action=tab][data-v=wizard]");
  await click("[data-action=restart]");
  ok(q("[data-action=branch][data-v=nodered]"), "scelta del ramo disponibile al passo 1");
  await click("[data-action=branch][data-v=nodered]");
  await sleep(30);
  const s1 = el.shadowRoot.querySelectorAll("select");
  s1[0].value = "d1"; s1[0].dispatchEvent(new w.Event("change", { bubbles: true })); await sleep(5);
  const s2 = el.shadowRoot.querySelectorAll("select");
  s2[1].value = "d2"; s2[1].dispatchEvent(new w.Event("change", { bubbles: true })); await sleep(5);
  await click("[data-action=propose]");
  ok(el.shadowRoot.textContent.includes("Cartella di Node-RED") && !el.shadowRoot.textContent.includes("dashboard salvate"), "passo 2 mostra la cartella Node-RED e non le dashboard");
  ok(q("input[data-bind=noderedPath]").value === "/config/node-red", "cartella rilevata precompilata");
  await click("[data-action=preview]");
  const pr = calls.filter((c) => c.type === "swap_wizard/preview").at(-1);
  ok(pr.branch === "nodered" && pr.nodered_path === "/config/node-red", "anteprima con ramo e cartella");
  ok(el.shadowRoot.textContent.includes("Flow di Node-RED") && el.shadowRoot.textContent.includes("backup è obbligatorio"), "ruolo flow e backup obbligatorio");
  ok(q("input[name=bk][value=false]").disabled && q("input[name=bk][value=true]").checked, "opzione senza backup bloccata");
  const rst = q("#rst"); rst.checked = true; rst.dispatchEvent(new w.Event("change", { bubbles: true }));
  await click("[data-action=askapply]");
  ok(q(".overlay"), "conferma");
  await click("[data-action=apply]");
  const ap2 = calls.filter((c) => c.type === "swap_wizard/apply").at(-1);
  ok(ap2.branch === "nodered" && ap2.backup === true && ap2.restart_nodered === true && ap2.nodered_addon === "a0d7b954_nodered" && ap2.files[0] === "flows.json", "apply Node-RED con backup e riavvio");
  ok(el.shadowRoot.textContent.includes("Node-RED riavviato"), "esito con riavvio");
  await click("[data-action=askrollback]");
  await click("[data-action=rollback]");
  const rb2 = calls.filter((c) => c.type === "swap_wizard/rollback").at(-1);
  ok(rb2.branch === "nodered" && rb2.operation_id === "op2" && rb2.restart_nodered === true, "rollback Node-RED con ramo");
  await click("[data-action=closedetail]");
  ok(el.shadowRoot.textContent.includes("Home Assistant") && el.shadowRoot.textContent.includes("Node-RED"), "cronologia con colonna Dove");
  console.log("TUTTO OK");
})().catch((e) => { console.error("ERRORE", e); process.exit(1); });
