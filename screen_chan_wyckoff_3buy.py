#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
缠论 + 威科夫三买盘中筛选器。

定义:
- 中枢/TR: 最近一段 8-18 日横向重叠区，振幅适中，收盘多次落在区间内。
- SOS/离开: 中枢后向上突破上沿，最高/收盘有效离开，且成交量放大。
- 三买/LPS: 突破后回踩上沿附近，不重新跌回中枢下半区，缩量且收盘承接。

这是日线级别的量化近似，不是完整笔/线段递归缠论。
数据: 东方财富前复权日线，盘中日 K 可用时按当日临时 K 筛。
"""
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import cache_data

TODAY = os.environ.get("SCREEN_DATE", date.today().isoformat())
MIN_AMOUNT = float(os.environ.get("MIN_AMOUNT", "50000000"))
REQUIRE_WEEKLY_UP = os.environ.get("REQUIRE_WEEKLY_UP", "1") != "0"
STRICT_BUY = os.environ.get("STRICT_BUY", "1") != "0"
# 中枢位置过滤: 用中枢下沿相对‘起涨低点’的前期涨幅(runup) 作为‘第几个中枢’的代理。
# 第一个中枢=底部吸筹(runup 小, 最稳); 第二/三个中枢=半山腰/趋势后段(runup 大, 背驰风险)。
RUNUP_LOOKBACK = int(os.environ.get("RUNUP_LOOKBACK", "60"))
MAX_RUNUP = float(os.environ.get("MAX_RUNUP", "0.60"))  # 硬顶: 前期涨幅超过即明显晚期中枢, 剔除
FIRST_PIVOT_RUNUP = float(os.environ.get("FIRST_PIVOT_RUNUP", "0.25"))  # 第一个中枢的前期涨幅上限
UA = "Mozilla/5.0"


def get(url, tries=4, timeout=10):
    for _ in range(tries):
        p = subprocess.run(
            ["curl", "--http1.1", "-s", "-m", str(timeout), "-A", UA, url],
            capture_output=True,
            text=True,
        )
        if p.returncode == 0 and p.stdout:
            return p.stdout
    return ""


def get_json(url, tries=4, timeout=10):
    for _ in range(tries):
        try:
            return json.loads(get(url, tries=1, timeout=timeout))
        except json.JSONDecodeError:
            continue
    return {}


def universe():
    if os.environ.get("ETF_ONLY", "0") != "0":
        return cache_data.etf_universe()
    return cache_data.universe()


def kline(secid):
    return cache_data.daily_kline(secid)


def avg(xs):
    return sum(xs) / len(xs) if xs else 0


def weekly_bars(D, O, H, L, C, V, A):
    bars = []
    cur = None
    for d, o, h, l, c, v, a in zip(D, O, H, L, C, V, A):
        year, week, _ = date.fromisoformat(d).isocalendar()
        key = (year, week)
        if cur is None or cur["key"] != key:
            if cur:
                bars.append(cur)
            cur = {"key": key, "date": d, "open": o, "high": h, "low": l, "close": c, "vol": v, "amt": a}
        else:
            cur["date"] = d
            cur["high"] = max(cur["high"], h)
            cur["low"] = min(cur["low"], l)
            cur["close"] = c
            cur["vol"] += v
            cur["amt"] += a
    if cur:
        bars.append(cur)
    return bars


def weekly_up_state(D, O, H, L, C, V, A):
    W = weekly_bars(D, O, H, L, C, V, A)
    if len(W) < 16:
        return None
    WC = [w["close"] for w in W]
    WH = [w["high"] for w in W]
    WL = [w["low"] for w in W]
    i = len(W) - 1
    ma = lambda p, k: avg(WC[k - p + 1 : k + 1])
    ma5, ma10, ma10p = ma(5, i), ma(10, i), ma(10, i - 3)
    recent_mid = sorted(WC[max(0, i - 5) : i + 1])[len(WC[max(0, i - 5) : i + 1]) // 2]
    higher_lows = WL[i] >= min(WL[max(0, i - 6) : i]) * 0.98
    not_lower_highs = WH[i] >= max(WH[max(0, i - 8) : i]) * 0.94
    up = WC[i] > ma10 and ma10 > ma10p and WC[i] >= recent_mid and (ma5 >= ma10 * 0.995 or higher_lows) and not_lower_highs
    return {
        "up": up,
        "wclose": WC[i],
        "wma10": ma10,
        "wbias10": (WC[i] / ma10 - 1) * 100,
        "wdate": W[i]["date"],
    }


def find_box_before_pullback(H, L, C, V, end):
    # end 是突破前一天；向前寻找一个窄幅重叠的 TR/中枢。
    best = None
    for length in range(8, 19):
        start = end - length + 1
        if start < 60:
            continue
        hi = max(H[start : end + 1])
        lo = min(L[start : end + 1])
        mid = (hi + lo) / 2
        width = (hi / lo - 1) if lo else 9
        if not (0.035 <= width <= 0.18):
            continue
        inside = sum(1 for k in range(start, end + 1) if lo <= C[k] <= hi)
        if inside < max(6, int(length * 0.65)):
            continue
        # 横向特征：前后收盘差不能太大，避免把单边趋势当中枢。
        drift = abs(C[end] / C[start] - 1)
        if drift > width * 0.8:
            continue
        score = inside / length - width
        if best is None or score > best["score"]:
            best = {"start": start, "end": end, "hi": hi, "lo": lo, "mid": mid, "width": width, "score": score}
    return best


def box_stage(L, box):
    """估算中枢在上升结构中的位置(第几个中枢)。

    以中枢下沿相对 RUNUP_LOOKBACK 日内‘起涨低点’的前期涨幅 runup 作为廉价代理:
      runup < FIRST_PIVOT_RUNUP        -> 第 1 个中枢(底部吸筹, 最稳)
      < 2*FIRST_PIVOT_RUNUP            -> 第 2 个中枢(半山腰再吸筹)
      更高                              -> 第 3+ 个中枢(趋势后段, 背驰风险)
    这是‘数中枢’的近似: 底部第一个中枢贴着起涨低点, runup 小; 越往后中枢离底越远, runup 越大。
    """
    start = box["start"]
    lo0 = max(0, start - RUNUP_LOOKBACK)
    origin_low = min(L[lo0:start]) if start > lo0 else box["lo"]
    runup = (box["lo"] / origin_low - 1) if origin_low > 0 else 0.0
    if runup < FIRST_PIVOT_RUNUP:
        stage = 1
    elif runup < FIRST_PIVOT_RUNUP * 2:
        stage = 2
    else:
        stage = 3
    return {"runup": runup, "stage": stage, "origin_low": origin_low}


def check(code, name, rows):
    if len(rows) < 80:
        return None
    D = [r[0] for r in rows]
    O = [float(r[1]) for r in rows]
    C = [float(r[2]) for r in rows]
    H = [float(r[3]) for r in rows]
    L = [float(r[4]) for r in rows]
    V = [float(r[5]) for r in rows]
    A = [float(r[6]) for r in rows]
    i = len(rows) - 1
    if D[i] != TODAY or A[i] < MIN_AMOUNT:
        return None

    weekly = weekly_up_state(D, O, H, L, C, V, A)
    if not weekly:
        return None
    if REQUIRE_WEEKLY_UP and not weekly["up"]:
        return None

    ma = lambda p, k: avg(C[k - p + 1 : k + 1])
    if C[i] < ma(60, i) or ma(60, i) <= ma(60, i - 10):
        return None
    if C[i] / C[i - 1] - 1 < -0.055:
        return None

    # 最近 1-5 日是三买/LPS回踩日，SOS 在其前 1-8 日内。
    for sos in range(max(65, i - 12), i):
        box = find_box_before_pullback(H, L, C, V, sos - 1)
        if not box:
            continue
        # 中枢位置过滤: 只买趋势前段的中枢, 严格版仅取第一个中枢。
        stage = box_stage(L, box)
        if stage["runup"] > MAX_RUNUP:
            continue
        if STRICT_BUY and stage["stage"] != 1:
            continue
        upper, lower, mid = box["hi"], box["lo"], box["mid"]
        vbase = avg(V[max(0, sos - 20) : sos])
        sos_break = C[sos] > upper * 1.015 and H[sos] > upper * 1.025
        sos_volume = V[sos] >= vbase * 1.25
        if not (sos_break and sos_volume):
            continue

        # SOS 后不能快速跌回中枢内部深处。
        if min(C[sos + 1 : i + 1] or [C[i]]) < mid:
            continue
        pull_days = i - sos
        if not (1 <= pull_days <= 8):
            continue
        pull_low = min(L[sos + 1 : i + 1])
        pull_low_idx = min(range(sos + 1, i + 1), key=lambda x: L[x])
        pull_touch = upper * 0.985 <= pull_low <= upper * 1.08
        support = C[i] >= upper * 0.995 and L[i] >= mid
        shrink = avg(V[sos + 1 : i + 1]) <= V[sos] * 0.78
        close_pos = (C[i] - L[i]) / (H[i] - L[i]) if H[i] > L[i] else 1
        if not (pull_touch and support and shrink and close_pos >= 0.45):
            continue
        if C[i] / C[i - 3] - 1 >= 0.20:
            continue
        if STRICT_BUY:
            if pull_days < 2:
                continue
            if not (upper * 0.99 <= pull_low <= upper * 1.04):
                continue
            if pull_low_idx <= sos or pull_low_idx >= i:
                continue
            if min(C[sos + 1 : i + 1]) < upper * 0.985:
                continue
            if max(H[sos + 1 : i + 1]) > H[sos] * 1.03:
                continue
            rebound = C[i] > C[i - 1] and C[i] > O[i] and C[i] >= H[i - 1] * 0.995
            reclaimed = C[i] >= upper * 1.01 and close_pos >= 0.6
            if not (rebound and reclaimed):
                continue

        return {
            "code": code,
            "name": name,
            "close": round(C[i], 2),
            "chg": round((C[i] / C[i - 1] - 1) * 100, 2),
            "box": f"{box['lo']:.2f}-{box['hi']:.2f}",
            "upper": round(upper, 2),
            "dist": round((C[i] / upper - 1) * 100, 1),
            "sos_date": D[sos][5:],
            "pull_days": pull_days,
            "vol_shrink": round(avg(V[sos + 1 : i + 1]) / V[sos], 2),
            "wbias10": round(weekly["wbias10"], 1),
            "buy_low": round(pull_low, 2),
            "amt": round(A[i] / 1e8, 1),
            "runup": round(stage["runup"] * 100, 1),
            "stage": stage["stage"],
        }
    return None


def main():
    uni = universe()
    wk = " + 周线向上" if REQUIRE_WEEKLY_UP else ""
    strict = "严格入场" if STRICT_BUY else "宽松候选"
    print(f"股票池(剔ST/科创/创业板) {len(uni)} 只，筛缠论+威科夫三买{wk} + {strict}...", flush=True)
    hits, done = [], 0
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(kline, sec): (code, name) for code, name, sec in uni}
        for fut in as_completed(futs):
            code, name = futs[fut]
            done += 1
            try:
                rows = fut.result()
                if rows:
                    item = check(code, name, rows)
                    if item:
                        hits.append(item)
            except Exception:
                pass
            if done % 500 == 0:
                print(f"  {done}/{len(uni)} 命中{len(hits)}", flush=True)

    # 第一个中枢优先, 同档再按距上沿/成交额排。
    hits.sort(key=lambda x: (x["stage"], x["dist"], -x["amt"]))
    _dump = os.environ.get("WATCH_JSON_OUT")
    if _dump:
        import json as _json
        _is_etf = os.environ.get("ETF_ONLY", "0") != "0"
        _json.dump({
            "strategy": "chan_wyckoff_3buy",
            "variant": ("etf" if _is_etf else "stock") + ("_strict" if STRICT_BUY else "_loose"),
            "strict": STRICT_BUY,
            "is_etf": _is_etf,
            "date": TODAY,
            "hits": hits,
        }, open(_dump, "w"), ensure_ascii=False)
    print(f"\n>>> 今日({TODAY}) 周线向上 + 日线级别 缠论+威科夫三买/{strict} 命中 {len(hits)} 只\n")
    print("代码    名称        现价    今日%  中枢/TR        距上沿  周MA10  三买低  SOS日  回踩天  缩量比  额(亿)  前涨%  中枢#")
    for h in hits[:50]:
        print(
            f"{h['code']}  {h['name'][:6]:<7} {h['close']:>7.2f} {h['chg']:>+6.2f} "
            f"{h['box']:<13} {h['dist']:>+5.1f}% {h['wbias10']:>+5.1f}% {h['buy_low']:>7.2f} {h['sos_date']:>5} "
            f"{h['pull_days']:>5} {h['vol_shrink']:>7.2f} {h['amt']:>6.1f} {h['runup']:>+6.1f} {h['stage']:>5}"
        )


if __name__ == "__main__":
    main()
