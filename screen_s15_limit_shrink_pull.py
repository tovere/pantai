#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""策略十五 · 昨涨停/大涨后今日缩量回踩。

买入（尾盘）:
  主板非 ST；昨涨停或昨涨幅≥6%；今日缩量（<0.80x）且收盘低于昨收（回踩）；
  今日跌幅不得低于 -3%；收盘仍在昨低之上（否则结构已坏）。
  可选上涨背景 `S15_UP_MODE=ma60|weekly|both`（默认 off：回测里加趋势过滤会降胜率、均值更负）。
  宽口径（昨>5%/跌>-6%/缩<1x）14000 笔期望贴零；深回踩与缩量不干净拖后腿，故收紧。

卖出:
  跌破买入日前一天最低价 → 立刻离场；
  次日及之后：放量下跌离场；红盘收盘离场；
  缩量下跌 → 再格局（继续拿）。
"""
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import cache_data
import screen_chan_wyckoff_3buy as s5

TODAY = os.environ.get("SCREEN_DATE", date.today().isoformat())
YDAY_MIN_CHG = float(os.environ.get("S15_YDAY_MIN_CHG", "6.0"))
LIMIT_CHG = float(os.environ.get("S15_LIMIT_CHG", "9.9"))
MAX_DROP = float(os.environ.get("S15_MAX_DROP", "-3.0"))
SHRINK = float(os.environ.get("S15_SHRINK", "0.80"))  # 今日量 < 昨日量 * SHRINK
MIN_AMT = float(os.environ.get("S15_MIN_AMT", "0.4"))
MAX_HOLD = int(os.environ.get("S15_MAX_HOLD", "8"))
# 上涨背景(可选): off=不过滤(默认, 回测显示过滤会降胜率); ma60 / weekly / both。
UP_MODE = os.environ.get("S15_UP_MODE", "off")


def universe(force=False):
    return cache_data.universe(force=force)


def _chg(c0, c1):
    if c0 is None or c1 is None or c0 <= 0:
        return None
    return (c1 / c0 - 1) * 100


def _avg(xs):
    return sum(xs) / len(xs) if xs else 0.0


def ma60_up(C, i):
    """日线上涨背景: 收盘在 MA60 上，且 MA60 不低于 10 日前。"""
    if i < 70:
        return False
    ma = _avg(C[i - 59 : i + 1])
    ma_p = _avg(C[i - 69 : i - 9])
    return ma > 0 and C[i] > ma and ma >= ma_p


def weekly_up(rows, i):
    """周线上涨背景: 复用策略五 weekly_up_state（as-of 当日，不含未来）。"""
    r = rows[: i + 1]
    if len(r) < 80:
        return False
    D = [x[0] for x in r]
    O = [float(x[1]) for x in r]
    C = [float(x[2]) for x in r]
    H = [float(x[3]) for x in r]
    L = [float(x[4]) for x in r]
    V = [float(x[5]) for x in r]
    A = [float(x[6]) for x in r]
    st = s5.weekly_up_state(D, O, H, L, C, V, A)
    return bool(st and st["up"])


def trend_ok(ma60, weekly, mode=None):
    mode = UP_MODE if mode is None else mode
    if mode in ("", "off", "0"):
        return True
    if mode == "ma60":
        return ma60
    if mode == "weekly":
        return weekly
    if mode == "both":
        return ma60 and weekly
    return ma60


def signal_at(code, name, rows, i, today_only=False, up_mode=None):
    if i < 3 or i >= len(rows):
        return None
    if today_only and rows[i][0] != TODAY:
        return None
    O = [float(r[1]) for r in rows]
    C = [float(r[2]) for r in rows]
    H = [float(r[3]) for r in rows]
    L = [float(r[4]) for r in rows]
    V = [float(r[5]) for r in rows]
    A = [float(r[6]) for r in rows]
    if min(C[i - 2], C[i - 1], C[i], V[i - 1], L[i - 1]) <= 0:
        return None

    prev_chg = _chg(C[i - 2], C[i - 1])
    chg = _chg(C[i - 1], C[i])
    if prev_chg is None or chg is None:
        return None
    if prev_chg < YDAY_MIN_CHG:
        return None
    if chg < MAX_DROP:
        return None
    if C[i] >= C[i - 1]:
        return None
    if V[i] >= V[i - 1] * SHRINK:
        return None
    amt = A[i] / 1e8
    if amt < MIN_AMT:
        return None
    stop = round(L[i - 1], 3)
    if C[i] <= stop:
        return None

    ma60 = ma60_up(C, i)
    weekly = weekly_up(rows, i)
    if not trend_ok(ma60, weekly, up_mode):
        return None

    vol_shrink = V[i] / V[i - 1] if V[i - 1] else 9
    limit = prev_chg >= LIMIT_CHG
    score = prev_chg + (10 if limit else 0) + (1 - vol_shrink) * 20 + (chg + 6)

    return {
        "code": code,
        "name": name,
        "date": rows[i][0],
        "close": round(C[i], 2),
        "chg": round(chg, 2),
        "prev_chg": round(prev_chg, 2),
        "prev_close": round(C[i - 1], 3),
        "prev_low": round(L[i - 1], 3),
        "prev_high": round(H[i - 1], 3),
        "vol_shrink": round(vol_shrink, 3),
        "amt": round(amt, 2),
        "stop": stop,
        "limit": int(limit),
        "ma60_up": int(ma60),
        "weekly_up": int(weekly),
        "score": round(score, 2),
    }


def exit_from(rows, buy_i, stop, max_hold=None):
    """buy_i 为尾盘买入日。从次日扫到止损 / 放量跌 / 红盘。"""
    max_hold = MAX_HOLD if max_hold is None else max_hold
    C = [float(r[2]) for r in rows]
    O = [float(r[1]) for r in rows]
    L = [float(r[4]) for r in rows]
    V = [float(r[5]) for r in rows]
    end = min(len(rows) - 1, buy_i + max_hold)
    if buy_i >= end:
        return buy_i, C[buy_i], "timeout"
    for j in range(buy_i + 1, end + 1):
        if O[j] <= stop:
            return j, O[j], "stop_open"
        if L[j] <= stop:
            return j, stop, "stop"
        if C[j] > C[j - 1]:
            return j, C[j], "red_close"
        if C[j] < C[j - 1] and V[j] >= V[j - 1]:
            return j, C[j], "vol_dump"
    return end, C[end], "timeout"


def check(code, name, rows):
    if not rows or rows[-1][0] != TODAY:
        return None
    return signal_at(code, name, rows, len(rows) - 1, today_only=True)


def main():
    uni = universe()
    print(
        f"股票池 {len(uni)} 只(主板非ST)，筛策略十五·昨大涨今缩量回踩 "
        f"(上涨={UP_MODE} 昨≥{YDAY_MIN_CHG}% 今跌≥{MAX_DROP}% 缩量<{SHRINK}x)…",
        flush=True,
    )
    hits, done = [], 0
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(cache_data.daily_kline, sec): (code, name) for code, name, sec in uni}
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

    hits.sort(key=lambda h: (-h["score"], h["vol_shrink"], -h["prev_chg"]))
    dump = os.environ.get("WATCH_JSON_OUT")
    if dump:
        json.dump({
            "strategy": "limit_shrink_pull",
            "variant": "stock",
            "is_etf": False,
            "date": TODAY,
            "hits": hits,
        }, open(dump, "w"), ensure_ascii=False)

    print(f"\n>>> 今日({TODAY}) 策略十五·昨大涨今缩量回踩 命中 {len(hits)} 只\n")
    print("代码    名称        现价   今日%   昨涨%   缩量   昨低/止损  额(亿)")
    for h in hits[:60]:
        tag = "涨停" if h["limit"] else "    "
        print(
            f"{h['code']}  {h['name'][:6]:<7} {h['close']:>7.2f} {h['chg']:>+6.2f} "
            f"{h['prev_chg']:>+6.2f}{tag} {h['vol_shrink']:>5.2f} "
            f"{h['stop']:>8.2f} {h['amt']:>6.1f}"
        )


if __name__ == "__main__":
    main()
