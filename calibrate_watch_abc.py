#!/usr/bin/env python3
"""Time-split calibration experiment for explainable dashboard grades."""
import json
import os
import random
import statistics
from concurrent.futures import ProcessPoolExecutor, as_completed

import cache_data
import watch_grade
import backtest_chan_wyckoff_3buy as s5

if os.environ.get("ABC_DATA_SOURCE") == "akshare":
    import akshare_data as history_data
else:
    history_data = cache_data

TRAIN_END = "2026-02-28"
_BENCHMARK = None


def solve(a, b):
    """Gaussian elimination for a small ridge-regression system."""
    n = len(b)
    m = [a[i][:] + [b[i]] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(m[row][col]))
        m[col], m[pivot] = m[pivot], m[col]
        div = m[col][col]
        for j in range(col, n + 1):
            m[col][j] /= div
        for row in range(n):
            if row == col:
                continue
            factor = m[row][col]
            for j in range(col, n + 1):
                m[row][j] -= factor * m[col][j]
    return [m[i][n] for i in range(n)]


def ridge_fit(samples, ridge=8.0):
    p = len(samples[0][0])
    xtx = [[0.0] * p for _ in range(p)]
    xty = [0.0] * p
    for x, y in samples:
        for i in range(p):
            xty[i] += x[i] * y
            for j in range(p):
                xtx[i][j] += x[i] * x[j]
    for i in range(1, p):
        xtx[i][i] += ridge
    return solve(xtx, xty)


def benchmark_returns(trade_date):
    global _BENCHMARK
    if _BENCHMARK is None:
        rows = history_data.daily_kline("1.510300") or []
        _BENCHMARK = {row[0]: (i, rows) for i, row in enumerate(rows)}
    found = _BENCHMARK.get(trade_date)
    if not found:
        return 0.0, 0.0
    i, rows = found
    closes = [float(row[2]) for row in rows]
    r20 = closes[i] / closes[i - 20] - 1 if i >= 20 and closes[i - 20] > 0 else 0.0
    r60 = closes[i] / closes[i - 60] - 1 if i >= 60 and closes[i - 60] > 0 else 0.0
    return r20, r60


def features(trade, rows, i, bars):
    flags = watch_grade.grade_three_buy(trade, bars)["flags"]
    bad = any(f["type"] == "bad" for f in flags)
    closes = [float(row[2]) for row in rows]
    ret = lambda n: closes[i] / closes[i - n] - 1 if i >= n and closes[i - n] > 0 else 0.0
    ma_now = sum(closes[i - 19:i + 1]) / 20 if i >= 19 else closes[i]
    ma_prev = sum(closes[i - 29:i - 9]) / 20 if i >= 29 else ma_now
    bench20, bench60 = benchmark_returns(trade["date"])
    return [
        1.0,
        float(trade["dist"] <= 3),
        float(3 < trade["dist"] <= 8),
        float(trade["pull_days"] <= 3),
        float(trade["pull_days"] >= 7),
        float(trade["vol_shrink"] <= 0.60),
        float(trade["vol_shrink"] >= 0.90),
        float(trade["amt"] < 1.5),
        float(bad),
        ret(5) * 10,
        ret(20) * 10,
        ret(60) * 5,
        (ma_now / ma_prev - 1) * 10 if ma_prev > 0 else 0.0,
        bench20 * 10,
        bench60 * 5,
    ]


def run_one(item):
    code, name, secid = item
    rows = history_data.daily_kline(secid) or []
    dates = [r[0] for r in rows]
    out = []
    for trade in s5.run_one(code, name, secid, rows):
        i = dates.index(trade["date"])
        bars = rows[max(0, i - 59):i + 1]
        trade["x"] = features(trade, rows, i, bars)
        out.append(trade)
    return out


def describe(label, trades):
    returns = [t["ret"] for t in trades]
    if not returns:
        return f"{label}: 0笔"
    return (
        f"{label}: {len(returns)}笔 胜率{sum(r > 0 for r in returns)/len(returns)*100:.1f}% "
        f"均值{statistics.mean(returns)*100:+.2f}% 中位{statistics.median(returns)*100:+.2f}%"
    )


def split_grades(train, test):
    model = ridge_fit(
        [(t["x"], max(-0.10, min(0.15, t["ret"]))) for t in train]
    )
    train_scores = sorted(sum(w * x for w, x in zip(model, t["x"])) for t in train)
    cut_c = train_scores[int(len(train_scores) * 0.40)]
    cut_a = train_scores[int(len(train_scores) * 0.75)]
    grades = {"A": [], "B": [], "C": []}
    for trade in test:
        pred = sum(w * x for w, x in zip(model, trade["x"]))
        grade = "A" if pred >= cut_a else "B" if pred >= cut_c else "C"
        grades[grade].append(trade)
    return model, cut_c, cut_a, grades


def main():
    feature_cache = os.environ.get("ABC_FEATURE_CACHE", "")
    if feature_cache and os.path.exists(feature_cache):
        with open(feature_cache, encoding="utf-8") as f:
            trades = json.load(f)
        print(f"loaded feature cache {feature_cache}: {len(trades)} trades", flush=True)
    else:
        trades = collect_trades()
        if feature_cache:
            os.makedirs(os.path.dirname(feature_cache), exist_ok=True)
            tmp = feature_cache + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(trades, f, ensure_ascii=False, separators=(",", ":"))
            os.replace(tmp, feature_cache)
            print(f"saved feature cache {feature_cache}", flush=True)
    evaluate(trades)


def collect_trades():
    trades = []
    universe = (
        cache_data.etf_universe()
        if os.environ.get("ETF_ONLY", "0") != "0"
        else cache_data.universe()
    )
    max_symbols = int(os.environ.get("ABC_MAX_SYMBOLS", "0"))
    if max_symbols and len(universe) > max_symbols:
        universe = random.Random(42).sample(universe, max_symbols)
    print(f"calibration universe={len(universe)} source={os.environ.get('ABC_DATA_SOURCE', 'cache')}", flush=True)
    workers = int(os.environ.get("ABC_WORKERS", "8"))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_one, item) for item in universe]
        failed = 0
        for done, future in enumerate(as_completed(futures), 1):
            try:
                trades.extend(future.result())
            except Exception as exc:
                failed += 1
                if failed <= 5:
                    print(f"  skipped bad symbol: {type(exc).__name__}: {exc}", flush=True)
            if done % 100 == 0 or done == len(futures):
                print(f"  {done}/{len(futures)} trades={len(trades)} failed={failed}", flush=True)
    return trades


def evaluate(trades):
    train = [t for t in trades if t["date"] <= TRAIN_END]
    test = [t for t in trades if t["date"] > TRAIN_END]
    # Expected utility: cap fat tails, while keeping losses and meaningful winners distinct.
    model = ridge_fit([(t["x"], max(-0.10, min(0.15, t["ret"]))) for t in train])
    for trade in trades:
        trade["pred"] = sum(w * x for w, x in zip(model, trade["x"]))
    ordered = sorted(t["pred"] for t in train)
    cut_c = ordered[int(len(ordered) * 0.40)]
    cut_a = ordered[int(len(ordered) * 0.75)]
    print("weights", " ".join(f"{w:+.5f}" for w in model))
    print("cuts", f"C/B={cut_c:+.5f}", f"B/A={cut_a:+.5f}")
    for period, group in (("TRAIN", train), ("TEST", test)):
        print(period, min(t["date"] for t in group), max(t["date"] for t in group))
        grades = {
            "A": [t for t in group if t["pred"] >= cut_a],
            "B": [t for t in group if cut_c <= t["pred"] < cut_a],
            "C": [t for t in group if t["pred"] < cut_c],
        }
        for grade in "ABC":
            print(describe(grade, grades[grade]))
    print("ROLLING OOS")
    for year in range(2022, 2027):
        cutoff = f"{year}-01-01"
        rolling_train = [t for t in trades if t["date"] < cutoff]
        rolling_test = [t for t in trades if t["date"].startswith(str(year))]
        if len(rolling_train) < 100 or not rolling_test:
            continue
        _model, _cut_c, _cut_a, grades = split_grades(rolling_train, rolling_test)
        print(f"YEAR {year} train={len(rolling_train)} test={len(rolling_test)}")
        for grade in "ABC":
            print(describe(grade, grades[grade]))
    print("TRAILING 2Y OOS")
    for year in range(2022, 2027):
        start = f"{year - 2}-01-01"
        cutoff = f"{year}-01-01"
        rolling_train = [t for t in trades if start <= t["date"] < cutoff]
        rolling_test = [t for t in trades if t["date"].startswith(str(year))]
        if len(rolling_train) < 100 or not rolling_test:
            continue
        _model, _cut_c, _cut_a, grades = split_grades(rolling_train, rolling_test)
        print(f"YEAR {year} train={len(rolling_train)} test={len(rolling_test)}")
        for grade in "ABC":
            print(describe(grade, grades[grade]))


if __name__ == "__main__":
    main()
