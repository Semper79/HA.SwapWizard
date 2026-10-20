"""Costanti di Swap Wizard."""

DOMAIN = "swap_wizard"
VERSION = "0.2.0"

PANEL_URL_PATH = "swap-wizard"
PANEL_WEBCOMPONENT = "swap-wizard-panel"
STATIC_URL = "/swap_wizard_static"

DATA_MANAGER = "manager"
DATA_SETUP_DONE = "setup_done"

# cartella (dentro la configurazione di HA) dove stanno registro e backup
DATA_DIR_NAME = "swap_wizard"
# sotto-cartella per registro e backup del ramo Node-RED
NODERED_DIR_NAME = "nodered"

BRANCHES = ("ha", "nodered")

# slug del componente aggiuntivo "Node-RED" della community (Home Assistant OS / Supervised)
DEFAULT_NODERED_ADDON = "a0d7b954_nodered"
OPT_NODERED_PATH = "nodered_path"
OPT_NODERED_ADDON = "nodered_addon"
