#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""策略十·缠论完备体系 —— 全市场回测。

一句话: 大级别不做下跌(操作级别铁律) -> 日线三类买卖点进场 -> 按利润最大定理出场。

出场遵循 70c/70d 两套官方操作模式, 用 PROFIT_MODE 切换:
  PROFIT_MODE=1 第一利润最大(70c, 守株): 三买后持股, 直到本级别背驰(一卖)才清仓。
  PROFIT_MODE=2 第二利润最大(70d, 轮动): 不参与中枢震荡, **一旦走出新中枢就撤**,
                把资金调去下一个买点。

止损全部是**结构止损**, 不是拍脑袋的百分比:
  三买 -> 跌破 ZG(中枢上沿失守 = 三买证伪, 中枢在扩展而不是结束)
  一/二买 -> 跌破买点低点(背驰底被打穿 = 背驰失败)
另叠一道 HARD_STOP 作为极端行情的兜底。
"""
import os
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))
os.environ.setdefault("MA_CACHE_DIR", str(_HERE.parent / "data_cache"))

import cache_data  # noqa: E402
import chan  # noqa: E402
import signals as sg  # noqa: E402

START = os.environ.get("START", "2025-07-01")
END = os.environ.get("END", "2026-06-26")
COST = 0.001
MAX_HOLD = int(os.environ.get("MAX_HOLD", "60"))
HARD_STOP = float(os.environ.get("HARD_STOP", "0.08"))
STOP_TOL = float(os.environ.get("STOP_TOL", "0.005"))   # 结构位下方的毛刺容忍
MIN_AMOUNT = float(os.environ.get("MIN_AMOUNT", "50000000"))
GAP_LIMIT = float(os.environ.get("GAP_LIMIT", "0.20"))  # 单日跳空超此=拆分/脏数据, 丢弃
PROFIT_MODE = int(os.environ.get("PROFIT_MODE", "1"))
# 出场(均叠结构止损+兜底硬止损): fractal=顶分型卖 | chan=纯缠论一卖/三卖 | trail=移动止损
#         ma5=收盘破5日线即卖 | ma5x2=连2日破5日线才卖(策略二口径, 容忍1天)
EXIT_MODE = os.environ.get("EXIT_MODE", "fractal")
LAUNCH_RET = float(os.environ.get("LAUNCH_RET", "0.05"))
TRAIL_PCT = float(os.environ.get("TRAIL_PCT", "0.08"))
ONLY_TYPE = os.environ.get("ONLY_TYPE", "")             # "1"/"2"/"3" 只回测某一类买点
ETF_ONLY = os.environ.get("ETF_ONLY", "0") != "0"
INCLUDE_ETF = os.environ.get("INCLUDE_ETF", "0") != "0"


def _ma(C, p):
    out, s = [None] * len(C), 0.0
    for i, c in enumerate(C):
        s += c
        if i >= p:
            s -= C[i - p]
        if i >= p - 1:
            out[i] = s / p
    return out


def struct_stop(rec):
    """结构止损位: 买点赖以成立的那个结构一旦被打穿, 买点就不存在了。

    三买破 ZG = 中枢没结束、在扩展; 一/二买破买点低点 = 背驰底被打穿、背驰失败。
    """
    base = min(rec["low"], rec["zg"]) if rec["type"] == 3 else rec["low"]
    return base * (1 - STOP_TOL)


def exit_trade(rows, i, rec):
    O = [float(r[1]) for r in rows]
    C = [float(r[2]) for r in rows]
    H = [float(r[3]) for r in rows]
    L = [float(r[4]) for r in rows]
    entry = C[i]
    stop = struct_stop(rec)
    hard = entry * (1 - HARD_STOP)
    end = min(len(rows) - 1, i + MAX_HOLD)
    worst, launched, peak = 0.0, False, H[i]
    m5 = _ma(C, 5) if EXIT_MODE.startswith("ma5") else None
    for j in range(i + 1, end + 1):
        if C[j - 1] > 0 and abs(O[j] / C[j - 1] - 1) > GAP_LIMIT:
            return j, 0.0, "split", worst
        worst = min(worst, L[j] / entry - 1)
        # 兜底硬止损(盘中): 防极端单日崩塌, 与结构无关。
        if O[j] <= hard:
            return j, O[j], "hard_open", worst
        if L[j] <= hard:
            return j, hard, "hard", worst
        if EXIT_MODE == "trail" and launched:
            t = peak * (1 - TRAIL_PCT)
            if O[j] <= t:
                return j, O[j], "trail_open", worst
            if L[j] <= t:
                return j, t, "trail", worst
        # 结构止损用**收盘**确认: 缠论看的是结构被破坏, 不是盘中一根影线的毛刺。
        if C[j] < stop:
            return j, C[j], "struct_break", worst
        st = chan.build(rows, j + 1)
        if st:
            sp = sg.sell_point(st)
            if sp:
                # 卖点优先级铁律: 一卖 > 二卖 > 三卖, 出现即走。
                return j, C[j], "一卖" if sp["type"] == -1 else "三卖", worst
            if PROFIT_MODE == 2 and any(p["si"] > i for p in st["ps"]):
                # 70d 激进模式: 走出新中枢 = 要进入磨人的中枢震荡, 立刻换股。
                return j, C[j], "new_pivot", worst
        # 沿5日线跟踪(策略二口径): 收盘跌破 MA5 卖出。ma5x2 = 容忍1天, 连2日破才卖。
        if m5 is not None and m5[j] is not None and C[j] < m5[j]:
            if EXIT_MODE == "ma5":
                return j, C[j], "ma5_break", worst
            if m5[j - 1] is not None and C[j - 1] < m5[j - 1]:
                return j, C[j], "ma5_break2", worst
        # 顶分型卖(策略五个股版实测最优的出场): 第 j 根收盘才能确认 j-1 是顶分型。
        if EXIT_MODE == "fractal" and j >= i + 2:
            if H[j - 1] > H[j - 2] and H[j - 1] > H[j] and L[j - 1] > L[j - 2] and L[j - 1] > L[j]:
                return j, C[j], "top_fractal", worst
        if C[j] / entry - 1 >= LAUNCH_RET:
            launched = True
        peak = max(peak, H[j])
    return end, C[end], "timeout", worst


def run_one(code, name, secid, rows=None):
    rows = rows if rows is not None else cache_data.daily_kline(secid)
    if not rows or len(rows) < 130:
        return []
    D = [r[0] for r in rows]
    A = [float(r[6]) for r in rows]
    out = []
    i, n = 110, len(rows)
    while i < n - 2:
        if not (START <= D[i] <= END) or A[i] < MIN_AMOUNT:
            i += 1
            continue
        st = chan.build(rows, i + 1)
        rec = sg.buy_point(st) if st else None
        if not rec or (ONLY_TYPE and str(rec["type"]) != ONLY_TYPE):
            i += 1
            continue
        if not sg.big_level_ok(rows[: i + 1]):
            i += 1
            continue
        j, sell, reason, mae = exit_trade(rows, i, rec)
        if reason == "split":
            i = j + 1
            continue
        rec.update({
            "date": D[i], "code": code, "name": name, "entry": float(rows[i][2]),
            "exit": D[j], "held": j - i, "reason": reason, "mae": mae,
        })
        rec["ret"] = sell / rec["entry"] - 1 - COST
        rec["pos"] = sg.POSITION[rec["type"]]
        out.append(rec)
        i = j + 1
    return out


def simulate(trades, slots):
    by = {}
    for t in sorted(trades, key=lambda x: (-x["pos"], x["code"])):
        by.setdefault(t["date"], []).append(t)
    days = sorted(set([t["date"] for t in trades] + [t["exit"] for t in trades]))
    cash, pos, curve = 1.0, [], []
    for dt in days:
        keep = []
        for p in pos:
            if p["exit"] == dt:
                cash += p["cap"] * (1 + p["ret"])
            else:
                keep.append(p)
        pos = keep
        held = {p["code"] for p in pos}
        eq = cash + sum(p["cap"] for p in pos)
        for t in by.get(dt, []):
            if len(pos) >= slots or cash <= 1e-9 or t["code"] in held:
                continue
            cap = min(eq / slots, cash)
            cash -= cap
            pos.append({"code": t["code"], "exit": t["exit"], "cap": cap, "ret": t["ret"]})
            held.add(t["code"])
        curve.append(cash + sum(p["cap"] for p in pos))
    if not curve:
        return 0.0, 0.0
    peak, mdd = curve[0], 0.0
    for v in curve:
        peak = max(peak, v)
        mdd = max(mdd, (peak - v) / peak)
    return curve[-1] - 1, mdd


def _line(label, ts):
    rs = [t["ret"] for t in ts]
    return (f"  {label:<16} {len(ts):>5}笔  胜率 {sum(1 for r in rs if r > 0)/len(rs)*100:5.1f}%  "
            f"均值 {statistics.mean(rs)*100:+6.2f}%  中位 {statistics.median(rs)*100:+6.2f}%  "
            f"MAE {statistics.mean(t['mae'] for t in ts)*100:+6.2f}%")


def summarize(trades):
    mode = "第一利润最大(持股到背驰)" if PROFIT_MODE == 1 else "第二利润最大(新中枢即撤)"
    print(f"\n>> 策略十·缠论完备体系 {START}~{END}  {mode}  交易 {len(trades)} 笔\n")
    if not trades:
        print("无信号。")
        return
    print(_line("整体", trades))
    print(f"  平均持有 {statistics.mean(t['held'] for t in trades):.1f}天  "
          f"最好/最差 {max(t['ret'] for t in trades)*100:+.1f}%/{min(t['ret'] for t in trades)*100:+.1f}%")

    for title, key in (("按买点类型", "kind"), ("按出场", "reason")):
        g = {}
        for t in trades:
            g.setdefault(t[key], []).append(t)
        print(f"\n{title}:")
        for k, v in sorted(g.items(), key=lambda x: -len(x[1])):
            print(_line(k, v))

    three = [t for t in trades if t["type"] == 3]
    if three:
        print("\n三买按中枢序号(验证'第一个中枢最稳'):")
        g = {}
        for t in three:
            g.setdefault(t["stage"], []).append(t)
        for k, v in sorted(g.items()):
            print(_line(f"第{k}个中枢", v))

    td = [t for t in trades if t["type"] == 1]
    if td:
        print("\n一买按背驰级别(验证'趋势背驰 > 盘整背驰'):")
        g = {}
        for t in td:
            g.setdefault("趋势背驰" if t.get("trend_div") else "盘整背驰", []).append(t)
        for k, v in sorted(g.items()):
            print(_line(k, v))

    g = {}
    for t in trades:
        g.setdefault(min(4, t["held"] // 5), []).append(t)
    print("\n按持有天数:")
    for k, v in sorted(g.items()):
        print(_line(f"{k*5}-{k*5+4}天" if k < 4 else "20天以上", v))
    print("\n最近15笔:")
    for t in sorted(trades, key=lambda x: x["date"])[-15:]:
        print(f"{t['date']} {t['code']} {t['name'][:6]:<6} {t['kind']:<12} "
              f"entry={t['entry']:.2f} exit={t['exit']} {t['reason']:<10} ret={t['ret']*100:+.1f}%")


def main():
    if ETF_ONLY:
        U = cache_data.etf_universe()
    else:
        U = cache_data.universe()
        if INCLUDE_ETF:
            U = U + cache_data.etf_universe()
    print(f"标的池 {len(U)} 只, 策略十回测中 (PROFIT_MODE={PROFIT_MODE} "
          f"EXIT={EXIT_MODE} WEEKLY={sg.WEEKLY_MODE} TYPES={ONLY_TYPE or sg.ENABLE_TYPES})...", flush=True)
    trades, done = [], 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(run_one, c, n, s): c for c, n, s in U}
        for fut in as_completed(futs):
            done += 1
            try:
                trades.extend(fut.result())
            except Exception:
                pass
            if done % 500 == 0:
                print(f"  {done}/{len(U)} 交易{len(trades)}", flush=True)
    summarize(trades)


if __name__ == "__main__":
    main()
