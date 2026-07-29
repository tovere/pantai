#!/usr/bin/env python3
"""Isolated AkShare history store; never reads or writes data_cache/."""
import json
import os
from pathlib import Path

ROOT = Path(os.environ.get("AKSHARE_DATA_DIR", "data_akshare")).resolve()
PROJECT_ROOT = Path(__file__).resolve().parent
LEGACY_CACHE = (PROJECT_ROOT / "data_cache").resolve()


def ensure_isolated_root():
    try:
        ROOT.relative_to(LEGACY_CACHE)
    except ValueError:
        pass
    else:
        raise RuntimeError(f"AKSHARE_DATA_DIR must not be inside {LEGACY_CACHE}")
    if ROOT == LEGACY_CACHE:
        raise RuntimeError(f"AKSHARE_DATA_DIR must not equal {LEGACY_CACHE}")
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "daily").mkdir(exist_ok=True)


def daily_path(secid):
    ensure_isolated_root()
    return ROOT / "daily" / f"{secid}.json"


def daily_kline(secid):
    path = daily_path(secid)
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8") as f:
            rows = json.load(f)
        return rows if isinstance(rows, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def universe(kind):
    ensure_isolated_root()
    path = ROOT / f"{kind}_universe.json"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return json.load(f)
