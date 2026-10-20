# Swap Wizard

![Validate](https://github.com/Semper79/HA.SwapWizard/actions/workflows/validate.yml/badge.svg) ![Tests](https://github.com/Semper79/HA.SwapWizard/actions/workflows/tests.yml/badge.svg) ![Licenza MIT](https://img.shields.io/badge/licenza-MIT-blue)

Pannello per Home Assistant che sostituisce **un telefono, un dispositivo o una singola entità** in tutte le automazioni, script e scene **e nei flow di Node-RED**, con **backup**, **registro di ogni modifica** e **rollback completo**.

Nato per il caso «ho cambiato telefono e le notifiche puntano ancora al vecchio», ma funziona anche per un sensore guasto sostituito da uno nuovo.

- Nessun Docker, nessun add-on: è un'**integrazione personalizzata** (funziona anche su Home Assistant Core/Container/Supervised/OS).
- Installabile da **HACS** (repository personalizzato) o a mano.
- Interfaccia a 4 passi nel menu laterale, in italiano.

## Cosa sostituisce

| Cosa | Dove si trova | Esempio |
|---|---|---|
| Servizio di notifica | YAML, script, azioni | `notify.mobile_app_pixel_vecchio` → `notify.mobile_app_pixel_nuovo` |
| `device_id` | azioni/trigger «dispositivo» dell'editor grafico, input dei blueprint | `0123…cdef` → `fedc…3210` |
| Entità | trigger, condizioni, azioni, template, dashboard | `sensor.pixel_vecchio_battery_level` → `sensor.pixel_nuovo_battery_level` |

Per il telefono le entità vengono abbinate in automatico (batteria, posizione, rete…); per gli altri dispositivi per tipo e classe. Ogni abbinamento è mostrato nel passo 2 con un livello di affidabilità e lo puoi correggere o escludere.

## Come non rompe le automazioni

La sostituzione lavora **sul testo** dei file, riga per riga. Non legge e riscrive il YAML, quindi commenti, ordine, virgolette e struttura restano identici: cambiano solo gli identificatori, e solo quando sono parole intere (`sensor.x` non tocca `sensor.x_altro` né `binary_sensor.x`).
Funziona allo stesso modo per automazioni scritte a mano, create dall'editor grafico (`automations.yaml`), script, scene, package e blueprint.

Dopo la modifica:
1. controlla la configurazione con il verificatore di Home Assistant;
2. se compaiono **errori nuovi**, ripristina da solo i file originali;
3. altrimenti ricarica automazioni/script/scene (nessun riavvio, tranne per le dashboard).

## Il flusso

1. **Dove e cosa sostituire** – prima scegli il ramo (**Home Assistant** oppure **Node-RED**), poi telefono, dispositivo o entità. Le sostituzioni sono le stesse nei due rami: cambia solo dove si cerca.
2. **Controlla** – tabella delle sostituzioni, modificabile; puoi aggiungere righe a mano.
3. **Anteprima e backup** – elenco dei file che verranno modificati, con ogni riga prima/dopo e il nome dell'automazione. Poi la domanda: *vuoi fare il backup?*
4. **Fatto** – riepilogo e pulsante «Annulla questa modifica».

Le righe che usano entità del vecchio dispositivo **senza corrispondente sul nuovo** non vengono toccate: compaiono tra le «da controllare a mano».

## Ramo Node-RED

Cerca e sostituisce dentro i flow (`flows.json`) con la stessa logica del ramo Home Assistant: anteprima nodo per nodo («Notifiche › Notifica batteria»), domanda sul backup, registro, rollback e ripristino automatico.

- **Cosa sostituisce:** `device_id` dei nodi dispositivo, entità (filtri, bersagli, dati, codice dei nodi function), azioni `notify.mobile_app_*`; per i nodi con servizio scritto in due campi (`"domain": "notify"` + `"service": "mobile_app_x"`) cambia il solo nome del servizio.
- **Come:** sul testo, senza riscrivere il JSON: formattazione e ordine dei nodi restano identici. Dopo la modifica il file viene riletto e, se non fosse più JSON valido, torna com'era.
- **Dove cerca:** nella cartella di Node-RED che indichi (viene proposta se trovata: `/config/node-red`, `/share/node-red`, `/addon_configs/*node-red*`). Prende i file `.json` che sono elenchi di nodi; salta `flows_cred.json` e `package.json`.
- **Cartelle consentite:** dentro `/config` sempre; fuori solo se autorizzate in `allowlist_external_dirs` di `configuration.yaml`.
- **Riavvio:** Node-RED legge i flow solo all'avvio, quindi la modifica diventa attiva dopo un riavvio, e fino ad allora un «Deploy» dall'editor la sovrascriverebbe. Puoi spuntare «Riavvia Node-RED dopo la modifica» (chiama `hassio.addon_restart`, quindi serve Home Assistant OS o Supervised; lo slug predefinito è `a0d7b954_nodered`, modificabile nel pannello). In alternativa riavvii tu.
- **Flow compatti:** se `flows.json` è salvato su una sola riga, il registro riga per riga non può bastare: in quel caso il backup è obbligatorio e il pannello lo impone.
- **Node-RED su un altro dispositivo** (o in un contenitore che Home Assistant non vede) non è raggiungibile: Home Assistant può modificare solo i file che vede.
- Registro e backup del ramo Node-RED stanno in `/config/swap_wizard/nodered/`; la **cronologia** mostra le operazioni di entrambi i rami.

## Backup, registro e rollback

Tutto sta in `/config/swap_wizard/`:

```
swap_wizard/
  operations/<id>.json         registro: sostituzioni, file, ogni riga prima/dopo, checksum
  backups/<id>/<file>          copia originale di ogni file modificato
  backups/<id>/_pre_rollback/  stato dei file subito prima di un rollback
```

- **Con backup** il rollback ripristina i file originali identici.
- **Senza backup** il rollback funziona comunque, **riga per riga**, grazie al registro.
- Se dopo la sostituzione hai modificato altre parti dei file, il rollback le **conserva** e ripristina solo le righe cambiate.
- Se una riga cambiata è stata ritoccata nel frattempo, il rollback **non tocca nulla** e ti elenca i conflitti. Con il backup puoi «forzare»: i file tornano com'erano, e una copia di quelli attuali resta in `_pre_rollback`.
- Il registro viene scritto **prima** di toccare i file; le scritture sono atomiche e, se una fallisce, quelle già fatte vengono annullate subito.
- Per sicurezza, se tra l'anteprima e l'applicazione un file cambia, l'applicazione si ferma e chiede di rigenerare l'anteprima.

Il backup di Swap Wizard copre **solo i file toccati**. Non sostituisce il backup completo di Home Assistant, che resta consigliato prima di cambiamenti grandi.

## Installazione

### Con HACS

[![Aggiungi a HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Semper79&repository=HA.SwapWizard&category=integration)

Il pulsante apre il tuo Home Assistant sulla pagina del repository. Oppure a mano:

1. HACS → ⋮ → *Repository personalizzati* → incolla `https://github.com/Semper79/HA.SwapWizard`, categoria **Integrazione**.
2. Scarica *Swap Wizard* e riavvia Home Assistant.
3. *Impostazioni → Dispositivi e servizi → Aggiungi integrazione → Swap Wizard*.
4. Compare **Swap Wizard** nel menu laterale (solo per amministratori).

### A mano
Copia la cartella `custom_components/swap_wizard` in `/config/custom_components/`, riavvia, poi come al punto 3.

## Cosa NON controlla

- App **AppDaemon** (`.py`) e template in file diversi da `.yaml/.yml/.jinja`.
- `secrets.yaml`, `custom_components`, `www`, `themes`.
- Riferimenti **dinamici** costruiti a runtime, come `notify.mobile_app_{{ nome }}`: nessuno strumento può saperlo da fuori.
- Le dashboard salvate dall'interfaccia si cercano solo se lo chiedi (casella nel passo 2) e richiedono un riavvio.

Per evitare di dover rifare tutto al prossimo cambio telefono: punta le automazioni a un **gruppo di notifica** o a un `input_text` con il nome del telefono, invece che al telefono in sé.

## Sviluppo e test

Tre livelli di test:

```
pip install pytest
pytest                      # motore di sostituzione + registro/rollback (non serve Home Assistant)

pip install pytest-homeassistant-custom-component home-assistant-frontend
pytest -c pytest_ha.ini     # integrazione su un Home Assistant vero: registri, WebSocket, pannello, ricarica

npm install jsdom
node tests_js/smoke.js      # il pannello attraverso tutti i passi, in un browser simulato (da questa cartella)
```

Coperti: flow di Node-RED (azioni, servizio diviso in dominio e nome, a capo `\n` nel codice, file compatto su una riga, cartelle non consentite, riavvio del componente aggiuntivo), formati di automazione (editor grafico, YAML, script, package, blueprint), identificatori simili che non devono essere toccati, fine riga CRLF, scambio incrociato di due entità, rollback con e senza backup, rollback dopo modifiche successive, conflitti, blocco se il file cambia dopo l'anteprima, scrittura interrotta a metà, abbinamento telefono vecchio/nuovo, ripristino automatico se la configurazione risulta errata, accesso riservato agli amministratori.

Verificato con Home Assistant 2026.2.3 e Python 3.13. Non provato su un'istanza reale con telefoni veri, con un Node-RED vero né in un vero browser. Il formato dei nodi di Node-RED (campi `action`, `domain`/`service`, `device_id`, `entity_id`) è ricavato dalla documentazione dei nodi e da esempi, non da flow reali: provalo prima su una copia.
