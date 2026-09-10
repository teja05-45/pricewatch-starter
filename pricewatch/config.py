from __future__ import annotations

from pathlib import Path
import yaml


def load_stores(path: str | Path = "stores.yaml", base_url_override: str | None = None) -> dict:
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if base_url_override:
        cfg["base_url"] = base_url_override
    cfg["base_url"] = cfg["base_url"].rstrip("/")
    return cfg


def load_rules(path: str | Path = "alerts.yaml") -> list[dict]:
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return cfg.get("rules", [])

