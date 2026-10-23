#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""策略十三 · 启动加速：第一波强启动后整理，再突破转强（不追近涨停）。

入场形态（当日收盘确认）:
  1) 近 LOOKBACK 日内存在启动日: 涨幅≥LAUNCH_CHG% 且放量≥VOL_MULT×前5日均量
  2) 启动后整理 HOLD_MIN~HOLD_MAX 天，期间未跌破启动低×BREAK_BUF，窗内最大回撤≤MAX_DD%
  3) 今日收阳、收盘创新高（≥整理段最高），涨幅在 [MIN_TODAY, MAX_TODAY]%（默认剔≥9.5%近涨停）
"""
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import cache_data

TODAY = os.environ.get("SCREEN_DATE", date.today().isoformat())
LOOKBACK = int(os.environ.get("S13_LOOKBACK", "20"))
LAUNCH_CHG = float(os.environ.get("S13_LAUNCH_CHG", "7.0"))
VOL_MULT = float(os.environ.get("S13_VOL_MULT", "1.4"))
HOLD_MIN = int(os.environ.get("S13_HOLD_MIN", "3"))
HOLD_MAX = int(os.environ.get("S13_HOLD_MAX", "8"))
MAX_DD = float(os.environ.get("S13_MAX_DD", "8.0"))
BREAK_BUF = float(os.environ.get("S13_BREAK_BUF", "0.99"))
MIN_TODAY = float(os.environ.get("S13_MIN_TODAY", "3.0"))
MAX_TODAY = float(os.environ.get("S13_MAX_TODAY", "8.5"))
MIN_AMT = float(os.environ.get("S13_MIN_AMT", "0.3"))  # 亿
EXCLUDE_CYB = os.environ.get("S13_EXCLUDE_CYB", "1") != "0"  # 剔创业/科创


def universe():
    items = cache_data.universe()
    if not EXCLUDE_CYB:
        return items
    # universe() 本身已剔 3/688；保持一致
    return items


def signal_at(code, name, rows, i, today_only=False):
    if i < LOOKBACK + 10 or i >= len(rows):
        return None
    if today_only and rows[i][0] != TODAY:
        return None

    O = [float(r[1]) for r in rows]
    C = [float(r[2]) for r in rows]
    H = [float(r[3]) for r in rows]
    L = [float(r[4]) for r in rows]
    V = [float(r[5]) for r in rows]
    A = [float(r[6]) for r in rows]

    # 今日转强
    chg = (C[i] / C[i - 1] - 1) * 100 if C[i - 1] else 0
    if not (MIN_TODAY <= chg <= MAX_TODAY):
        return None
    if C[i] <= O[i]:
        return None
    amt = A[i] / 1e8
    if amt < MIN_AMT:
        return None

    # 在近窗内找启动日 launch（不含今日）
    best = None
    lo = max(6, i - LOOKBACK)
    for j in range(lo, i):
        gap = i - j  # 启动后已过天数
        if gap < HOLD_MIN or gap > HOLD_MAX:
            continue
        jchg = (C[j] / C[j - 1] - 1) * 100 if C[j - 1] else 0
        if jchg < LAUNCH_CHG:
            continue
        base_vol = sum(V[j - 5 : j]) / 5
        if base_vol <= 0 or V[j] < VOL_MULT * base_vol:
            continue
        # 整理段 j+1 .. i-1
        seg = range(j + 1, i)
        if not seg:
            continue
        launch_low = L[j]
        peak_after = max(H[k] for k in seg)
        trough = min(L[k] for k in seg)
        # 未破启动低
        if trough < launch_low * BREAK_BUF:
            continue
        # 相对启动收盘的回撤
        dd = (min(C[k] for k in seg) / C[j] - 1) * 100
        if dd < -MAX_DD:
            continue
        # 今日突破整理高（或至少收在启动后新高）
        if C[i] < peak_after:
            continue
        # 也要求相对启动前高有推进
        pre_high = max(H[max(0, j - 60) : j]) if j > 0 else H[j]
        score = jchg + V[j] / base_vol + chg
        cand = {
            "code": code,
            "name": name,
            "date": rows[i][0],
            "close": round(C[i], 2),
            "chg": round(chg, 2),
            "amt": round(amt, 2),
            "launch_date": rows[j][0],
            "launch_chg": round(jchg, 2),
            "launch_low": round(launch_low, 3),
            "hold_days": gap,
            "consol_high": round(peak_after, 3),
            "pull_dd": round(dd, 2),
            "vol_ratio": round(V[j] / base_vol, 2),
            "stop": round(launch_low * BREAK_BUF, 3),
            "pre_high": round(pre_high, 3),
            "score": round(score, 2),
        }
        if best is None or cand["score"] > best["score"]:
            best = cand
    return best


def check(code, name, rows):
    if not rows or rows[-1][0] != TODAY:
        return None
    return signal_at(code, name, rows, len(rows) - 1, today_only=True)


def main():
    uni = universe()
    print(
        f"股票池 {len(uni)} 只，筛策略十三·启动加速 "
        f"(启动≥{LAUNCH_CHG}% 整理{HOLD_MIN}-{HOLD_MAX}日 今日{MIN_TODAY}-{MAX_TODAY}%)...",
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

    hits.sort(key=lambda h: (-h["score"], -h["chg"]))
    dump = os.environ.get("WATCH_JSON_OUT")
    if dump:
        json.dump({
            "strategy": "launch_accel",
            "variant": "stock",
            "is_etf": False,
            "date": TODAY,
            "hits": hits,
        }, open(dump, "w"), ensure_ascii=False)

    print(f"\n>>> 今日({TODAY}) 策略十三·启动加速 命中 {len(hits)} 只\n")
    print("代码    名称        现价   今日%  启动日    启动% 整理天 回撤%  止损   额(亿)")
    for h in hits[:40]:
        print(
            f"{h['code']}  {h['name'][:6]:<7} {h['close']:>7.2f} {h['chg']:>+6.2f} "
            f"{h['launch_date']} {h['launch_chg']:>+5.1f} {h['hold_days']:>4} "
            f"{h['pull_dd']:>+5.1f} {h['stop']:>6.2f} {h['amt']:>6.1f}"
        )


if __name__ == "__main__":
    main()
