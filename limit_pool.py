"""Dated raw limit pool acquisition; no inferred historical sector memberships."""
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from fuyao_client import get

DIR = Path(__file__).resolve().parent / "data_cache" / "limit_pools"
TZ = timezone(timedelta(hours=8))


def fetch(day, broken=False):
    date = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=TZ)
    items, page = [], 1
    while True:
        data = get("/api/a-share/special-data/" + ("limit-break-pool" if broken else "limit-up-pool"),
                   {"date_ms": int(date.timestamp()*1000), "page": page, "size": 200})
        items.extend(data.get("item") or [])
        if page >= data.get("pagination", {}).get("pages", 1):
            break
        page += 1
        if page > 30:
            raise ValueError("涨停池分页异常，拒绝保存不完整结果")
    result = {"date": day, "capturedAt": datetime.now(TZ).isoformat(),
              "source": "hithink-limit-break-pool" if broken else "hithink-limit-up-pool", "items": items}
    DIR.mkdir(parents=True, exist_ok=True)
    path = DIR / (day + ("-broken.json" if broken else ".json"))
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False))
    tmp.replace(path)
    return result


def enrich(result, day):
    path = DIR / (day + ".json")
    if not path.exists():
        return result
    pool = json.loads(path.read_text())
    lookup = {str(i.get("ticker")): i for i in pool["items"]}
    themes = {}
    for row in result["items"]:
        raw = lookup.get(row["code"])
        if not raw:
            row["qualityStatus"] = "涨停池未匹配"
            continue
        row.update(name=raw.get("name"), sealMoney=raw.get("seal_money"),
                   maxSealMoney=raw.get("max_seal_money"), sealTime=raw.get("limit_up_time"),
                   reason=raw.get("limit_up_reason"), qualityStatus="已匹配")
        # Provider supplies a textual reason, not structured sector membership.
        row["themes"] = [s.strip() for s in re.split(r"[+＋、;；]", raw.get("limit_up_reason") or "") if s.strip()]
        for theme in set(row["themes"]):
            group = themes.setdefault(theme, {"theme": theme, "count": 0, "maxHeight": 0, "codes": []})
            group["count"] += 1
            group["maxHeight"] = max(group["maxHeight"], row["height"])
            group["codes"].append(row["code"])
    result["themes"] = sorted(themes.values(), key=lambda t: -t["count"])
    result["poolDate"] = pool["date"]
    result["warnings"].append("题材按数据源涨停原因文本拆分，不等同正式板块成分；题材与封单尚未参与历史概率估计。")
    return result
