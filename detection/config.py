"""
Configuration persistante sauvegardée dans data/config.json.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "data" / "config.json"

DEFAULTS = {
    "exposure": 1200,
}


def load() -> dict:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                data = json.load(f)
            return {**DEFAULTS, **data}
        except Exception as e:
            logger.warning(f"Erreur lecture config : {e}")
    return dict(DEFAULTS)


def save(data: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    current = load()
    current.update(data)
    with open(CONFIG_PATH, "w") as f:
        json.dump(current, f, indent=2)
    logger.info(f"Config sauvegardée : {current}")
