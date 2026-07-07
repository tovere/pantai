#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略二回测：上升趋势 + 连续3日站上MA5(新突破)买入 → 收盘跌破MA5卖出。
持有周期不固定（沿5日线持股）。数据：项目 data_cache（默认 2025 起）。
"""
import os
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from cache_data import daily_kline, universe

SIGNAL_START, SIGNAL_END = "2025-07-01", "2026-06-29"
COST = 0.001
N_ABOVE = 3

def run_one(code, rows):
    if len(rows)<70: return []
    dates=[r[0] for r in rows]; O=[float(r[1]) for r in rows]
    C=[float(r[2]) for r in rows]; L=[float(r[4]) for r in rows]
    lim=0.20 if code.startswith(("30","688")) else 0.10
    ma=lambda p,j: sum(C[j-p+1:j+1])/p
    n=len(rows)
    ma5=[sum(C[k-4:k+1])/5 if k>=4 else None for k in range(n)]
    above=[ma5[k] is not None and C[k]>=ma5[k] for k in range(n)]
    hold=lambda k: above[k] or (k>0 and above[k-1])   # B:容忍单日浅破,连2日破才算断
    trades=[]; i=63
    while i<n-1:
        # 连续站上MA5天数(容忍单日浅破)
        s=0; k=i
        while k>=5 and hold(k): s+=1; k-=1
        fresh = above[i] and s==3                 # 今日在线上 + 刚满3天
        up = C[i]>=ma(60,i) and ma(60,i)>ma(60,i-10)
        chg = C[i]/C[i-1]-1
        buyable = chg < lim-0.005          # 信号日涨停封死→买不进
        if fresh and up and chg>=-0.05 and buyable and SIGNAL_START<=dates[i]<=SIGNAL_END:
            buy=C[i]; stop=buy*0.95               # -5%硬止损
            j=i+1; sell=None; closed=True
            while j<n:
                if O[j]<=stop: sell=O[j]; break    # 跳空低开破止损→开盘成交(更差)
                if L[j]<=stop: sell=stop; break    # 盘中触止损→止损价成交
                if not hold(j): sell=C[j]; break   # 连2日破MA5→收盘卖
                j+=1
            if sell is None: sell=C[n-1]; j=n-1; closed=False
            held=j-i
            trades.append({"ret":sell/buy-1-COST,"held":held,"closed":closed})
            i=j+1                                  # 平仓后再找下一笔
        else:
            i+=1
    return trades

def main():
    uni=universe(); print(f"缓存股票池(剔ST/科创/创业板) {len(uni)} 只，回测中...")
    all_t=[]; done=0; failed=0
    with ThreadPoolExecutor(max_workers=24) as ex:
        futs={ex.submit(daily_kline,s):c for c,n_,s in uni}
        for f in as_completed(futs):
            done+=1; c=futs[f]
            try:
                ks=f.result()
                if ks: all_t.extend(run_one(c,ks))
                else: failed+=1
            except Exception: failed+=1
            if done%1500==0: print(f"  {done}/{len(uni)} 交易{len(all_t)} 失败{failed}")

    rets=[t["ret"] for t in all_t]
    wins=[r for r in rets if r>0]
    losses=[r for r in rets if r<=0]
    avg_w=statistics.mean(wins) if wins else 0
    avg_l=statistics.mean(losses) if losses else 0
    open_n=sum(1 for t in all_t if not t["closed"])
    print(f"\n>> 区间 {SIGNAL_START}~{SIGNAL_END}  成本往返{COST*100:.2f}%")
    print(f">> 交易总数 {len(all_t)} 笔（其中未平仓强制了结 {open_n} 笔）\n")
    print(f"  胜率        {len(wins)/len(rets)*100:.1f}%")
    print(f"  单笔均收益   {statistics.mean(rets)*100:+.2f}%")
    print(f"  中位数      {statistics.median(rets)*100:+.2f}%")
    print(f"  平均盈利    {avg_w*100:+.2f}%   平均亏损 {avg_l*100:+.2f}%")
    print(f"  盈亏比      {avg_w/abs(avg_l):.2f}" if avg_l else "  盈亏比 inf")
    print(f"  平均持有    {statistics.mean(t['held'] for t in all_t):.1f} 个交易日")
    print(f"  最好/最差   {max(rets)*100:+.0f}% / {min(rets)*100:+.0f}%")
    # 按持有天数看
    print("\n  --- 收益分布 ---")
    buckets=[("亏损>10%",lambda r:r<=-0.10),("亏5~10%",lambda r:-0.10<r<=-0.05),
             ("亏0~5%",lambda r:-0.05<r<=0),("赚0~5%",lambda r:0<r<=0.05),
             ("赚5~15%",lambda r:0.05<r<=0.15),("赚>15%",lambda r:r>0.15)]
    for name,fn in buckets:
        cnt=sum(1 for r in rets if fn(r))
        print(f"  {name:<10}: {cnt:>5} 笔 ({cnt/len(rets)*100:4.1f}%)")

if __name__=="__main__": main()
