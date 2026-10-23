#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中证2000连小阳 · AkShare 资金曲线年化。

入场: 连小阳边缘触发 → 次日开盘
离场: 放量≥VOL_MULT×窗均量 / 破窗低止损 / 超时MAX_HOLD
组合: 等权 N_SLOTS 槽位（默认匹配小资金少持仓）
"""
from __future__ import annotations

import csv
import math
import os
import statistics
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

os.environ.setdefault("AKSHARE_DATA_DIR", str(HERE / "data_akshare"))
os.environ["ABC_DATA_SOURCE"] = "akshare"

import akshare_data as ad  # noqa: E402

START = os.environ.get("START", "2020-01-02")
END = os.environ.get("END", "2026-07-29")
INIT = float(os.environ.get("INIT", "10000"))
N_SLOTS = int(os.environ.get("N_SLOTS", "4"))
COST = float(os.environ.get("COST", "0.001"))
MAX_HOLD = int(os.environ.get("MAX_HOLD", "15"))
VOL_MULT = float(os.environ.get("VOL_MULT", "2.0"))
STOP_BELOW = float(os.environ.get("STOP_BELOW", "0.97"))
COOLDOWN = int(os.environ.get("COOLDOWN", "5"))
WINDOW = 8
MIN_YANG, MIN_STREAK = 6, 5
MAX_BODY, MAX_CHG = 3.5, 4.0
MIN_NET, MAX_NET = 2.0, 25.0
TIER = int(os.environ.get("YANG_TIER", "0"))  # 0全量 2/3档
CSI_PATH = HERE / "data_cache" / "csi2000_cons.csv"
WORKERS = int(os.environ.get("SIM_WORKERS", "8"))


def secid_of(code: str) -> str:
    return ("1." if code.startswith("6") else "0.") + code


def load_universe():
    rows = []
    with CSI_PATH.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            code = (r.get("成分券代码") or "").strip()
            name = (r.get("成分券名称") or "").strip()
            if not code or code.startswith(("3", "688", "8", "4", "9")):
                continue
            if not (code.startswith("0") or code.startswith("6")):
                continue
            if "ST" in name or "退" in name or "PT" in name:
                continue
            rows.append((code, name, secid_of(code)))
    return rows


def signal_at(rows, i):
    w = WINDOW
    if i < max(w, 20) or i >= len(rows):
        return None
    d = rows[i][0]
    if not (START <= d <= END):
        return None
    win = rows[i - w + 1 : i + 1]
    prev_closes = [float(rows[i - w + k][2]) for k in range(w)]
    yang_flags, small_flags, bodies, chgs, vols = [], [], [], [], []
    for k, r in enumerate(win):
        o, c = float(r[1]), float(r[2])
        pc = prev_closes[k]
        body = (c - o) / o * 100.0 if o else 0.0
        chg = (c / pc - 1.0) * 100.0 if pc else 0.0
        bodies.append(body)
        chgs.append(chg)
        vols.append(float(r[5]))
        is_yang = c > o
        yang_flags.append(is_yang)
        small_flags.append(is_yang and 0 < body <= MAX_BODY and chg <= MAX_CHG)
    yang_n = sum(yang_flags)
    small_n = sum(small_flags)
    streak = 0
    for y in reversed(yang_flags):
        if y:
            streak += 1
        else:
            break
    c0, c1 = prev_closes[0], float(win[-1][2])
    net = (c1 / c0 - 1.0) * 100.0 if c0 else 0.0
    max_chg = max(chgs) if chgs else 0.0
    avg_chg = sum(chgs) / len(chgs)
    avg_body = sum(bodies) / len(bodies)
    vol_base = sum(vols) / len(vols) if vols else 0.0
    win_low = min(float(r[4]) for r in win)
    if streak < MIN_STREAK or yang_n < MIN_YANG:
        return None
    if small_n < max(MIN_YANG - 1, MIN_STREAK - 1):
        return None
    if not (MIN_NET <= net <= MAX_NET):
        return None
    if max_chg > MAX_CHG + 1.5 or avg_chg > 2.8 or avg_body > 2.5:
        return None
    if vol_base <= 0:
        return None
    ret20 = (c1 / float(rows[i - 20][2]) - 1.0) * 100.0 if rows[i - 20][2] else 0.0
    amt = float(rows[i][6]) / 1e8
    if TIER == 2:
        if net > 8 or ret20 >= 0 or not (0.3 <= amt < 1.2):
            return None
    elif TIER == 3:
        if net > 8 or ret20 >= 5 or not (0.3 <= amt < 1.0):
            return None
    return {
        "date": d,
        "streak": streak,
        "small_n": small_n,
        "net": net,
        "ret20": ret20,
        "amt": amt,
        "vol_base": vol_base,
        "win_low": win_low,
    }


def is_new_signal(rows, i):
    cur = signal_at(rows, i)
    if not cur or signal_at(rows, i - 1):
        return None
    return cur


def exit_trade(rows, buy_i, sig):
    C = [float(r[2]) for r in rows]
    L = [float(r[4]) for r in rows]
    V = [float(r[5]) for r in rows]
    O = [float(r[1]) for r in rows]
    base = sig["vol_base"]
    stop = sig["win_low"] * STOP_BELOW
    end = min(len(rows) - 1, buy_i + MAX_HOLD)
    for j in range(buy_i, end + 1):
        if O[j] <= stop:
            return j, O[j], "stop_open"
        if L[j] <= stop:
            return j, stop, "stop"
        if V[j] >= VOL_MULT * base:
            return j, C[j], "vol_spike"
    return end, C[end], "timeout"


def run_one(item):
    code, name, secid = item
    rows = ad.daily_kline(secid)
    if not rows or len(rows) < WINDOW + 25:
        return []
    # akshare rows are list[list] already
    out = []
    next_ok = max(WINDOW, 20)
    i = next_ok
    while i < len(rows) - 2:
        if i < next_ok:
            i += 1
            continue
        sig = is_new_signal(rows, i)
        if not sig:
            i += 1
            continue
        buy_i = i + 1
        if buy_i >= len(rows):
            break
        entry_px = float(rows[buy_i][1])
        if entry_px <= 0:
            i += 1
            continue
        sell_i, sell_px, reason = exit_trade(rows, buy_i, sig)
        held = sell_i - buy_i + 1
        # 样本末截断不计入
        if reason == "timeout" and held < MAX_HOLD and rows[sell_i][0] >= END:
            break
        if rows[buy_i][0] > END:
            break
        ret = sell_px / entry_px - 1.0 - COST
        out.append({
            "code": code,
            "name": name,
            "signal": sig["date"],
            "entry": rows[buy_i][0],
            "exit": rows[sell_i][0],
            "ret": ret,
            "reason": reason,
            "held": held,
            "streak": sig["streak"],
            "rank": sig["streak"] * 10 + sig["small_n"],
        })
        next_ok = sell_i + 1 + COOLDOWN
        i = buy_i + 1
    return out


def simulate(trades):
    """仅在信号入场日开仓；用全市场交易日推进，空仓日也计入曲线。"""
    if not trades:
        return None
    from datetime import datetime

    # 交易日历: 参考平安银行
    cal_rows = ad.daily_kline("0.000001") or []
    calendar = [r[0] for r in cal_rows if START <= r[0] <= END]
    if not calendar:
        calendar = sorted({t["entry"] for t in trades} | {t["exit"] for t in trades})

    by_entry = defaultdict(list)
    for t in trades:
        by_entry[t["entry"]].append(t)

    cash, positions, curve, taken = INIT, [], [], 0
    closed_rets = []
    for day in calendar:
        keep = []
        for pos in positions:
            if pos["exit"] == day:
                cash += pos["cap"] * (1 + pos["ret"])
                closed_rets.append(pos["ret"])
            else:
                keep.append(pos)
        positions = keep
        held = {p["code"] for p in positions}
        equity = cash + sum(p["cap"] for p in positions)
        for trade in sorted(
            by_entry.get(day, []),
            key=lambda t: (-t.get("rank", 0), t["code"]),
        ):
            if len(positions) >= N_SLOTS or cash <= 50:
                break
            if trade["code"] in held:
                continue
            if trade["exit"] <= day:
                continue
            commit = min(equity / N_SLOTS, cash)
            if commit < 50:
                break
            cash -= commit
            positions.append({
                "code": trade["code"],
                "exit": trade["exit"],
                "cap": commit,
                "ret": trade["ret"],
            })
            held.add(trade["code"])
            taken += 1
        curve.append({"date": day, "equity": cash + sum(p["cap"] for p in positions)})
    final = cash + sum(p["cap"] for p in positions)
    peak, mdd = INIT, 0.0
    for pt in curve:
        peak = max(peak, pt["equity"])
        if peak > 0:
            mdd = max(mdd, (peak - pt["equity"]) / peak)
    if len(curve) >= 2:
        d0, d1 = curve[0]["date"], curve[-1]["date"]
        t0 = datetime.strptime(d0, "%Y-%m-%d")
        t1 = datetime.strptime(d1, "%Y-%m-%d")
        years = max((t1 - t0).days / 365.25, 1 / 365.25)
        total = final / INIT - 1
        cagr = (final / INIT) ** (1 / years) - 1 if final > 0 else -1.0
    else:
        years, total, cagr = 0, 0, 0
    rs = [t["ret"] for t in trades]
    return {
        "final": round(final, 2),
        "total_ret": total,
        "cagr": cagr,
        "years": years,
        "mdd": mdd,
        "signals": len(trades),
        "taken": taken,
        "slot_win": sum(1 for r in closed_rets if r > 0) / len(closed_rets) if closed_rets else 0,
        "sig_win": sum(1 for r in rs if r > 0) / len(rs) if rs else 0,
        "avg_sig": statistics.mean(rs) if rs else 0,
        "curve": curve,
        "start": curve[0]["date"] if curve else "",
        "end": curve[-1]["date"] if curve else "",
    }


def collect_trades(uni):
    trades = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(run_one, it) for it in uni]
        for n, fut in enumerate(as_completed(futs), 1):
            try:
                trades.extend(fut.result() or [])
            except Exception:
                pass
            if n % 300 == 0 or n == len(futs):
                print(f"  scan {n}/{len(futs)} trades={len(trades)}", flush=True)
    return trades


def main():
    uni = load_universe()
    # 仅保留 akshare 有数据的
    uni = [it for it in uni if ad.daily_kline(it[2])]
    tier_name = {0: "全量", 2: "2档未涨透", 3: "3档温和未透"}.get(TIER, str(TIER))
    print(
        f"AkShare连小阳年化 | {tier_name} | 池{len(uni)} | "
        f"{START}~{END} | 本金{INIT:.0f} | 槽位{N_SLOTS} | VOL≥{VOL_MULT}x",
        flush=True,
    )
    trades = collect_trades(uni)
    # 按年拆信号胜率
    by_year = defaultdict(list)
    for t in trades:
        by_year[t["entry"][:4]].append(t["ret"])
    print("\n[信号层 按年]")
    for y in sorted(by_year):
        rs = by_year[y]
        print(
            f"  {y}  {len(rs):>5}笔  胜{sum(r>0 for r in rs)/len(rs)*100:5.1f}%  "
            f"均{statistics.mean(rs)*100:+6.2f}%"
        )
    sim = simulate(trades)
    if not sim:
        print("无交易"); return
    print(
        f"\n[组合资金曲线] {sim['start']}→{sim['end']} ({sim['years']:.2f}年)\n"
        f"  本金 {INIT:.0f} → 期末 {sim['final']:.0f}\n"
        f"  总收益 {sim['total_ret']*100:+.1f}%\n"
        f"  年化CAGR {sim['cagr']*100:+.1f}%\n"
        f"  最大回撤 {sim['mdd']*100:.1f}%\n"
        f"  信号 {sim['signals']} / 实际开仓 {sim['taken']}\n"
        f"  信号胜率 {sim['sig_win']*100:.1f}%  均{sim['avg_sig']*100:+.2f}%\n"
        f"  槽位平仓胜率 {sim['slot_win']*100:.1f}%"
    )
    out = HERE / "data_cache" / f"akshare_small_yang_tier{TIER}_sim.json"
    payload = {k: v for k, v in sim.items() if k != "curve"}
    payload["tier"] = TIER
    payload["init"] = INIT
    payload["n_slots"] = N_SLOTS
    payload["source"] = "akshare"
    with out.open("w", encoding="utf-8") as f:
        import json
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\n摘要已写 {out}")


if __name__ == "__main__":
    main()
