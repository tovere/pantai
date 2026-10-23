#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""策略5/7/10/11 · 各10万 · 2024-01-02~2026-07-29 资金曲线 (AkShare本地库 + 多进程)。"""
from __future__ import annotations

import json
import os
import statistics
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "strategy_chan_final"))

os.environ.setdefault("AKSHARE_DATA_DIR", str(HERE / "data_akshare"))
os.environ["ABC_DATA_SOURCE"] = "akshare"

START = "2024-01-02"
END = "2026-07-29"
INIT = 100_000.0
N_SLOTS = 5
COST = 0.001
OUT = HERE / "data_cache" / "sim_capital_2024_s571011.json"
WORKERS = int(os.environ.get("SIM_WORKERS", "8"))


def secid_of(code: str) -> str:
    return ("1." if code.startswith("6") else "0.") + code


def stock_universe():
    import akshare_data as ad
    items = ad.universe("stock")
    return list({it["code"]: (it["code"], it.get("name") or it["code"], secid_of(it["code"])) for it in items}.values())


def rows_of(secid: str):
    import akshare_data as ad
    return ad.daily_kline(secid) or []


def build_up_map():
    rows = rows_of("1.510300")
    closes = [float(r[2]) for r in rows]
    dates = [r[0] for r in rows]
    out = {}
    for i in range(60, len(rows)):
        ma20 = sum(closes[i - 19 : i + 1]) / 20
        ma60 = sum(closes[i - 59 : i + 1]) / 60
        ret20 = closes[i] / closes[i - 20] - 1 if closes[i - 20] else 0
        out[dates[i]] = bool(closes[i] >= ma20 and closes[i] >= ma60 and ret20 >= 0)
    return out


def simulate(trades):
    if not trades:
        return {"final": INIT, "ret": 0.0, "mdd": 0.0, "n": 0, "taken": 0, "win": 0.0, "avg": 0.0, "curve": []}
    by_entry = defaultdict(list)
    for t in trades:
        by_entry[t["entry"]].append(t)
    days = sorted({t["entry"] for t in trades} | {t["exit"] for t in trades})
    cash, positions, curve, taken = INIT, [], [], 0
    for day in days:
        keep = []
        for pos in positions:
            if pos["exit"] == day:
                cash += pos["cap"] * (1 + pos["ret"])
            else:
                keep.append(pos)
        positions = keep
        held = {p["code"] for p in positions}
        equity = cash + sum(p["cap"] for p in positions)
        for trade in sorted(by_entry.get(day, []), key=lambda t: (-t.get("rank", 0), t.get("risk", 9), t["code"])):
            if len(positions) >= N_SLOTS or cash <= 1e-6:
                break
            if trade["code"] in held:
                continue
            commit = min(equity / N_SLOTS, cash)
            if commit < 100:
                break
            cash -= commit
            positions.append({"code": trade["code"], "exit": trade["exit"], "cap": commit, "ret": trade["ret"]})
            held.add(trade["code"])
            taken += 1
        curve.append({"date": day, "equity": round(cash + sum(p["cap"] for p in positions), 2)})
    final = cash + sum(p["cap"] for p in positions)
    peak, mdd = INIT, 0.0
    for pt in curve:
        peak = max(peak, pt["equity"])
        if peak > 0:
            mdd = max(mdd, (peak - pt["equity"]) / peak)
    rets = [t["ret"] for t in trades]
    step = max(1, len(curve) // 100)
    return {
        "final": round(final, 2), "ret": final / INIT - 1, "mdd": mdd,
        "n": len(trades), "taken": taken,
        "win": sum(1 for r in rets if r > 0) / len(rets) if rets else 0,
        "avg": statistics.mean(rets) if rets else 0,
        "curve": curve[::step],
    }


UP_MAP = {}


def _init_worker(up_path: str):
    global UP_MAP
    with open(up_path, encoding="utf-8") as f:
        UP_MAP = json.load(f)


def _pool_map(fn, universe, label, up_path):
    trades = []
    with ProcessPoolExecutor(
        max_workers=WORKERS, initializer=_init_worker, initargs=(up_path,)
    ) as ex:
        futs = [ex.submit(fn, it) for it in universe]
        for n, fut in enumerate(as_completed(futs), 1):
            try:
                trades.extend(fut.result() or [])
            except Exception as exc:
                if n <= 3:
                    print(f"  WARN {label}: {type(exc).__name__}: {exc}", flush=True)
            if n % 400 == 0 or n == len(futs):
                print(f"  {label} {n}/{len(futs)} trades={len(trades)}", flush=True)
    return trades


# ---- workers (import inside for fresh env) ----

def worker_s5(item):
    os.environ.update({
        "AKSHARE_DATA_DIR": str(HERE / "data_akshare"),
        "STRICT_BUY": "0", "S5_STAGE1_ONLY": "1", "S5_MAX_DIST": "5",
        "S5_MAX_SHRINK": "0.50", "S5_MAX_RISK": "4", "S5_MIN_PULL": "2",
        "EXIT_MODE": "fractal", "ABC_DATA_SOURCE": "akshare",
    })
    import backtest_chan_wyckoff_3buy as bt
    import screen_chan_wyckoff_3buy as sig
    import akshare_data as ad

    bt.START, bt.END, bt.COST, bt.EXIT_MODE, bt.STRICT = START, END, COST, "fractal", False
    sig.kline = ad.daily_kline
    code, name, secid = item
    rows = ad.daily_kline(secid) or []
    if len(rows) < 110:
        return []
    up = UP_MAP
    O = [float(r[1]) for r in rows]
    C = [float(r[2]) for r in rows]
    out = []
    for i in range(90, len(rows) - 3):
        d = rows[i][0]
        if not (START <= d <= END) or not up.get(d):
            continue
        rec = bt.signal_at(code, name, rows, i)
        if not rec:
            continue
        if bt._has_gap(O, C, i - 70, i):
            continue
        if int(rec.get("stage", 1)) != 1:
            continue
        if float(rec.get("dist", 99)) > 5 or float(rec.get("vol_shrink", 99)) > 0.50:
            continue
        risk = (float(rec["entry"]) / float(rec["buy_low"]) - 1) * 100
        if risk > 4 or int(rec.get("pull_days", 0)) < 2:
            continue
        j, sell, reason, mae = bt.exit_trade(rows, i, rec)
        if reason == "split":
            continue
        out.append({
            "code": code, "name": name, "entry": d, "exit": rows[j][0],
            "ret": sell / rec["entry"] - 1 - COST, "risk": risk,
            "rank": 2 if rec["dist"] <= 3.5 and rec["vol_shrink"] <= 0.45 else 1,
        })
    return out


def worker_s7(item):
    os.environ.update({
        "AKSHARE_DATA_DIR": str(HERE / "data_akshare"),
        "ABC_DATA_SOURCE": "akshare", "EXIT_MODE": "low_ma5",
        "START": START, "END": END,
    })
    import backtest_oversold_volume_2buy as s7
    import akshare_data as ad

    s7.START, s7.END, s7.EXIT_MODE, s7.COST = START, END, "low_ma5", COST
    s7.history_data = ad
    out = []
    for t in s7.run_one(item):
        out.append({
            "code": t["code"], "name": t.get("name", ""),
            "entry": t["date"], "exit": t["exit"], "ret": t["ret"],
            "risk": abs(float(t.get("mae") or 0)) * 100, "rank": 1,
        })
    return out


def worker_s10(item):
    os.environ.update({
        "AKSHARE_DATA_DIR": str(HERE / "data_akshare"),
        "ENABLE_TYPES": "3", "WEEKLY_MODE": "ma", "PULLBACK_GG": "0",
        "EXIT_MODE": "fractal", "ONLY_TYPE": "3",
        "START": START, "END": END,
    })
    import chan
    import signals as sg
    import strategy_chan_final.backtest as s10
    import akshare_data as ad

    s10.START, s10.END, s10.COST, s10.EXIT_MODE, s10.ONLY_TYPE = START, END, COST, "fractal", "3"
    up = UP_MAP
    code, name, secid = item
    rows = ad.daily_kline(secid) or []
    if len(rows) < 130:
        return []
    D = [r[0] for r in rows]
    A = [float(r[6]) for r in rows]
    out = []
    i, n = 110, len(rows)
    while i < n - 2:
        d = D[i]
        if not (START <= d <= END) or A[i] < 5e7 or not up.get(d):
            i += 1
            continue
        st = chan.build(rows, i + 1)
        rec = sg.buy_point(st) if st else None
        if not rec or rec.get("type") != 3 or not sg.big_level_ok(rows[: i + 1]):
            i += 1
            continue
        stage = int(rec.get("stage") or 0)
        lag = int(rec.get("lag") or 99)
        entry = float(rows[i][2])
        stop = min(float(rec.get("low") or entry), float(rec.get("zg") or entry))
        risk = (entry / stop - 1) * 100 if stop else 99
        if stage != 1 or lag > 2 or risk > 12:
            i += 1
            continue
        j, sell, reason, mae = s10.exit_trade(rows, i, rec)
        if reason == "split":
            i = j + 1
            continue
        out.append({
            "code": code, "name": name, "entry": d, "exit": D[j],
            "ret": sell / entry - 1 - COST, "risk": risk,
            "rank": 2 if lag == 2 else 1,
        })
        i = j + 1
    return out


def worker_s11(item):
    os.environ.update({
        "AKSHARE_DATA_DIR": str(HERE / "data_akshare"),
        "STRICT_BUY": "0", "MIN_MKTCAP": "20000000000",
        "VDB_SHRINK": "0.50", "VDB_LOOSE_DIST": "6",
        "VDB_MIN_RET20": "0", "VDB_EXCLUDE_REV": "1",
        "STOP_MODE": "close", "START": START, "END": END,
    })
    import vdb_pullback as sig
    import backtest_vdb_pullback as s11
    import akshare_data as ad

    s11.START, s11.END, s11.COST = START, END, COST
    code, name, secid = item
    rows = ad.daily_kline(secid) or []
    if len(rows) < 110:
        return []
    out = []
    for i in range(90, len(rows) - 3):
        d = rows[i][0]
        if not (START <= d <= END):
            continue
        rec = sig.signal_at(code, name, rows, i)
        if not rec:
            continue
        j, sell, reason, mae = s11.exit_trade(rows, i, rec)
        if reason == "split":
            continue
        entry = float(rec["entry"])
        dist = float(rec.get("dist_vdb") or 99)
        shrink = float(rec.get("vol_shrink") or 99)
        out.append({
            "code": code, "name": name, "entry": d, "exit": rows[j][0],
            "ret": sell / entry - 1 - COST, "risk": dist,
            "rank": 2 if dist <= 4 else 1 if shrink <= 0.45 else 0,
        })
    return out


def main():
    import akshare_data as ad
    print(f"AkShare root={ad.ROOT}", flush=True)
    print(f"区间 {START}~{END}  初始{INIT:.0f}/策略  {N_SLOTS}仓  workers={WORKERS}", flush=True)
    up = build_up_map()
    uni = stock_universe()
    up_path = HERE / "data_cache" / "_sim_up_map.json"
    up_path.parent.mkdir(parents=True, exist_ok=True)
    up_path.write_text(json.dumps(up), encoding="utf-8")
    print(f"上涨市日 {sum(1 for v in up.values() if v)}/{len(up)}  股票池 {len(uni)}", flush=True)

    results = {}
    specs = [
        ("s5", "策略五·个股·宽松调优", "首中枢+距≤5+缩≤0.50+risk≤4+pull≥2+上涨市·顶分型", worker_s5),
        ("s7", "策略七·超跌放量回踩二买", "L2止损+涨6%后MA5保护", worker_s7),
        ("s10", "策略十·个股·缠论三买", "首中枢+lag≤2+risk≤12+上涨市·顶分型", worker_s10),
        ("s11", "策略十一·VDB缩量回踩·宽松", "≥200亿+缩≤0.50+距≤6+ret20≥0+剔反转", worker_s11),
    ]
    for key, title, note, fn in specs:
        print(f"\n=== {key.upper()} ===", flush=True)
        trades = _pool_map(fn, uni, key.upper(), str(up_path))
        sim = simulate(trades)
        results[key] = {"title": title, "note": note, **sim}
        print(
            f"  → 终值 {sim['final']:,.0f} ({sim['ret']*100:+.1f}%) "
            f"MDD{sim['mdd']*100:.1f}% 信号{sim['n']}/接单{sim['taken']}",
            flush=True,
        )

    payload = {
        "start": START, "end": END, "init": INIT, "n_slots": N_SLOTS, "cost": COST,
        "source": "akshare:data_akshare",
        "assumptions": [
            "每策略独立初始10万, 互不共享",
            "5仓等权, 同日信号有限接单",
            "口径=盯盘台当前个股调优版(非ETF)",
            "S5/S10仅上涨市入场",
            "往返成本0.1%",
            "AkShare库末日2026-07-29",
        ],
        "strategies": results,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n写入 {OUT}", flush=True)


if __name__ == "__main__":
    main()
