#!/usr/bin/env python3
"""Download qfq A-share/ETF daily bars into the isolated AkShare store."""
import argparse
import json
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import akshare as ak

import akshare_data


def secid(code, is_etf):
    if is_etf:
        return ("1." if code.startswith("5") else "0.") + code
    return ("1." if code.startswith("6") else "0.") + code


def atomic_json(path, value):
    tmp = path.with_suffix(f".tmp.{os.getpid()}")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def stock_universe():
    frame = ak.stock_info_a_code_name()
    return [
        {"code": str(row["code"]).zfill(6), "name": str(row["name"]), "is_etf": False}
        for _, row in frame.iterrows()
    ]


def etf_universe():
    frame = ak.fund_etf_spot_em()
    return [
        {"code": str(row["代码"]).zfill(6), "name": str(row["名称"]), "is_etf": True}
        for _, row in frame.iterrows()
    ]


def existing_universe(kind):
    filename = "universe.json" if kind == "stock" else "etf_universe.json"
    path = Path(__file__).resolve().parent / "data_cache" / filename
    with path.open(encoding="utf-8") as f:
        payload = json.load(f)
    return [
        {"code": code, "name": name, "is_etf": kind == "etf"}
        for code, name, _secid in payload["items"]
    ]


def fetch_one(item, start, end, retries, pause):
    code = item["code"]
    for attempt in range(retries + 1):
        try:
            if item["is_etf"]:
                frame = ak.fund_etf_hist_em(
                    symbol=code, period="daily", start_date=start,
                    end_date=end, adjust="qfq",
                )
            else:
                frame = ak.stock_zh_a_hist(
                    symbol=code, period="daily", start_date=start,
                    end_date=end, adjust="qfq",
                )
            rows = []
            for _, row in frame.iterrows():
                rows.append([
                    str(row["日期"]), float(row["开盘"]), float(row["收盘"]),
                    float(row["最高"]), float(row["最低"]), float(row["成交量"]),
                    float(row["成交额"]),
                ])
            if not rows:
                raise RuntimeError("empty history")
            path = akshare_data.daily_path(secid(code, item["is_etf"]))
            atomic_json(path, rows)
            time.sleep(pause + random.random() * pause)
            return item, len(rows), None
        except Exception as exc:
            if attempt >= retries:
                return item, 0, f"{type(exc).__name__}: {exc}"
            time.sleep((attempt + 1) * 2 + random.random())


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", choices=("all", "stock", "etf"), default="all")
    parser.add_argument("--start", default="20200101")
    parser.add_argument("--end", default=date.today().strftime("%Y%m%d"))
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--pause", type=float, default=0.15)
    parser.add_argument("--max-symbols", type=int, default=0)
    parser.add_argument("--symbols", default="", help="comma-separated codes")
    parser.add_argument(
        "--universe-source", choices=("existing", "akshare"), default="existing",
        help="existing only reads code/name lists from data_cache; history never writes there",
    )
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    akshare_data.ensure_isolated_root()
    items = []
    wanted = {code.strip() for code in args.symbols.split(",") if code.strip()}
    if wanted and args.market == "all":
        raise SystemExit("--symbols requires --market stock or --market etf")
    if wanted:
        items = [
            {"code": code, "name": code, "is_etf": args.market == "etf"}
            for code in sorted(wanted)
        ]
    elif args.market in ("all", "stock"):
        stocks = (
            existing_universe("stock") if args.universe_source == "existing"
            else stock_universe()
        )
        atomic_json(akshare_data.ROOT / "stock_universe.json", stocks)
        items.extend(stocks)
    if not wanted and args.market in ("all", "etf"):
        etfs = (
            existing_universe("etf") if args.universe_source == "existing"
            else etf_universe()
        )
        atomic_json(akshare_data.ROOT / "etf_universe.json", etfs)
        items.extend(etfs)
    raw_count = len(items)
    unique = {}
    for item in items:
        unique[secid(item["code"], item["is_etf"])] = item
    items = list(unique.values())
    candidate_count = len(items)
    if not args.force:
        items = [
            item for item in items
            if not akshare_data.daily_path(secid(item["code"], item["is_etf"])).exists()
        ]
    if args.max_symbols > 0:
        items = items[:args.max_symbols]
    print(
        f"AkShare {ak.__version__}; output={akshare_data.ROOT}; "
        f"range={args.start}~{args.end}; pending={len(items)}",
        flush=True,
    )
    done = failed = bars = 0
    errors = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [
            pool.submit(fetch_one, item, args.start, args.end, args.retries, args.pause)
            for item in items
        ]
        for future in as_completed(futures):
            item, count, error = future.result()
            done += 1
            bars += count
            if error:
                failed += 1
                errors.append({"code": item["code"], "name": item["name"], "error": error})
            if done % 50 == 0 or done == len(items):
                print(f"  {done}/{len(items)} failed={failed} bars={bars}", flush=True)
    manifest = {
        "source": "AkShare", "akshareVersion": ak.__version__,
        "adjust": "qfq", "start": args.start, "end": args.end,
        "universeItems": raw_count, "uniqueCandidates": candidate_count,
        "requested": len(items), "completed": done - failed, "failed": failed,
        "bars": bars, "availableFiles": len(list((akshare_data.ROOT / "daily").glob("*.json"))),
        "errors": errors,
    }
    atomic_json(akshare_data.ROOT / "manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
