"""
Configuração dinâmica em runtime — salva em bot_config.json.
Sobrepõe os defaults do config.py sem precisar de redeploy.
"""

import json
from pathlib import Path
from config import (
    OPPORTUNITIES_SOURCES, KEYWORDS_OPPORTUNITIES, OPORTUNIDADES_CHANNEL_ID,
    NEWS_SOURCES,
)

_CONFIG_PATH = (
    Path("/app/data/bot_config.json")
    if Path("/app/data").exists()
    else Path(__file__).parent / "bot_config.json"
)

_DEFAULTS = {
    "opp_channel_id": None,   # None → usa OPORTUNIDADES_CHANNEL_ID do env
    "opp_sources":    None,   # None → usa OPPORTUNITIES_SOURCES do config.py
    "opp_keywords":   None,   # None → usa KEYWORDS_OPPORTUNITIES do config.py
    "news_sources":   None,   # None → usa NEWS_SOURCES do config.py
}


def _load() -> dict:
    if _CONFIG_PATH.exists():
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                return {**_DEFAULTS, **json.load(f)}
        except Exception:
            pass
    return dict(_DEFAULTS)


def _save(cfg: dict):
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


# ─── Getters ─────────────────────────────────

def get_opp_channel_id() -> int:
    v = _load()["opp_channel_id"]
    return v if v is not None else OPORTUNIDADES_CHANNEL_ID

def get_opp_sources() -> list:
    v = _load()["opp_sources"]
    return v if v is not None else OPPORTUNITIES_SOURCES

def get_opp_keywords() -> list:
    v = _load()["opp_keywords"]
    return v if v is not None else list(KEYWORDS_OPPORTUNITIES)

def get_news_sources() -> list:
    v = _load()["news_sources"]
    return v if v is not None else list(NEWS_SOURCES)


# ─── Setters ─────────────────────────────────

def set_opp_channel_id(val: int):
    cfg = _load(); cfg["opp_channel_id"] = val; _save(cfg)

def set_opp_sources(val: list):
    cfg = _load(); cfg["opp_sources"] = val; _save(cfg)

def set_opp_keywords(val: list):
    cfg = _load(); cfg["opp_keywords"] = val; _save(cfg)

def set_news_sources(val: list):
    cfg = _load(); cfg["news_sources"] = val; _save(cfg)

def reset():
    if _CONFIG_PATH.exists():
        _CONFIG_PATH.unlink()
    print("[CONFIG] Reset para defaults.")
