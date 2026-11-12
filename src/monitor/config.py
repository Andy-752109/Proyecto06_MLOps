"""Carga de configuración e identidades reproducibles (config_ref, source_ref)."""
import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config/monitor.yaml"
SCENARIOS_PATH = ROOT / "config/scenarios.yaml"

# Secciones que definen el comportamiento comparable entre C1 y C2.
CONFIG_SECTIONS = ("model", "policy", "windows", "reference", "alerts", "capture")


def canonical_hash(obj) -> str:
    data = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(data.encode()).hexdigest()


def load_config(path: Path = CONFIG_PATH) -> dict:
    cfg = yaml.safe_load(Path(path).read_text())
    cfg["model"]["classes"] = {int(k): v for k, v in cfg["model"]["classes"].items()}
    lo, hi = cfg["policy"]["lower"], cfg["policy"]["upper"]
    if not (0 <= lo < hi <= 1):
        raise ValueError(f"umbrales inválidos: se requiere 0 <= {lo} < {hi} <= 1")
    if cfg["model"]["conf_floor"] > lo:
        raise ValueError("conf_floor por encima del umbral inferior ocultaría la zona baja")
    cfg["config_ref"] = config_ref(cfg)
    return cfg


def config_snapshot(cfg: dict) -> dict:
    """Secciones que identifican la configuración (lo que se hashea)."""
    return {k: cfg[k] for k in CONFIG_SECTIONS}


def config_ref(cfg: dict) -> str:
    snap = json.loads(json.dumps(config_snapshot(cfg)))  # claves int -> str, igual que al guardar
    return "cfg-" + canonical_hash(snap)[:12]


def load_scenario(name: str, path: Path = SCENARIOS_PATH) -> dict:
    scenarios = yaml.safe_load(Path(path).read_text())
    if name not in scenarios:
        raise KeyError(f"escenario desconocido {name!r}; opciones: {sorted(scenarios)}")
    sc = scenarios[name]
    sc["name"] = name
    sc["source_ref"] = "src-" + canonical_hash(sc["source"])[:12]
    return sc


def load_reference(cfg: dict) -> dict | None:
    path = ROOT / cfg["reference"]["path"]
    if not path.exists():
        return None
    return json.loads(path.read_text())
