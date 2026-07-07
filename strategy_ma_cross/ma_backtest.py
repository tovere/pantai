#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略回测：2日均线上穿5日均线 且 收盘>=13日均线，不抗单次日卖出。
可叠加"龙头过滤"：信号日近 LEADER_LOOKBACK 天内涨停 >= LEADER_MIN_LIMITS 次。
数据源：东方财富 (push2his.eastmoney.com)  前复权(fqt=1)。纯标准库 + 多线程。
"""
import json
import urllib.request
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------------- 参数 ----------------
SIGNAL_START = "2025-07-01"   # 信号日窗口：近一年
SIGNAL_END   = "2026-06-29"
DATA_BEG     = "20250401"     # 拉数据起点（给MA13 + 涨停回看留热身）
DATA_END     = "20500101"
ROUND_TRIP_COST = 0.001       # 往返成本约0.1%
LEADER_LOOKBACK   = 10        # 龙头：回看天数
LEADER_MIN_LIMITS = 2         # 龙头：期间至少涨停次数
WORKERS      = 24
TIMEOUT      = 20
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", "ignore")

# ---------------- 股票池（分页拉全A，剔除ST/退）----------------
def fetch_universe():
    out, pn, pz = [], 1, 100
    while True:
        url = (f"https://push2.eastmoney.com/api/qt/clist/get?pn={pn}&pz={pz}&po=1&np=1"
               "&fltt=2&invt=2&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f12,f14")
        d = json.loads(http_get(url)).get("data")
        if not d or not d.get("diff"):
            break
        for it in d["diff"]:
            code, name = it["f12"], it["f14"]
            if "ST" in name or "退" in name or "PT" in name:
                continue
            if code.startswith("6"):
                secid = f"1.{code}"
            elif code.startswith(("0", "3")):
                secid = f"0.{code}"
            else:
                continue
            out.append((code, name, secid))
        if pn * pz >= d.get("total", 0):
            break
        pn += 1
    return out

# ---------------- 单只K线 ----------------
def fetch_kline(secid):
    url = ("https://push2his.eastmoney.com/api/qt/stock/kline/get"
           f"?secid={secid}&fields1=f1,f2,f3,f4,f5,f6"
           "&fields2=f51,f52,f53,f54,f55,f56,f57"
           f"&klt=101&fqt=1&beg={DATA_BEG}&end={DATA_END}")
    obj = json.loads(http_get(url))
    d = obj.get("data")
    if not d or not d.get("klines"):
        return None
    rows = []
    for line in d["klines"]:
        p = line.split(",")
        rows.append({"date": p[0], "open": float(p[1]), "close": float(p[2]),
                     "high": float(p[3]), "low": float(p[4])})
    return rows

def ma(vals, n, i):
    if i + 1 < n:
        return None
    return sum(vals[i - n + 1:i + 1]) / n

def limit_pct(code):
    return 0.20 if code.startswith("30") or code.startswith("688") else 0.10

def count_limit_ups(rows, i, lookback, lim):
    """统计 [i-lookback+1, i] 内涨停天数（收盘涨幅≥涨停-0.5%）"""
    cnt = 0
    for j in range(max(1, i - lookback + 1), i + 1):
        prev = rows[j - 1]["close"]
        if prev > 0 and rows[j]["close"] / prev - 1 >= lim - 0.005:
            cnt += 1
    return cnt

# ---------------- 单只回测 ----------------
def backtest_one(code, name, rows):
    closes = [r["close"] for r in rows]
    lim = limit_pct(code)
    n = len(rows)
    trades = []
    for i in range(1, n):
        date = rows[i]["date"]
        if not (SIGNAL_START <= date <= SIGNAL_END):
            continue
        ma2, ma5, ma13 = ma(closes, 2, i), ma(closes, 5, i), ma(closes, 13, i)
        ma2p, ma5p = ma(closes, 2, i - 1), ma(closes, 5, i - 1)
        if None in (ma2, ma5, ma13, ma2p, ma5p):
            continue
        if not (ma2 > ma5 and ma2p <= ma5p and closes[i] >= ma13):
            continue
        if i + 1 >= n:
            continue  # 没有次日，无法卖出
        rec = {"code": code, "name": name, "sig_date": date,
               "leader": count_limit_ups(rows, i, LEADER_LOOKBACK, lim) >= LEADER_MIN_LIMITS}
        sig_limit_up = closes[i] / closes[i - 1] - 1 >= lim - 0.005
        # 变体A：信号日尾盘买(close[i])，次日卖。信号日涨停封死→买不进，跳过A
        if not sig_limit_up:
            buy = closes[i]
            rec["A_open"]  = rows[i + 1]["open"]  / buy - 1 - ROUND_TRIP_COST
            rec["A_close"] = rows[i + 1]["close"] / buy - 1 - ROUND_TRIP_COST
        # 变体C：次日早盘竞价买(open[i+1])，再隔一天(i+2)卖。次日一字涨停开盘→买不进，跳过C
        if i + 2 < n:
            o1 = rows[i + 1]["open"]
            if o1 / closes[i] - 1 < lim - 0.005:
                rec["C_open"]  = rows[i + 2]["open"]  / o1 - 1 - ROUND_TRIP_COST
                rec["C_close"] = rows[i + 2]["close"] / o1 - 1 - ROUND_TRIP_COST
        trades.append(rec)
    return trades

# ---------------- 统计 ----------------
def stats(returns):
    if not returns:
        return None
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]
    avg_w = statistics.mean(wins) if wins else 0
    avg_l = statistics.mean(losses) if losses else 0
    pl = (avg_w / abs(avg_l)) if avg_l != 0 else float("inf")
    return {"n": len(returns), "winrate": len(wins) / len(returns),
            "avg": statistics.mean(returns), "median": statistics.median(returns),
            "best": max(returns), "worst": min(returns), "pl": pl}

def pr(title, s):
    if not s:
        print(f"  {title:<12}: 无交易")
        return
    print(f"  {title:<12}: {s['n']:>5}笔  胜率{s['winrate']*100:4.1f}%  "
          f"均{s['avg']*100:+5.2f}%  中位{s['median']*100:+5.2f}%  "
          f"盈亏比{s['pl']:.2f}  最好{s['best']*100:+.0f}% 最差{s['worst']*100:+.0f}%")

def main():
    print(">> 拉取股票池...")
    uni = fetch_universe()
    print(f"   股票池：{len(uni)} 只")

    all_trades, done, fail = [], 0, 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(fetch_kline, secid): (code, name) for code, name, secid in uni}
        for fut in as_completed(futs):
            code, name = futs[fut]
            done += 1
            try:
                rows = fut.result()
                if rows:
                    all_trades.extend(backtest_one(code, name, rows))
            except Exception:
                fail += 1
            if done % 800 == 0:
                print(f"   进度 {done}/{len(uni)}  信号 {len(all_trades)}  失败 {fail}")

    leaders = [t for t in all_trades if t["leader"]]
    print(f"\n>> 完成。失败 {fail} 只。窗口 {SIGNAL_START} ~ {SIGNAL_END}  成本往返{ROUND_TRIP_COST*100:.2f}%")
    print(f">> 信号总数 {len(all_trades)} 笔，其中龙头(近{LEADER_LOOKBACK}天涨停≥{LEADER_MIN_LIMITS}次) {len(leaders)} 笔\n")

    col = lambda ts, k: [t[k] for t in ts if k in t]
    print("===== 全部信号（不选股）=====")
    print(" [A]信号日尾盘买,次日卖（剔除信号日涨停买不进）")
    pr("A 次日竞价卖", stats(col(all_trades, "A_open")))
    pr("A 次日收盘卖", stats(col(all_trades, "A_close")))
    print(" [C]次日早盘竞价买,再隔日卖（剔除一字板买不进）")
    pr("C 隔日竞价卖", stats(col(all_trades, "C_open")))
    pr("C 隔日收盘卖", stats(col(all_trades, "C_close")))
    print("\n===== 仅龙头股 =====")
    print(" [A]信号日尾盘买,次日卖")
    pr("A 次日竞价卖", stats(col(leaders, "A_open")))
    pr("A 次日收盘卖", stats(col(leaders, "A_close")))
    print(" [C]次日早盘竞价买,再隔日卖")
    pr("C 隔日竞价卖", stats(col(leaders, "C_open")))
    pr("C 隔日收盘卖", stats(col(leaders, "C_close")))

    # 龙头组按月看稳定性（变体C 次日竞价买,隔日竞价卖）
    by_month = {}
    for t in leaders:
        if "C_open" in t:
            by_month.setdefault(t["sig_date"][:7], []).append(t["C_open"])
    print("\n----- 龙头组·变体C(次日竞价买,隔日竞价卖)·分月 -----")
    for m in sorted(by_month):
        s = stats(by_month[m])
        print(f"   {m}: {s['n']:>3}笔  胜率{s['winrate']*100:4.1f}%  均{s['avg']*100:+5.2f}%")

if __name__ == "__main__":
    main()
