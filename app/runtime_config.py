from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parent.parent
BASE_CONFIG_PATH = "app/config.yaml"
RUN_CONFIG_PATH = "01_inputs/run_config.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_runtime_config(root: Path = ROOT) -> dict[str, Any]:
    config = _load_yaml(root / BASE_CONFIG_PATH)
    run_config_file = root / RUN_CONFIG_PATH
    if run_config_file.exists():
        config = _deep_merge(config, _load_yaml(run_config_file))
    return config
