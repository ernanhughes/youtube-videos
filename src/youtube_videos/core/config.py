"""Hydra composition with a minimal OmegaConf-compatible fallback for restricted environments."""
from __future__ import annotations
from pathlib import Path
import os
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[3] / "config"
PACKAGED_ROOT = Path(__file__).resolve().parents[1] / "conf"
CONFIG_ROOT = Path(os.environ.get("YTV_CONFIG_DIR", PROJECT_ROOT if PROJECT_ROOT.is_dir() else PACKAGED_ROOT))


def _deep_merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for key, value in b.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(workflow: str = "technical_lesson", events: str = "local", config_dir: Path | None = None) -> dict:
    root = (config_dir or CONFIG_ROOT).resolve()
    # Hydra is the production composer. Use its actual config groups where installed.
    try:
        from hydra import compose, initialize_config_dir
        from omegaconf import OmegaConf
        with initialize_config_dir(version_base=None, config_dir=str(root)):
            cfg = compose(config_name="config", overrides=[f"workflow={workflow}", f"events={events}"])
        return OmegaConf.to_container(cfg, resolve=True)
    except ImportError:
        base = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
        base.pop("defaults", None)
        base.pop("hydra", None)
        return _deep_merge(base, {
            "workflow": yaml.safe_load((root / "workflow" / f"{workflow}.yaml").read_text(encoding="utf-8")),
            "events": yaml.safe_load((root / "events" / f"{events}.yaml").read_text(encoding="utf-8")),
        })
