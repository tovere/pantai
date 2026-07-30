#!/usr/bin/env python3
"""Replay dashboard A/B/C grading on historical strategy trades."""
import argparse
import json
import os
import statistics
from concurrent.futures import ProcessPoolExecutor, as_completed

import cache_data
import watch_grade
import backtest_chan_wyckoff_3buy as s5
import backtest_squeeze_launch as s6
import backtest_nzi_reversal as s8
import backtest_strategy9_distilled as s9

if os.environ.get("ABC_DATA_SOURCE") == "akshare":
    import akshare_data as history_data
else:
    history_data = cache_data


SPECS = (
    ("s5_stock_strict", "策略五·个股·严格三买", "chan_wyckoff_3buy"),
    ("s6_stock", "策略六·个股·压缩蓄势", "squeeze_launch"),
    ("s8_stock", "策略八·个股·N字反包", "nzi_reversal"),
    ("s9_stock", "策略九·防守蒸馏版", "strategy9_distilled"),
)
MODULES = {
    "s5_stock_strict": s5,
    "s6_stock": s6,
    "s8_stock": s8,
    "s9_stock": s9,
}


def grade_hit(strategy, trade, rows):
    hit = dict(trade)
    hit["close"] = trade["entry"]
    if strategy == "squeeze_launch":
        hit["bias60"] = trade["bias60"] * 100
        hit["runup"] = trade["runup"] * 100
    elif strategy == "strategy9_distilled":
        if trade.get("kind") == "coil_launch":
            hit["bias60"] = trade.get("bias60", 0) * 100
            hit["runup"] = trade.get("runup", 0) * 100
        elif trade.get("kind") == "spring_2buy":
            hit["up_from_spring"] = trade.get("up_from_spring", 0) * 100
    dates = [r[0] for r in rows]
    i = dates.index(trade["date"])
    bars = rows[max(0, i - 59):i + 1]
    return watch_grade.grade(strategy, hit, bars)["grade"]


def run_one(spec, item):
    key, _title, strategy = spec
    module = MODULES[key]
    code, name, secid = item
    rows = history_data.daily_kline(secid) or []
    found = module.run_one(code, name, secid, rows)
    for trade in found:
        trade["grade"] = grade_hit(strategy, trade, rows)
    return key, secid, found


def run_spec(spec, universe):
    key, title, _strategy = spec
    trades = []
    workers = int(os.environ.get("ABC_WORKERS", "8"))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(run_one, spec, item): item[2]
            for item in universe
        }
        failed = 0
        for done, future in enumerate(as_completed(futures), 1):
            try:
                _key, _secid, found = future.result()
                trades.extend(found)
            except Exception as exc:
                failed += 1
                if failed <= 5:
                    print(f"WARN {key} {futures[future]}: {exc}", flush=True)
            if done % 100 == 0 or done == len(futures):
                print(f"  {done}/{len(futures)} trades={len(trades)} failed={failed}", flush=True)
    return title, trades


def metric(trades):
    if not trades:
        return "0笔"
    returns = [t["ret"] for t in trades]
    return (
        f"{len(trades):4d}笔  胜率{sum(r > 0 for r in returns) / len(returns) * 100:5.1f}%  "
        f"均值{statistics.mean(returns) * 100:+6.2f}%  "
        f"中位{statistics.median(returns) * 100:+6.2f}%"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", choices=[s[0] for s in SPECS])
    parser.add_argument("--output")
    args = parser.parse_args()
    universe = cache_data.universe()
    print(f"评级分层回测，股票池 {len(universe)} 只；区间 {s5.START}~{s5.END}")
    specs = [s for s in SPECS if not args.strategy or s[0] == args.strategy]
    for spec in specs:
        title, trades = run_spec(spec, universe)
        if args.output:
            os.makedirs(os.path.dirname(args.output), exist_ok=True)
            tmp = args.output + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(trades, f, ensure_ascii=False, separators=(",", ":"))
            os.replace(tmp, args.output)
            print(f"saved {args.output}", flush=True)
        print(f"\n{title}  总体 {metric(trades)}")
        for grade in "ABCD":
            print(f"  {grade}: {metric([t for t in trades if t['grade'] == grade])}")


if __name__ == "__main__":
    main()
