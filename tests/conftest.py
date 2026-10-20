"""Carica engine e journal come pacchetto 'swc' SENZA importare Home Assistant,
cosi' i test del motore girano ovunque (basta pytest)."""
import importlib.util
import sys
import types
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "swap_wizard"


def _load_core() -> None:
    if "swc" in sys.modules:
        return
    pkg = types.ModuleType("swc")
    pkg.__path__ = [str(PKG_DIR)]
    sys.modules["swc"] = pkg
    for name in ("engine", "journal"):
        spec = importlib.util.spec_from_file_location(f"swc.{name}", PKG_DIR / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"swc.{name}"] = module
        spec.loader.exec_module(module)
        setattr(pkg, name, module)


_load_core()
