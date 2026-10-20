#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""情绪周期核心：用全市场日线算涨停/连板/晋级/炸板/溢价，再映射成五阶段。

口径（务必读）：
  - 股票池默认主板（cache_data.universe，剔 ST/科创/创业板）。本地缓存几乎没有创业板，
    连板高度会系统性偏低；这是「主板情绪」，不是游资软件里的全 A 情绪。
  - 涨停=收盘贴住涨停价（允许 0.5% 容差），且不得远超涨停价（排除新股首日/脏数据）。
  - 一字板=开/高/低/收都贴涨停价。信号日封死涨停、一字涨停，一律视为买不进。

阶段：冰点 / 修复 / 发酵 / 高潮 / 退潮。
A 过滤器默认只在 修复+发酵 开仓；B 打板按阶段选首板回踩 / 二板回踩。
"""
from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cache_data

PHASES = ("ice", "repair", "ferment", "climax", "ebb")
PHASE_CN = {
    "ice": "冰点",
    "repair": "修复",
    "ferment": "发酵",
    "climax": "高潮",
    "ebb": "退潮",
}
# A：回测后趋势策略在发酵/高潮更好，冰点修复显著为负（与「高潮空仓」的打板教科书相反）
A_TRADE_PHASES = frozenset({"ferment", "climax"})
A_HYPOTHESIS_PHASES = frozenset({"repair", "ferment"})  # 教科书假设，回测对照用
A_PAUSE_PHASES = frozenset({"ice", "repair"})  # 筛选器只在这两档关趋势策略
# B1 首板回踩：教科书冰点+修复；回测该档为负，筛选器只作观察
B1_PHASES = frozenset({"ice", "repair"})
# B2 二板回踩：教科书修复+发酵；回测为负
B2_PHASES = frozenset({"repair", "ferment"})
B3_PHASES = frozenset({"ferment", "climax"})  # 昨日涨停溢价仅这两档勉强非负

HEAT_ICE = float(os.environ.get("HEAT_ICE", "28"))
HEAT_REPAIR = float(os.environ.get("HEAT_REPAIR", "45"))
HEAT_FERMENT = float(os.environ.get("HEAT_FERMENT", "68"))
HEAT_DROP_EBB = float(os.environ.get("HEAT_DROP_EBB", "10"))
MIN_DAY_N = int(os.environ.get("SENT_MIN_N", "800"))  # 当日样本太少不计入日历
WORKERS = int(os.environ.get("WORKERS", "12"))
CAL_PATH = cache_data.CACHE_DIR / "sentiment_cycle.json"


def limit_ratio(code):
    if code.startswith(("300", "301", "688", "689")):
        return 0.20
    if code.startswith(("8", "4")):
        return 0.30
    return 0.10


def _near(px, target, rel=0.005):
    return target > 0 and abs(px - target) / target <= rel


def limit_px(prev, ratio):
    return round(prev * (1 + ratio), 2)


def is_limit_up(code, prev, close):
    """收盘封住涨停价（1 分钱容差）。不用 9.5% 近似，否则连板高度会被放大。"""
    if prev <= 0 or close <= 0:
        return False
    r = limit_ratio(code)
    px = limit_px(prev, r)
    return close >= px - 0.01 and close <= px + 0.05


def is_limit_down(code, prev, close):
    if prev <= 0 or close <= 0:
        return False
    r = limit_ratio(code)
    px = round(prev * (1 - r), 2)
    return close <= px + 0.01 and close >= px - 0.05


def is_broken(code, prev, high, close):
    """盘中摸到涨停价但收盘没封住。"""
    if prev <= 0 or high <= 0:
        return False
    if is_limit_up(code, prev, close):
        return False
    r = limit_ratio(code)
    px = limit_px(prev, r)
    return high >= px - 0.01


def is_yizi_up(code, prev, o, h, low, c):
    """一字涨停：开盘即涨停且全天不打开。"""
    if not is_limit_up(code, prev, c):
        return False
    r = limit_ratio(code)
    px = limit_px(prev, r)
    return _near(o, px, 0.006) and _near(h, px, 0.006) and _near(low, px, 0.006)


def parse_stock(code, name, rows):
    """把一只票的日线编成连板序列。rows 同 cache_data.daily_kline。"""
    n = len(rows)
    if n < 30:
        return None
    dates = [r[0] for r in rows]
    O = [float(r[1]) for r in rows]
    C = [float(r[2]) for r in rows]
    H = [float(r[3]) for r in rows]
    L = [float(r[4]) for r in rows]
    V = [float(r[5]) for r in rows]
    A = [float(r[6]) for r in rows] if len(rows[0]) > 6 else [0.0] * n
    lu = [0] * n
    ld = [0] * n
    brk = [0] * n
    yizi = [0] * n
    streak = [0] * n
    for i in range(1, n):
        prev = C[i - 1]
        if is_limit_up(code, prev, C[i]):
            lu[i] = 1
            yizi[i] = 1 if is_yizi_up(code, prev, O[i], H[i], L[i], C[i]) else 0
            streak[i] = streak[i - 1] + 1
        else:
            brk[i] = 1 if is_broken(code, prev, H[i], C[i]) else 0
            ld[i] = 1 if is_limit_down(code, prev, C[i]) else 0
            streak[i] = 0
    return {
        "code": code,
        "name": name,
        "dates": dates,
        "O": O, "C": C, "H": H, "L": L, "V": V, "A": A,
        "lu": lu, "ld": ld, "brk": brk, "yizi": yizi, "streak": streak,
    }


def _load_one(item):
    code, name, secid = item
    rows = cache_data.daily_kline(secid)
    if not rows:
        return None
    return parse_stock(code, name, rows)


def load_stocks(uni=None):
    uni = uni if uni is not None else cache_data.universe()
    out, done, fail = [], 0, 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(_load_one, it): it[0] for it in uni}
        for fut in as_completed(futs):
            done += 1
            try:
                rec = fut.result()
                if rec:
                    out.append(rec)
                else:
                    fail += 1
            except Exception:
                fail += 1
            if done % 800 == 0:
                print(f"  载入 {done}/{len(uni)} 有效{len(out)} 空{fail}", flush=True)
    return out


def _heat(m):
    """0-100 情绪热度。高度项用 2/3/4+ 板的宽度，避免单只老妖把全市场抬进高潮。"""
    high_w = m["h2"] + 2 * m["h3"] + 3 * m["h4p"]
    h = min(high_w / 20.0, 1.0) * 30.0
    lu_s = max(0.0, min(1.0, (m["lu"] - 15) / 80.0)) * 25.0
    prem_s = max(0.0, min(1.0, (m["premium"] + 0.03) / 0.10)) * 20.0
    promo_s = max(0.0, min(1.0, m["promo"])) * 15.0
    brk_s = (1.0 - max(0.0, min(1.0, m["break_rate"]))) * 10.0
    return h + lu_s + prem_s + promo_s + brk_s


def assign_phases(days):
    """热度分档 + 从高位回落标退潮；禁止冰点一天跳到高潮。"""
    heats = [_heat(m) for m in days]
    prev = None
    for i, m in enumerate(days):
        h = heats[i]
        m["heat"] = round(h, 1)
        h5max = max(heats[max(0, i - 5) : i + 1])
        falling = h5max - h >= HEAT_DROP_EBB

        if h < HEAT_ICE:
            raw = "ice"
        elif h < HEAT_REPAIR:
            raw = "repair"
        elif h < HEAT_FERMENT:
            raw = "ferment"
        else:
            raw = "climax"
        # 高位板宽度：2板以上家数。单只 10 连板的老妖不抬档。
        high_n = m["h2"] + m["h3"] + m["h4p"]
        if high_n >= 12 and raw != "ice":
            raw = "climax"
        elif high_n >= 6 and raw == "repair":
            raw = "ferment"
        elif high_n <= 1 and m["lu"] <= 30 and m["premium"] < 0 and raw != "climax":
            raw = "ice"

        p = raw
        if prev in ("ferment", "climax") and falling and raw != "climax":
            p = "ebb"
        elif prev == "ebb":
            if falling and raw != "ice":
                p = "ebb"
            else:
                p = raw

        if prev == "ice" and p in ("ferment", "climax"):
            p = "repair"
        if prev == "repair" and p == "climax":
            p = "ferment"
        if prev in ("climax", "ferment") and p == "ice":
            p = "ebb"

        m["phase"] = p
        m["phase_cn"] = PHASE_CN[p]
        prev = p
    return days


def aggregate(stocks):
    """按交易日汇总市场情绪指标。溢价=昨日涨停今日开盘相对昨收。"""
    by_date = {}
    for s in stocks:
        dates, C, O = s["dates"], s["C"], s["O"]
        lu, ld, brk, yizi, streak = s["lu"], s["ld"], s["brk"], s["yizi"], s["streak"]
        code, name = s["code"], s["name"]
        n = len(dates)
        for i in range(1, n):
            d = dates[i]
            bucket = by_date.get(d)
            if bucket is None:
                bucket = {
                    "date": d,
                    "n": 0,
                    "lu": 0,
                    "ld": 0,
                    "brk": 0,
                    "yizi": 0,
                    "h1": 0,
                    "h2": 0,
                    "h3": 0,
                    "h4p": 0,
                    "max_height": 0,
                    "leader": "",
                    "leader_name": "",
                    "promo_num": 0,
                    "promo_den": 0,
                    "prem_sum": 0.0,
                    "prem_n": 0,
                    "up": 0,
                    "down": 0,
                }
                by_date[d] = bucket
            bucket["n"] += 1
            if C[i] > C[i - 1]:
                bucket["up"] += 1
            elif C[i] < C[i - 1]:
                bucket["down"] += 1
            if lu[i]:
                bucket["lu"] += 1
                h = streak[i]
                if h > bucket["max_height"]:
                    bucket["max_height"] = h
                    bucket["leader"] = code
                    bucket["leader_name"] = name
                if h == 1:
                    bucket["h1"] += 1
                elif h == 2:
                    bucket["h2"] += 1
                elif h == 3:
                    bucket["h3"] += 1
                else:
                    bucket["h4p"] += 1
                if yizi[i]:
                    bucket["yizi"] += 1
            if ld[i]:
                bucket["ld"] += 1
            if brk[i]:
                bucket["brk"] += 1
            # 昨日涨停 → 今日晋级 / 今日开盘溢价
            if lu[i - 1]:
                bucket["promo_den"] += 1
                if lu[i]:
                    bucket["promo_num"] += 1
                if C[i - 1] > 0:
                    bucket["prem_sum"] += O[i] / C[i - 1] - 1
                    bucket["prem_n"] += 1

    days = []
    for d in sorted(by_date):
        b = by_date[d]
        if b["n"] < MIN_DAY_N:
            continue
        promo = (b["promo_num"] / b["promo_den"]) if b["promo_den"] else 0.0
        attempt = b["lu"] + b["brk"]
        brk_rate = (b["brk"] / attempt) if attempt else 0.0
        prem = (b["prem_sum"] / b["prem_n"]) if b["prem_n"] else 0.0
        days.append({
            "date": d,
            "n": b["n"],
            "lu": b["lu"],
            "ld": b["ld"],
            "brk": b["brk"],
            "yizi": b["yizi"],
            "h1": b["h1"],
            "h2": b["h2"],
            "h3": b["h3"],
            "h4p": b["h4p"],
            "max_height": b["max_height"],
            "leader": b["leader"],
            "leader_name": b["leader_name"],
            "promo": promo,
            "promo_n": b["promo_num"],
            "promo_d": b["promo_den"],
            "break_rate": brk_rate,
            "premium": prem,
            "high_n": b["h2"] + b["h3"] + b["h4p"],
            "breadth": (b["up"] / (b["up"] + b["down"])) if (b["up"] + b["down"]) else 0.5,
        })
    return assign_phases(days)


def phase_map(days):
    return {m["date"]: m["phase"] for m in days}


def save_calendar(days, n_stocks):
    CAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "asof": days[-1]["date"] if days else "",
        "n_stocks": n_stocks,
        "days": days,
    }
    tmp = CAL_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(CAL_PATH)


def load_calendar():
    try:
        payload = json.loads(CAL_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    days = payload.get("days") if isinstance(payload, dict) else None
    return days if days else None


def build_calendar(uni=None, persist=True, reuse=True):
    """载入全市场日线 → 情绪日历。reuse=True 时若磁盘日历日期够新则直接用。"""
    if reuse:
        cached = load_calendar()
        if cached:
            return cached, None
    stocks = load_stocks(uni)
    days = aggregate(stocks)
    if persist and days:
        save_calendar(days, len(stocks))
    return days, stocks


def advice(phase):
    if phase == "ice":
        return "5/10/11 少开新仓；12 连小阳仍可看（样本少）"
    if phase == "repair":
        return "样本很少；5/10/11 慎开，不要等修复才买"
    if phase == "ferment":
        return "策略10 个股这段最好；5 ETF 发酵偏弱；11 正常做；12 正常看"
    if phase == "climax":
        return "5 ETF / 5个股 / 11 开（高潮更好）；10 可做；12 连小阳降权"
    return "退潮：5/10 少开或停；11 仍正但胜率掉；12 连小阳这段最好"


if __name__ == "__main__":
    os.environ.setdefault("CACHE_ONLY", "1")
    print("构建情绪日历…", flush=True)
    days, stocks = build_calendar(reuse=False)
    n = len(stocks or [])
    print(f"股票 {n} 只，交易日 {len(days)} 根\n")
    print("日期        阶段  热度  涨停 跌停 最高板 1/2/3/4+板  晋级%  炸板%  溢价%  宽度%")
    for m in days[-25:]:
        print(
            f"{m['date']}  {m['phase_cn']:<2} {m['heat']:5.1f} "
            f"{m['lu']:4d} {m['ld']:4d} {m['max_height']:3d} "
            f"{m['h1']:3d}/{m['h2']:2d}/{m['h3']:2d}/{m['h4p']:2d}  "
            f"{m['promo']*100:5.1f} {m['break_rate']*100:5.1f} "
            f"{m['premium']*100:+6.2f} {m['breadth']*100:5.1f}"
        )
    from collections import Counter
    cnt = Counter(m["phase_cn"] for m in days)
    print("\n阶段天数:", dict(cnt))
    if days:
        print(f"最新 {days[-1]['date']} {days[-1]['phase_cn']} · {advice(days[-1]['phase'])}")
