#!/usr/bin/env python3
"""Replay dashboard grades for strategy 10 with its production parameters."""
import argparse
import json
import os
import random
import statistics
from concurrent.futures import ProcessPoolExecutor, as_completed


PARSER = argparse.ArgumentParser()
PARSER.add_argument("--etf", action="store_true")
PARSER.add_argument("--assume-sub", action="store_true")
PARSER.add_argument("--calibrate", action="store_true")
ARGS = PARSER.parse_args()

# These must be set before strategy_chan_final imports its signal module.
os.environ["ENABLE_TYPES"] = "3"
os.environ["ONLY_TYPE"] = "3"
os.environ["WEEKLY_MODE"] = "ma"
os.environ["EXIT_MODE"] = "trail" if ARGS.etf else "fractal"
os.environ["ETF_ONLY"] = "1" if ARGS.etf else "0"
os.environ["PULLBACK_GG"] = "1" if ARGS.etf else "0"

import cache_data  # noqa: E402
import watch_grade  # noqa: E402
from calibrate_watch_abc import evaluate  # noqa: E402
from strategy_chan_final import backtest as bt  # noqa: E402

if os.environ.get("ABC_DATA_SOURCE") == "akshare":
    import akshare_data as history_data  # noqa: E402
else:
    history_data = cache_data


def grade_trade(trade, rows):
    dates = [r[0] for r in rows]
    i = dates.index(trade["date"])
    stop = min(trade["low"], trade["zg"])
    hit = {
        "close": trade["entry"],
        "stage": trade.get("stage", 0),
        "lag": trade.get("lag", 0),
        "risk": (trade["entry"] / stop - 1) * 100 if stop else 99,
        "amt": float(rows[i][6]) / 1e8,
        "is_etf": ARGS.etf,
        # Historical 30-minute cache is too short for a one-year replay.
        "sub": "三买" if ARGS.assume_sub else "",
    }
    bars = rows[max(0, i - 59):i + 1]
    return watch_grade.grade("chan_final", hit, bars)["grade"]


def calibration_features(trade, rows):
    dates = [r[0] for r in rows]
    i = dates.index(trade["date"])
    stop = min(trade["low"], trade["zg"])
    risk = (trade["entry"] / stop - 1) * 100 if stop else 99
    bars = rows[max(0, i - 59):i + 1]
    bad = watch_grade._rejection(bars) or watch_grade._volume_stall(
        bars, trade.get("lag", 0) + 2
    )
    return [
        1.0,
        float(trade.get("stage", 0) == 1),
        float(trade.get("stage", 0) == 2),
        float(risk <= 4),
        float(risk > 8),
        float(trade.get("lag", 0) <= 1),
        float(trade.get("lag", 0) >= 4),
        float(float(rows[i][6]) / 1e8 < 1.5),
        float(bad),
    ]


def run_one(item):
    code, name, secid = item
    rows = history_data.daily_kline(secid) or []
    trades = bt.run_one(code, name, secid, rows)
    for trade in trades:
        trade["grade"] = grade_trade(trade, rows)
        trade["x"] = calibration_features(trade, rows)
    return trades


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
    universe = cache_data.etf_universe() if ARGS.etf else cache_data.universe()
    max_symbols = int(os.environ.get("ABC_MAX_SYMBOLS", "0"))
    if max_symbols and len(universe) > max_symbols:
        universe = random.Random(42).sample(universe, max_symbols)
    feature_cache = os.environ.get("ABC_FEATURE_CACHE", "")
    if feature_cache and os.path.exists(feature_cache):
        with open(feature_cache, encoding="utf-8") as f:
            trades = json.load(f)
        print(f"loaded feature cache {feature_cache}: {len(trades)} trades", flush=True)
    else:
        trades = []
        print(f"calibration universe={len(universe)}", flush=True)
        with ProcessPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(run_one, item) for item in universe]
            for done, future in enumerate(as_completed(futures), 1):
                try:
                    trades.extend(future.result())
                except Exception as exc:
                    if done <= 5:
                        print(f"skipped bad symbol: {type(exc).__name__}: {exc}", flush=True)
                if done % 50 == 0 or done == len(futures):
                    print(f"  {done}/{len(futures)} trades={len(trades)}", flush=True)
        if feature_cache:
            os.makedirs(os.path.dirname(feature_cache), exist_ok=True)
            tmp = feature_cache + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(trades, f, ensure_ascii=False, separators=(",", ":"))
            os.replace(tmp, feature_cache)
    pool_name = "ETF" if ARGS.etf else "个股"
    if ARGS.calibrate:
        calibrate(trades)
        return
    sub_name = "全假设30分共振" if ARGS.assume_sub else "无30分共振"
    print(f"策略十·{pool_name}·{sub_name}  总体 {metric(trades)}")
    for grade in "ABCD":
        selected = [t for t in trades if t["grade"] == grade]
        print(f"  {grade}: {metric(selected)}")


def calibrate(trades):
    evaluate(trades)


if __name__ == "__main__":
    main()
