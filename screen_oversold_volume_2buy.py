#!/usr/bin/env python3
"""策略7：超跌放量反弹后的缩量回踩二买（日线候选）。"""
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import cache_data
from backtest_oversold_volume_2buy import signal_at

TODAY = os.environ.get("SCREEN_DATE", date.today().isoformat())


def check(code, name, rows):
    if len(rows) < 110 or rows[-1][0] != TODAY:
        return None
    data = {
        "dates": [row[0] for row in rows],
        "open": [float(row[1]) for row in rows],
        "close": [float(row[2]) for row in rows],
        "high": [float(row[3]) for row in rows],
        "low": [float(row[4]) for row in rows],
        "vol": [float(row[5]) for row in rows],
        "amount": [float(row[6]) for row in rows],
    }
    i = len(rows) - 1
    setup = signal_at(data, i)
    if not setup:
        return None
    close = data["close"][i]
    return {
        "code": code, "name": name, "close": round(close, 2),
        "chg": round((close / data["close"][i - 1] - 1) * 100, 2),
        "l1": round(setup["l1"], 2), "l2": round(setup["l2"], 2),
        "stop": round(setup["l2"] * 0.99, 2),
        "higher_low": round(setup["l2"] / setup["l1"] * 100 - 100, 1),
        "rebound_vr": round(setup["rebound_vr"], 2),
        "pull_vol_ratio": round(setup["pull_vol_ratio"], 2),
        "oversold20": round(setup["ret20"] * 100, 1),
        "bias60": round(setup["bias60"] * 100, 1),
        "pull_days": i - setup["rebound"],
        "rebound_date": data["dates"][setup["rebound"]][5:],
        "amt": round(data["amount"][i] / 1e8, 1),
    }


def main():
    universe = list({item[0]: item for item in cache_data.universe()}.values())
    hits = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {
            pool.submit(cache_data.daily_kline, secid): (code, name)
            for code, name, secid in universe
        }
        for done, future in enumerate(as_completed(futures), 1):
            code, name = futures[future]
            try:
                item = check(code, name, future.result() or [])
                if item:
                    hits.append(item)
            except Exception:
                pass
            if done % 500 == 0 or done == len(futures):
                print(f"  {done}/{len(futures)} 命中{len(hits)}", flush=True)
    hits.sort(key=lambda item: (item["pull_vol_ratio"], -item["rebound_vr"]))
    output = os.environ.get("WATCH_JSON_OUT")
    if output:
        with open(output, "w", encoding="utf-8") as file:
            json.dump({"strategy": "oversold_volume_2buy", "variant": "stock",
                       "is_etf": False, "date": TODAY, "hits": hits}, file,
                      ensure_ascii=False)
    print(f"策略7 超跌放量回踩二买：{len(hits)}只")


if __name__ == "__main__":
    main()
