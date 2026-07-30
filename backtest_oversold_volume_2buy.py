#!/usr/bin/env python3
"""策略7B研究：超跌 -> 放量反弹 -> 缩量回踩不破前低 -> 二买转强。"""
import json
import os
import statistics
from concurrent.futures import ProcessPoolExecutor, as_completed

import cache_data

if os.environ.get("ABC_DATA_SOURCE") == "akshare":
    import akshare_data as history_data
else:
    history_data = cache_data

START = os.environ.get("START", "2020-01-01")
END = os.environ.get("END", "2026-07-29")
MIN_AMOUNT = float(os.environ.get("MIN_AMOUNT", "50000000"))
OVERSOLD_20 = float(os.environ.get("OVERSOLD_20", "-0.12"))
OVERSOLD_MA60 = float(os.environ.get("OVERSOLD_MA60", "-0.12"))
REBOUND_CHG = float(os.environ.get("REBOUND_CHG", "0.03"))
REBOUND_VR = float(os.environ.get("REBOUND_VR", "1.5"))
PULL_MIN = int(os.environ.get("PULL_MIN", "2"))
PULL_MAX = int(os.environ.get("PULL_MAX", "8"))
PULL_VOL = float(os.environ.get("PULL_VOL", "0.65"))
HIGHER_LOW = float(os.environ.get("HIGHER_LOW", "0.005"))
MAX_HOLD = int(os.environ.get("MAX_HOLD", "40"))
LAUNCH_WAIT = int(os.environ.get("LAUNCH_WAIT", "5"))
LAUNCH_RET = float(os.environ.get("LAUNCH_RET", "0.06"))
TRAIL_PCT = float(os.environ.get("TRAIL_PCT", "0.10"))
COST = float(os.environ.get("COST", "0.001"))
GAP_LIMIT = float(os.environ.get("GAP_LIMIT", "0.20"))
EXIT_MODE = os.environ.get("EXIT_MODE", "original")
MA5_ACTIVATE = float(os.environ.get("MA5_ACTIVATE", "0.06"))


def avg(values):
    return sum(values) / len(values) if values else 0.0


def signal_at(data, i):
    dates = data["dates"]
    if i < 90 or not START <= dates[i] <= END:
        return None
    o, c, h = data["open"], data["close"], data["high"]
    low, vol, amount = data["low"], data["vol"], data["amount"]
    if amount[i] < MIN_AMOUNT or c[i - 1] <= 0:
        return None

    # 当前K线是二次转强，不允许直接把第一次放量反弹当买点。
    if not (c[i] > o[i] and c[i] > h[i - 1] and c[i] / c[i - 1] - 1 >= 0.01):
        return None

    for rebound in range(i - PULL_MIN, max(60, i - PULL_MAX) - 1, -1):
        if rebound < 21 or c[rebound - 1] <= 0:
            continue
        v20 = avg(vol[rebound - 20:rebound])
        rebound_chg = c[rebound] / c[rebound - 1] - 1
        if not (
            c[rebound] > o[rebound]
            and rebound_chg >= REBOUND_CHG
            and v20 > 0
            and vol[rebound] >= v20 * REBOUND_VR
        ):
            continue

        # L1 必须出现在放量反弹当日或之前5日，且此前确有超跌段。
        l1_idx = min(range(rebound - 5, rebound + 1), key=lambda j: low[j])
        l1 = low[l1_idx]
        if l1 <= 0:
            continue
        ma60 = avg(c[rebound - 59:rebound + 1])
        ret20 = c[rebound - 1] / c[rebound - 21] - 1 if c[rebound - 21] > 0 else 0
        bias60 = c[rebound - 1] / ma60 - 1 if ma60 > 0 else 0
        if ret20 > OVERSOLD_20 and bias60 > OVERSOLD_MA60:
            continue
        if c[rebound] / l1 - 1 < 0.05:
            continue

        pull_start = rebound + 1
        if pull_start >= i:
            continue
        l2_idx = min(range(pull_start, i + 1), key=lambda j: low[j])
        l2 = low[l2_idx]
        if l2 <= 0 or l2_idx >= i or l2 < l1 * (1 + HIGHER_LOW):
            continue
        pull_avg_vol = avg(vol[pull_start:i])
        if pull_avg_vol > vol[rebound] * PULL_VOL:
            continue
        # 回踩不能吞掉第一次反弹的大部分实体，避免把持续下跌误认成二买。
        rebound_mid = (c[rebound] + l1) / 2
        if l2 < rebound_mid * 0.98:
            continue
        # 二次转强需要量能从回踩地量恢复，但不要求再次爆量。
        if pull_avg_vol > 0 and vol[i] < pull_avg_vol * 1.05:
            continue
        return {
            "l1": l1,
            "l1_idx": l1_idx,
            "l2": l2,
            "l2_idx": l2_idx,
            "rebound": rebound,
            "rebound_vr": vol[rebound] / v20,
            "pull_vol_ratio": pull_avg_vol / vol[rebound],
            "ret20": ret20,
            "bias60": bias60,
        }
    return None


def exit_trade(data, i, setup):
    o, c, h, low = data["open"], data["close"], data["high"], data["low"]
    entry = c[i]
    hard_stop = setup["l2"] * 0.99
    mode_holds = {"hold10": 10, "hold20": 20, "structure10": 10, "structure20": 20}
    end = len(c) - 1 if EXIT_MODE == "low_ma5" else min(
        len(c) - 1, i + mode_holds.get(EXIT_MODE, MAX_HOLD)
    )
    launched = False
    ma5_protect = False
    peak = h[i]
    worst = 0.0
    for j in range(i + 1, end + 1):
        if c[j - 1] > 0 and abs(o[j] / c[j - 1] - 1) > GAP_LIMIT:
            return j, 0.0, "split", worst
        stop = max(hard_stop, peak * (1 - TRAIL_PCT)) if EXIT_MODE == "original" and launched else hard_stop
        worst = min(worst, low[j] / entry - 1)
        if o[j] <= stop:
            return j, o[j], "trail_open" if launched else "stop_open", worst
        if low[j] <= stop:
            return j, stop, "trail" if launched else "stop", worst
        if EXIT_MODE == "low_ma5":
            ma5 = avg(c[j - 4:j + 1]) if j >= 4 else 0.0
            # 五日线仅承担止盈：出现过收盘浮盈后启用，避免把普通亏损
            # 提前包装成“止盈”；未盈利时唯一退出条件仍是跌破 L2。
            if c[j] / entry - 1 >= MA5_ACTIVATE and ma5 > 0 and c[j] >= ma5:
                ma5_protect = True
            if ma5_protect and c[j] < ma5:
                return j, c[j], "ma5_profit", worst
        if EXIT_MODE == "original" and not launched and j - i >= LAUNCH_WAIT:
            return j, c[j], "no_launch", worst
        if EXIT_MODE == "original" and not launched and c[j] / entry - 1 >= LAUNCH_RET:
            launched = True
        if EXIT_MODE.startswith("structure") and j - i >= 3:
            ma5 = avg(c[max(0, j - 4):j + 1])
            ma10 = avg(c[max(0, j - 9):j + 1])
            if c[j] < ma5 and c[j] < ma10 and c[j] < c[j - 1]:
                return j, c[j], "ma_weak", worst
        peak = max(peak, h[j])
    return end, c[end], "censored" if EXIT_MODE == "low_ma5" else "timeout", worst


def run_one(item):
    code, name, secid = item
    rows = history_data.daily_kline(secid) or []
    if len(rows) < 110:
        return []
    data = {
        "dates": [row[0] for row in rows],
        "open": [float(row[1]) for row in rows],
        "close": [float(row[2]) for row in rows],
        "high": [float(row[3]) for row in rows],
        "low": [float(row[4]) for row in rows],
        "vol": [float(row[5]) for row in rows],
        "amount": [float(row[6]) for row in rows],
    }
    out = []
    last_signal = -20
    for i in range(90, len(rows) - 3):
        if i - last_signal < 5:
            continue
        setup = signal_at(data, i)
        if not setup:
            continue
        j, sell, reason, mae = exit_trade(data, i, setup)
        if reason == "split":
            continue
        entry = data["close"][i]
        available = len(data["close"]) - 1 - i
        # 信号按当日收盘买入，不能把买入前已经出现的当日最高价算作可得涨幅。
        mfe10_end = min(len(data["high"]), i + 11)
        mfe20_end = min(len(data["high"]), i + 21)
        future10 = data["high"][i + 1:mfe10_end]
        future20 = data["high"][i + 1:mfe20_end]
        higher_low_pct = setup["l2"] / setup["l1"] * 100 - 100
        out.append({
            "date": data["dates"][i], "code": code, "name": name,
            "open": data["open"][i], "high": data["high"][i],
            "low": data["low"][i], "close": entry,
            "amount": data["amount"][i], "amt": data["amount"][i] / 1e8,
            "entry": entry, "exit": data["dates"][j], "held": j - i,
            "reason": reason, "ret": sell / entry - 1 - COST, "mae": mae,
            "l1": setup["l1"], "l2": setup["l2"], "stop": setup["l2"] * 0.99,
            "higher_low": higher_low_pct,
            "higher_low_ratio": setup["l2"] / setup["l1"] - 1,
            "rebound_vr": setup["rebound_vr"],
            "pull_vol_ratio": setup["pull_vol_ratio"],
            "ret20": setup["ret20"], "bias60": setup["bias60"],
            "mfe10": max(future10, default=entry) / entry - 1,
            "mfe20": max(future20, default=entry) / entry - 1,
            "complete10": available >= 10, "complete20": available >= 20,
        })
        last_signal = i
    return out


def metric(trades):
    if not trades:
        return "0笔"
    returns = [trade["ret"] for trade in trades]
    return (
        f"{len(trades)}笔 胜率{sum(value > 0 for value in returns)/len(returns)*100:.1f}% "
        f"均值{statistics.mean(returns)*100:+.2f}% 中位{statistics.median(returns)*100:+.2f}% "
        f"MAE{statistics.mean(trade['mae'] for trade in trades)*100:+.2f}%"
    )


def main():
    # 股票池来源偶尔包含重复证券，按代码去重，避免重复计算同一信号。
    universe = list({item[0]: item for item in cache_data.universe()}.values())
    output = os.environ.get("S7B_OUTPUT", "")
    trades = []
    workers = int(os.environ.get("S7B_WORKERS", "8"))
    print(f"策略7B universe={len(universe)} source={os.environ.get('ABC_DATA_SOURCE', 'cache')} exit={EXIT_MODE}", flush=True)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_one, item) for item in universe]
        failed = 0
        for done, future in enumerate(as_completed(futures), 1):
            try:
                trades.extend(future.result())
            except Exception as exc:
                failed += 1
                if failed <= 5:
                    print(f"WARN {type(exc).__name__}: {exc}", flush=True)
            if done % 100 == 0 or done == len(futures):
                print(f"  {done}/{len(futures)} trades={len(trades)} failed={failed}", flush=True)
    if output:
        os.makedirs(os.path.dirname(output), exist_ok=True)
        tmp = output + ".tmp"
        with open(tmp, "w", encoding="utf-8") as file:
            json.dump(trades, file, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, output)
    print("ALL", metric(trades))
    for year in range(2020, 2027):
        selected = [trade for trade in trades if trade["date"].startswith(str(year))]
        if selected:
            print(year, metric(selected))


if __name__ == "__main__":
    main()
