"""Next-open A/B linkage plans. Uses opening observations only, never daily highs."""
import json
from pathlib import Path


def prepare(day):
    path = Path(__file__).resolve().parent / "data_cache" / "limit_prediction.json"
    if not path.exists():
        raise ValueError("缺少连板分析")
    result = json.loads(path.read_text())
    if result.get("date") != day or result.get("intraday"):
        raise ValueError("连板账户等待当日收盘分析")
    items = result.get("items", [])
    relationships = []
    for sector in result.get("sectors", []):
        members = [r for r in items if r["code"] in sector["codes"]]
        if len(members) < 2:
            continue
        members.sort(key=lambda r: (-r["height"], r.get("sealTime") or "99:99", r["code"]))
        leader = members[0]
        for follower in members[1:]:
            if follower["height"] >= leader["height"]:
                continue
            relationships.append({"leader": leader["code"], "follower": follower["code"],
                                  "sector": sector["name"], "evidence": "同日正式行业；A板数高于B",
                                  "minLeaderGap": 0, "maxLeaderGap": .099,
                                  "minFollowerGap": -.02, "maxFollowerGap": .07})
    allowed = {r["follower"] for r in relationships}
    candidates = [{"code":r["code"], "name":r["name"], "close":r["close"],
                   "grade": "B", "flags": [], "height":r["height"],
                   "probability":r["probability"], "contextProbability":r.get("contextProbability")}
                  for r in items if r["code"] in allowed]
    return candidates, relationships, result.get("market", {})


def check(order, execution_day, read_bars):
    relation = order.get("linkage")
    if not relation:
        return ""
    for code, low, high in [(relation["leader"], relation["minLeaderGap"], relation["maxLeaderGap"]),
                            (order["code"], relation["minFollowerGap"], relation["maxFollowerGap"])]:
        series = read_bars(code)
        current = next((r for r in series if r[0] == execution_day), None)
        previous = [r for r in series if order["date"] <= r[0] < execution_day]
        if not current or not previous or previous[-1][0] != order["date"]:
            return "A/B缺少信号日或执行日行情，取消联动"
        gap = current[1]/previous[-1][2]-1
        if not low <= gap <= high:
            return "A开盘不符预期或B超过计划区间，取消联动"
    return ""
