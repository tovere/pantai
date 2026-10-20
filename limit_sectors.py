"""Capture current industry membership with observation date; never backfill it."""
import json
import time
from pathlib import Path
from datetime import datetime
from limit_pool import TZ, DIR
from fuyao_client import get

ROOT = Path(__file__).resolve().parent / "data_cache" / "limit_sectors"


def capture():
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    catalog = get("/api/a-share-index/catalog/ths-index-list", {"tag": "industry"})
    path = ROOT / today
    path.mkdir(parents=True, exist_ok=True)
    for sector in catalog.get("item", []):
        target = path / (sector["thscode"] + ".json")
        if target.exists():
            continue
        members = get("/api/a-share-index/constituents/ths-stock-list", {"thscode": sector["thscode"]})
        result = {"date": today, "sector": sector, "members": members.get("item", []),
                  "capturedAt": datetime.now(TZ).isoformat()}
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(result, ensure_ascii=False))
        tmp.replace(target)
        time.sleep(.2)


def aggregate(day):
    poolpath = DIR / (day + ".json")
    if not poolpath.exists():
        return []
    pool = json.loads(poolpath.read_text())
    hits = {str(item["ticker"]): item for item in pool["items"]}
    out = []
    for path in sorted((ROOT / day).glob("*.json")):
        data = json.loads(path.read_text())
        members = {str(m["ticker"]) for m in data["members"]}
        matched = [hits[code] for code in members & hits.keys()]
        if matched:
            out.append({"name": data["sector"]["name"], "thscode": data["sector"]["thscode"],
                        "members": len(members), "limitCount": len(matched),
                        "limitPct": round(len(matched)/len(members)*100, 2),
                        "maxHeight": max((i.get("continue_day_cnt") or 1) for i in matched),
                        "codes": sorted(members & hits.keys())})
    return sorted(out, key=lambda r: (-r["limitCount"], -r["limitPct"]))
