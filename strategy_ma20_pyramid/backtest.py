#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""策略十二（冲胜率调优）：上穿 MA20 + 多头排列 + 贴线乖离 + 收盘位置；破 MA5 离场。

目标约 40%+ 胜率。不加仓。同池对照策略三。默认本地日线缓存。
"""
from __future__ import annotations

import os
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cache_data

START = os.environ.get("START", "2025-07-01")
END = os.environ.get("END", "2026-06-29")
COST = float(os.environ.get("COST", "0.001"))
WORKERS = int(os.environ.get("WORKERS", "8"))
BENCH = os.environ.get("BENCH_SECID", "1.510300")
REQUIRE_UP_MKT = os.environ.get("REQUIRE_UP_MKT", "1") != "0"
# 入场贴线：收盘相对 MA20 乖离上限
BIAS_MAX = float(os.environ.get("BIAS_MAX", "0.03"))
# 收盘在当日 K 线位置下限 (C-L)/(H-L)
CLOSE_POS_MIN = float(os.environ.get("CLOSE_POS_MIN", "0.55"))
HARD_STOP = float(os.environ.get("HARD_STOP", "0.05"))

_UP_MKT = None


def market_up_map():
    global _UP_MKT
    if _UP_MKT is not None:
        return _UP_MKT
    rows = cache_data.daily_kline(BENCH) or []
    out = {}
    if len(rows) < 70:
        _UP_MKT = out
        return out
    C = [float(r[2]) for r in rows]
    D = [r[0] for r in rows]
    for i in range(59, len(rows)):
        ma20 = sum(C[i - 19 : i + 1]) / 20
        ma60 = sum(C[i - 59 : i + 1]) / 60
        ret20 = C[i] / C[i - 20] - 1 if i >= 20 else 0.0
        out[D[i]] = bool(C[i] >= ma20 and C[i] >= ma60 and ret20 >= 0)
    _UP_MKT = out
    return out


def _in_range(dates, i):
    return i >= 63 and i < len(dates) - 1 and START <= dates[i] <= END


def _chg_ok(code, C, i):
    lim = 0.20 if code.startswith("30") else 0.10
    chg = C[i] / C[i - 1] - 1
    return chg >= -0.05 and chg < lim - 0.005


def _prep(rows):
    dates = [r[0] for r in rows]
    O = [float(r[1]) for r in rows]
    C = [float(r[2]) for r in rows]
    H = [float(r[3]) for r in rows]
    L = [float(r[4]) for r in rows]
    V = [float(r[5]) for r in rows]
    n = len(rows)
    ma5 = [sum(C[max(0, k - 4) : k + 1]) / min(5, k + 1) for k in range(n)]
    ma10 = [sum(C[max(0, k - 9) : k + 1]) / min(10, k + 1) for k in range(n)]
    ma20 = [sum(C[k - 19 : k + 1]) / 20 if k >= 19 else None for k in range(n)]
    ma60 = [sum(C[k - 59 : k + 1]) / 60 if k >= 59 else None for k in range(n)]
    return dates, O, C, H, L, V, ma5, ma10, ma20, ma60


def _signal_s3(code, dates, O, C, H, L, V, ma20, ma60, i):
    if not _in_range(dates, i):
        return False
    m20, m60, m60p = ma20[i], ma60[i], ma60[i - 10]
    if m20 is None or m60 is None or m60p is None:
        return False
    uptrend = C[i] > m20 > m60 and m60 > m60p
    pulled = max(C[i - 9 : i + 1]) >= m20 * 1.05
    touch = L[i] <= m20 * 1.02 and C[i] >= m20
    shrink = V[i] < sum(V[i - 5 : i]) / 5
    return bool(uptrend and pulled and touch and shrink and _chg_ok(code, C, i))


def _entry_s12(code, dates, O, C, H, L, ma5, ma10, ma20, ma60, i, up_map):
    """上穿MA20 + MA20上行结构 + 多头排列 + 上涨市 + 乖离≤BIAS_MAX + 收盘位置。"""
    if not _in_range(dates, i):
        return False
    m20, m20p = ma20[i], ma20[i - 1]
    m60, m60p = ma60[i], ma60[i - 10]
    if None in (m20, m20p, m60, m60p, ma20[i - 5]):
        return False
    cross = C[i - 1] <= m20p and C[i] > m20
    structure = m20 > m60 and m60 > m60p and m20 > ma20[i - 5]
    align = ma5[i] >= ma10[i] >= m20
    up_mkt = (not REQUIRE_UP_MKT) or up_map.get(dates[i], False)
    bias_ok = (C[i] / m20 - 1) <= BIAS_MAX
    rng = H[i] - L[i]
    pos_ok = rng > 0 and (C[i] - L[i]) / rng >= CLOSE_POS_MIN
    return bool(
        cross
        and structure
        and align
        and up_mkt
        and bias_ok
        and pos_ok
        and _chg_ok(code, C, i)
    )


def _trade_s3(i, dates, O, C, L, ma20):
    buy = C[i]
    stop = buy * (1 - HARD_STOP)
    n = len(C)
    j = i + 1
    sell, reason, closed = None, "eod", True
    while j < n:
        if O[j] <= stop:
            sell, reason = O[j], "stop_open"
            break
        if L[j] <= stop:
            sell, reason = stop, "stop"
            break
        if C[j] < ma20[j]:
            sell, reason = C[j], "ma20_break"
            break
        j += 1
    if sell is None:
        sell, j, closed = C[n - 1], n - 1, False
    return {
        "entry": dates[i],
        "exit": dates[j],
        "ret": sell / buy - 1 - COST,
        "held": j - i,
        "closed": closed,
        "reason": reason,
        "exit_i": j,
    }


def _trade_s12(i, dates, O, C, L, ma5):
    """破 MA5 或 −HARD_STOP 离场。"""
    buy = C[i]
    stop = buy * (1 - HARD_STOP)
    n = len(C)
    j = i + 1
    sell, reason, closed = None, "eod", True
    while j < n:
        if O[j] <= stop:
            sell, reason = O[j], "stop_open"
            break
        if L[j] <= stop:
            sell, reason = stop, "stop"
            break
        if C[j] < ma5[j]:
            sell, reason = C[j], "ma5_break"
            break
        j += 1
    if sell is None:
        sell, j, closed = C[n - 1], n - 1, False
    return {
        "entry": dates[i],
        "exit": dates[j],
        "ret": sell / buy - 1 - COST,
        "held": j - i,
        "closed": closed,
        "reason": reason,
        "exit_i": j,
    }


def run_s3(code, name, rows):
    if not rows or len(rows) < 70:
        return []
    dates, O, C, H, L, V, ma5, ma10, ma20, ma60 = _prep(rows)
    n = len(rows)
    out = []
    i = 63
    while i < n - 1:
        if not _signal_s3(code, dates, O, C, H, L, V, ma20, ma60, i):
            i += 1
            continue
        rec = _trade_s3(i, dates, O, C, L, ma20)
        exit_i = rec.pop("exit_i")
        rec.update({"code": code, "name": name, "kind": "s3"})
        out.append(rec)
        i = exit_i + 1
    return out


def run_s12(code, name, rows, up_map):
    if not rows or len(rows) < 70:
        return []
    dates, O, C, H, L, V, ma5, ma10, ma20, ma60 = _prep(rows)
    n = len(rows)
    out = []
    i = 63
    while i < n - 1:
        if not _entry_s12(code, dates, O, C, H, L, ma5, ma10, ma20, ma60, i, up_map):
            i += 1
            continue
        rec = _trade_s12(i, dates, O, C, L, ma5)
        exit_i = rec.pop("exit_i")
        rec.update({"code": code, "name": name, "kind": "s12"})
        out.append(rec)
        i = exit_i + 1
    return out


def run_one(item, up_map):
    code, name, secid = item
    rows = cache_data.daily_kline(secid) or []
    return run_s3(code, name, rows), run_s12(code, name, rows, up_map)


def _stats(trades, title):
    print(f"\n>> {title}")
    if not trades:
        print("  无交易")
        return
    rs = [t["ret"] for t in trades]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    aw = statistics.mean(wins) if wins else 0.0
    al = statistics.mean(losses) if losses else 0.0
    print(
        f"  笔数 {len(rs)}  胜率 {len(wins)/len(rs)*100:.1f}%  "
        f"均值 {statistics.mean(rs)*100:+.2f}%  中位 {statistics.median(rs)*100:+.2f}%"
    )
    print(
        f"  平均盈利 {aw*100:+.2f}% / 平均亏损 {al*100:+.2f}%  "
        f"盈亏比 {aw/abs(al) if al else float('inf'):.2f}  "
        f"平均持有 {statistics.mean(t['held'] for t in trades):.1f}天"
    )
    print(f"  最好/最差 {max(rs)*100:+.1f}% / {min(rs)*100:+.1f}%")
    by_reason = {}
    for t in trades:
        by_reason.setdefault(t.get("reason", "?"), []).append(t["ret"])
    print("  出场:")
    for reason, vals in sorted(by_reason.items(), key=lambda x: -len(x[1])):
        print(
            f"    {reason:<12} {len(vals):>4}笔  "
            f"胜率 {sum(1 for v in vals if v>0)/len(vals)*100:5.1f}%  "
            f"均值 {statistics.mean(vals)*100:+.2f}%"
        )


def main():
    os.environ.setdefault("CACHE_ONLY", "1")
    U = cache_data.universe()
    up_map = market_up_map()
    print(
        f"策略十二(胜率调优) vs 策略三  池={len(U)}  {START}~{END}  "
        f"BIAS_MAX={BIAS_MAX} CLOSE_POS>={CLOSE_POS_MIN} 出场=MA5",
        flush=True,
    )
    s3, s12 = [], []
    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(run_one, item, up_map) for item in U]
        for fut in as_completed(futs):
            done += 1
            try:
                a, b = fut.result()
                s3.extend(a)
                s12.extend(b)
            except Exception:
                pass
            if done % 500 == 0:
                print(f"  {done}/{len(U)}  s3={len(s3)} s12={len(s12)}", flush=True)

    _stats(s3, f"策略三·回踩破MA20  {START}~{END}")
    _stats(
        s12,
        f"策略十二·上穿+排列+bias≤{BIAS_MAX*100:.0f}%+pos≥{CLOSE_POS_MIN}+破MA5  {START}~{END}",
    )

    def brief(ts):
        if not ts:
            return "0笔"
        rs = [t["ret"] for t in ts]
        return (
            f"{len(rs)}笔  胜率{sum(1 for r in rs if r>0)/len(rs)*100:.1f}%  "
            f"均值{statistics.mean(rs)*100:+.2f}%  中位{statistics.median(rs)*100:+.2f}%"
        )

    print("\n===== 对照摘要 =====")
    print(f"  策略三   {brief(s3)}")
    print(f"  策略十二 {brief(s12)}")


if __name__ == "__main__":
    main()
