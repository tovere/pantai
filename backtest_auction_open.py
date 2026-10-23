#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""今早可买 tab 回放：昨晚盯盘命中 ∩ 次日开盘规则，开盘买、再下一开盘卖。

做不到的部分：历史个股竞价量比/未匹配/9:20-9:25 tape。MCP 竞价接口没有日期参数。
本脚本复用 tab 的候选合并 + classify 里不依赖竞价盘口的规则：
  剔十四/十五、D 放弃、仅十二全量池观察、C 观察、开盘近涨停放弃、开盘破止损放弃。
  无竞价字段时，A/B 且可执行 → 记为「可买」(与盘口缺失时 tab 的兜底句一致)。

    python3 backtest_auction_open.py
"""
import json
import os
import statistics
from collections import Counter
from pathlib import Path

import auction_open_screen as auc
import cache_data
import watch_export

HERE = Path(__file__).resolve().parent
HIST_DIR = Path(watch_export.HIST_DIR)
COST = float(os.environ.get("COST", "0.001"))


def trading_days():
    rows = cache_data.daily_kline("1.000001") or cache_data.daily_kline("0.000001") or []
    return [r[0] for r in rows if r]


def next_day(days, d, n=1):
    try:
        i = days.index(d)
    except ValueError:
        later = [x for x in days if x > d]
        if not later:
            return None
        i = days.index(later[0]) - 1
    j = i + n
    if j < 0 or j >= len(days):
        return None
    return days[j]


def bar_on(rows, d):
    if not rows:
        return None
    for r in rows:
        if r[0] == d:
            return r
    return None


def load_hist(path):
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    for sec in payload.get("sections") or []:
        key = sec.get("key") or ""
        if "is_etf" not in sec:
            sec["is_etf"] = "etf" in key
        for h in sec.get("hits") or []:
            if "is_etf" not in h:
                h["is_etf"] = sec["is_etf"]
    return payload


def classify_open(cand, buy_open, prev_close):
    row = dict(cand)
    row["open_price"] = buy_open
    row["auction_price"] = buy_open
    row["prev_price"] = prev_close or cand.get("close")
    row["auction_pct"] = None
    row["auction_volume"] = None
    row["auction_unmatched"] = None
    row["auction_volume_ratio"] = None
    row["settle_tag"] = "无对照"
    action, reason = auc.classify(row)
    return action, reason, row


def bucket(label, xs, min_n=8):
    if len(xs) < min_n:
        print(f"  {label:<22} {len(xs):>4}笔 (少)")
        return
    rs = [t["ret"] for t in xs]
    print(
        f"  {label:<22} {len(xs):>4}笔  胜{sum(r > 0 for r in rs) / len(rs) * 100:5.1f}%  "
        f"均{statistics.mean(rs) * 100:+6.2f}%  中{statistics.median(rs) * 100:+6.2f}%"
    )


def main():
    os.environ.setdefault("CACHE_ONLY", "1")
    days = trading_days()
    files = sorted(HIST_DIR.glob("*.json"))
    print(
        f"今早可买回放  盯盘历史 {len(files)} 日  口径=次日开→再下一开  扣{COST*100:.2f}%  "
        f"无历史竞价盘口",
        flush=True,
    )
    trades = []
    days_out = []
    skipped_hist = 0
    for fp in files:
        payload = load_hist(fp)
        sig = payload.get("date") or fp.stem
        buy_d = next_day(days, sig, 1)
        sell_d = next_day(days, sig, 2)
        if not buy_d or not sell_d:
            skipped_hist += 1
            continue
        cands = auc.collect_candidates(payload)
        day_rets = []
        for c in cands:
            secid = watch_export._secid(c["code"], c["is_etf"])
            rows = cache_data.daily_kline(secid)
            buy_bar = bar_on(rows, buy_d)
            sell_bar = bar_on(rows, sell_d)
            if not buy_bar or not sell_bar:
                continue
            buy_px = float(buy_bar[1])
            sell_px = float(sell_bar[1])
            if buy_px <= 0 or sell_px <= 0:
                continue
            prev = None
            try:
                if c.get("close") not in (None, ""):
                    prev = float(c["close"])
            except (TypeError, ValueError):
                prev = None
            if not prev or prev <= 0:
                i = next((k for k, r in enumerate(rows or []) if r[0] == buy_d), None)
                if i is None or i < 1:
                    continue
                prev = float(rows[i - 1][2])
            action, reason, row = classify_open(c, buy_px, prev)
            ret = sell_px / buy_px - 1 - COST
            rec = {
                "signal": sig,
                "buy": buy_d,
                "sell": sell_d,
                "code": c["code"],
                "name": c["name"],
                "grade": c.get("grade"),
                "action": action,
                "reason": reason,
                "open_pct": row.get("open_pct"),
                "ret": ret,
                "is_etf": c["is_etf"],
            }
            trades.append(rec)
            if action == "buy":
                day_rets.append(ret)
        if day_rets:
            days_out.append({
                "signal": sig, "buy": buy_d, "n": len(day_rets),
                "ret": statistics.mean(day_rets),
            })

    buy = [t for t in trades if t["action"] == "buy"]
    watch = [t for t in trades if t["action"] == "watch"]
    skip = [t for t in trades if t["action"] == "skip"]
    print(f"\n>> 可复盘信号日 {len(files) - skipped_hist}  "
          f"(缺 D+2 跳过 {skipped_hist})  候选{len(trades)}  "
          f"可买{len(buy)} 观察{len(watch)} 放弃{len(skip)}\n")
    bucket("可买(跟着tab)", buy, 1)
    bucket("观察(对照)", watch, 1)
    bucket("放弃(对照)", skip, 1)
    print("\n[可买·评级]")
    for g in "AB":
        bucket(g, [t for t in buy if t["grade"] == g], 1)
    print("\n[可买·类型]")
    bucket("ETF", [t for t in buy if t["is_etf"]], 1)
    bucket("个股", [t for t in buy if not t["is_etf"]], 1)
    print("\n[日等权篮子] 当天全部可买等权，一天一笔")
    if days_out:
        rs = [d["ret"] for d in days_out]
        print(
            f"  {len(days_out)}个交易日  日胜{sum(r > 0 for r in rs) / len(rs) * 100:5.1f}%  "
            f"均{statistics.mean(rs) * 100:+6.2f}%  中{statistics.median(rs) * 100:+6.2f}%  "
            f"日均{statistics.mean(d['n'] for d in days_out):.1f}只"
        )
        for d in days_out[-8:]:
            print(f"    {d['buy']}  n={d['n']:<3}  {d['ret']*100:+6.2f}%")
    print("\n[放弃原因]")
    for k, n in Counter(t["reason"].split("，")[0][:18] for t in skip).most_common(6):
        print(f"  {k:<22} {n}")


if __name__ == "__main__":
    main()
