#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""策略十一 · 回测: VDB 后缩量回踩买入, 止损=VDB低点, 止盈=确认顶分型。

嵌套段(chain≥1)会单独分档, 验证「VDB→缩量→再放量→再缩量」是否可做。
"""
import os
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

import cache_data
import vdb_pullback as sig

START = os.environ.get("START", "2025-07-01")
END = os.environ.get("END", "2026-07-30")
COST = 0.001
MAX_HOLD = int(os.environ.get("MAX_HOLD", "30"))
GAP_LIMIT = float(os.environ.get("GAP_LIMIT", "0.20"))
# touch=盘中触及VDB低即止(原版); close=收盘跌破才认(少被影线洗)
STOP_MODE = os.environ.get("STOP_MODE", "close")


def is_top_fractal(H, L, j):
    return H[j] > H[j - 1] and H[j] > H[j + 1] and L[j] > L[j - 1] and L[j] > L[j + 1]


def exit_trade(rows, i, rec):
    O = [float(r[1]) for r in rows]
    C = [float(r[2]) for r in rows]
    H = [float(r[3]) for r in rows]
    L = [float(r[4]) for r in rows]
    entry = rec["entry"]
    stop = rec["stop"]
    end = min(len(rows) - 1, i + MAX_HOLD)
    worst = 0.0
    for j in range(i + 1, end + 1):
        if C[j - 1] > 0 and abs(O[j] / C[j - 1] - 1) > GAP_LIMIT:
            return j, 0.0, "split", worst
        worst = min(worst, L[j] / entry - 1)
        if STOP_MODE == "close":
            if O[j] <= stop:
                return j, O[j], "stop_open", worst
            if C[j] < stop:
                return j, C[j], "stop", worst
        else:
            if O[j] <= stop:
                return j, O[j], "stop_open", worst
            if L[j] <= stop:
                return j, stop, "stop", worst
        if j >= i + 2 and is_top_fractal(H, L, j - 1):
            return j, C[j], "top_fractal", worst
    return end, C[end], "timeout", worst


def run_one(code, name, secid, rows=None):
    rows = rows if rows is not None else cache_data.daily_kline(secid)
    if not rows or len(rows) < 110:
        return []
    out = []
    for i in range(90, len(rows) - 3):
        d = rows[i][0]
        if not (START <= d <= END):
            continue
        rec = sig.signal_at(code, name, rows, i)
        if not rec:
            continue
        j, sell, reason, mae = exit_trade(rows, i, rec)
        if reason == "split":
            continue
        rec["exit"] = rows[j][0]
        rec["sell"] = sell
        rec["reason"] = reason
        rec["held"] = j - i
        rec["ret"] = sell / rec["entry"] - 1 - COST
        rec["mae"] = mae
        out.append(rec)
    return out


def _bucket(trades, label):
    if not trades:
        print(f"  {label}: 0笔")
        return
    rs = [t["ret"] for t in trades]
    print(
        f"  {label}: {len(rs):4d}笔  胜率{sum(r > 0 for r in rs) / len(rs) * 100:5.1f}%  "
        f"均值{statistics.mean(rs) * 100:+6.2f}%  中位{statistics.median(rs) * 100:+6.2f}%  "
        f"MAE{statistics.mean(t['mae'] for t in trades) * 100:+6.2f}%  "
        f"持有{statistics.mean(t['held'] for t in trades):.1f}天"
    )


def summarize(trades):
    rev = "偏反转" if sig.REQUIRE_REVERSAL else ("严格入场" if sig.STRICT_BUY else "宽松候选")
    print(
        f"\n>> 策略十一回测 {START}~{END}  {rev}  止损={STOP_MODE}@VDB低  "
        f"止盈=顶分型  信号 {len(trades)} 笔\n"
    )
    if not trades:
        return
    _bucket(trades, "总体")
    by_reason = {}
    for t in trades:
        by_reason.setdefault(t["reason"], []).append(t)
    print("\n出场:")
    for reason, ts in sorted(by_reason.items(), key=lambda x: -len(x[1])):
        _bucket(ts, reason)
    print("\n嵌套分档(chain=前面还有几段VDB):")
    for c in sorted({t.get("chain", 0) for t in trades}):
        _bucket([t for t in trades if t.get("chain", 0) == c], f"chain={c}")
    print("\n反转背景分档:")
    _bucket([t for t in trades if t.get("reversal")], "长跌/低位背景")
    _bucket([t for t in trades if not t.get("reversal")], "非超跌背景")
    sample = sorted(trades, key=lambda x: x["date"])[-15:]
    print("\n最近15笔:")
    for t in sample:
        print(
            f"{t['date']} {t['code']} {t['name'][:6]:<6} entry={t['entry']:.2f} "
            f"stop={t['stop']:.2f} chain={t.get('chain', 0)} "
            f"held={t['held']:>2} {t['reason']:<11} ret={t['ret'] * 100:+.1f}%"
        )


def main():
    if os.environ.get("ETF_ONLY", "0") != "0":
        uni = cache_data.etf_universe()
    else:
        uni = cache_data.universe()
    print(f"标的池 {len(uni)} 只，回测策略十一·VDB缩量回踩...", flush=True)
    trades, done = [], 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(run_one, c, n, s): c for c, n, s in uni}
        for fut in as_completed(futs):
            done += 1
            try:
                trades.extend(fut.result())
            except Exception:
                pass
            if done % 500 == 0:
                print(f"  {done}/{len(uni)} 信号{len(trades)}", flush=True)
    summarize(trades)


if __name__ == "__main__":
    main()
