"""Test di integrazione con un Home Assistant vero (pytest-homeassistant-custom-component)."""
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def link_integration(hass):
    """Mette l'integrazione dentro <config>/custom_components del test."""
    target = Path(hass.config.path("custom_components"))
    target.mkdir(parents=True, exist_ok=True)
    dest = target / "swap_wizard"
    shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(ROOT / "custom_components" / "swap_wizard", dest, ignore=shutil.ignore_patterns("__pycache__"))
    yield


@pytest.fixture(autouse=True)
def clean_config_dir(hass):
    """La cartella di prova e' condivisa tra i test: la ripulisco prima e dopo."""
    cfg = Path(hass.config.path())

    def wipe():
        for name in ("automations.yaml", "scripts.yaml", "scenes.yaml"):
            (cfg / name).unlink(missing_ok=True)
        shutil.rmtree(cfg / "swap_wizard", ignore_errors=True)
        shutil.rmtree(cfg / "node-red", ignore_errors=True)

    wipe()
    yield
    wipe()
