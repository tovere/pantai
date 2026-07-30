#!/usr/bin/env python3
"""Build a local stock -> industry cache without touching kline cache.

Default scope is current watch hits so the dashboard can show industries quickly.
Source is CNINFO company profile through AkShare, not East Money.
"""
import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import akshare as ak


HERE = Path(__file__).resolve().parent
OUT = HERE / "data_cache" / "stock_industry.json"


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".tmp.{os.getpid()}")
    with tmp.open("w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def read_existing():
    try:
        payload = json.load(OUT.open(encoding="utf-8"))
        return payload.get("items", {}) if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def watch_codes():
    payload = json.load((HERE / "watch_data.json").open(encoding="utf-8"))
    codes = {
        hit["code"]
        for section in payload.get("sections", [])
        if not section.get("is_etf")
        for hit in section.get("hits", [])
        if hit.get("code")
    }
    return sorted(codes)


def universe_codes():
    payload = json.load((HERE / "data_cache" / "universe.json").open(encoding="utf-8"))
    return sorted({code for code, _name, _secid in payload.get("items", [])})


def fetch_one(code):
    frame = ak.stock_profile_cninfo(symbol=code)
    if frame.empty or "所属行业" not in frame.columns:
        return code, {"industry": ""}
    row = frame.iloc[0]
    time.sleep(0.1)
    return code, {
        "industry": str(row.get("所属行业") or ""),
        "sourceName": str(row.get("A股简称") or ""),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=("watch", "all"), default="watch")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    codes = watch_codes() if args.scope == "watch" else universe_codes()
    items = read_existing()
    pending = [code for code in codes if args.force or not items.get(code, {}).get("industry")]
    done = failed = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(fetch_one, code): code for code in pending}
        for future in as_completed(futures):
            code = futures[future]
            done += 1
            try:
                code, item = future.result()
                items[code] = item
            except Exception as exc:
                failed += 1
                items[code] = {"industry": "", "error": f"{type(exc).__name__}: {exc}"}
            if done % 20 == 0 or done == len(pending):
                cached = sum(1 for code in codes if items.get(code, {}).get("industry"))
                print(f"  {done}/{len(pending)} cached={cached} failed={failed}", flush=True)
    atomic_json(OUT, {
        "date": date.today().isoformat(),
        "source": "akshare.stock_profile_cninfo",
        "scope": args.scope,
        "items": items,
    })
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
