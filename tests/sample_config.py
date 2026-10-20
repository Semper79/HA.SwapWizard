"""File di configurazione di esempio, scritti come li scrive Home Assistant."""

OLD_DEV = "0123456789abcdef0123456789abcdef"
NEW_DEV = "fedcba9876543210fedcba9876543210"

AUTOMATIONS = f"""- id: '1700000000001'
  alias: Avviso lavatrice finita
  description: ''
  triggers:
  - trigger: state
    entity_id: sensor.lavatrice_stato
    to: finito
  actions:
  - action: notify.mobile_app_pixel_vecchio
    data:
      title: Lavatrice
      message: Finito!   # commento da conservare
  - alias: Notifica con dispositivo
    device_id: {OLD_DEV}
    domain: mobile_app
    type: notify
    message: Ciao
  mode: single
- id: '1700000000002'
  alias: Batteria telefono scarica
  description: ''
  triggers:
  - trigger: numeric_state
    entity_id: sensor.pixel_vecchio_battery_level
    below: 15
  actions:
  - action: notify.mobile_app_pixel_vecchio
    data:
      message: 'Batteria {{{{ states("sensor.pixel_vecchio_battery_level") }}}}%'
  - action: notify.mobile_app_pixel_vecchio_altro
    data:
      message: non toccare
  mode: single
- id: '1700000000003'
  alias: Con blueprint
  description: ''
  use_blueprint:
    path: miei/notifica.yaml
    input:
      notify_device: {OLD_DEV}
"""

SCRIPTS = """invia_avviso:
  alias: Invia avviso
  sequence:
  - alias: Manda notifica
    action: notify.mobile_app_pixel_vecchio
    data:
      message: Script
"""

PACKAGE = """automation:
  - alias: Da package
    trigger:
      - platform: state
        entity_id: binary_sensor.porta
    action:
      - service: notify.mobile_app_pixel_vecchio
        data:
          message: Porta
"""

UNRELATED = """homeassistant:
  name: Casa
"""


# ---------------------------------------------------------------- Node-RED
import json as _json

FLOW_NODES = [
    {"id": "tab1", "type": "tab", "label": "Notifiche", "disabled": False, "info": ""},
    {"id": "n1", "type": "server-state-changed", "z": "tab1", "name": "Batteria bassa",
     "entityidfilter": "sensor.pixel_vecchio_battery_level", "wires": [["n2"]]},
    {"id": "n2", "type": "api-call-service", "z": "tab1", "name": "Notifica batteria",
     "domain": "notify", "service": "mobile_app_pixel_vecchio",
     "data": "{\"message\":\"Batteria\"}", "wires": [[]]},
    {"id": "n3", "type": "api-call-service", "z": "tab1", "name": "Notifica con azione",
     "action": "notify.mobile_app_pixel_vecchio",
     "targets": {"entity_id": ["sensor.pixel_vecchio_battery_level"], "device_id": [OLD_DEV + "#"]},
     "wires": [[]]},
    {"id": "n4", "type": "function", "z": "tab1", "name": "Calcolo",
     "func": "var a = 'sensor.altro';\nsensor.pixel_vecchio_battery_level\nreturn msg;", "wires": [[]]},
    {"id": "n5", "type": "api-call-service", "z": "tab1", "name": "Non toccare",
     "domain": "notify", "service": "mobile_app_pixel_vecchio_altro", "wires": [[]]},
]
FLOWS_PRETTY = _json.dumps(FLOW_NODES, indent=4, ensure_ascii=False)
FLOWS_COMPACT = _json.dumps(FLOW_NODES, separators=(",", ":"), ensure_ascii=False)
