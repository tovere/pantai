#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
探索入场过滤：在 B+(-5%止损) 卖出基础上，对比不同入场过滤的单笔表现。
  base   : 新突破(连3日站上MA5,B容忍) + 上升趋势(MA60上行)
  +m5m10 : 再加 MA5>MA10
  +阳线   : 再加 连续3日收盘>开盘
  +收涨   : 再加 连续3日收盘>昨收
卖出统一: 连2日破MA5(B) 或 -5%硬止损。
"""
import json, urllib.request, statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
SIGNAL_START, SIGNAL_END = "2025-07-01", "2026-06-29"
COST=0.001; UA="Mozilla/5.0"
def get(u): return urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":UA}),timeout=20).read().decode("utf-8","ignore")
def uni():
    out,pn=[],1
    while True:
        d=json.loads(get(f"https://push2.eastmoney.com/api/qt/clist/get?pn={pn}&pz=100&po=1&np=1&fltt=2&invt=2&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f12,f14")).get("data")
        if not d or not d.get("diff"): break
        for it in d["diff"]:
            c,nm=it["f12"],it["f14"]
            if "ST" in nm or "退" in nm or "PT" in nm or c.startswith("688") or c.startswith("3"): continue
            out.append((c, f"1.{c}" if c.startswith("6") else f"0.{c}"))
        if pn*100>=d.get("total",0): break
        pn+=1
    return out
def kl(s):
    d=json.loads(get(f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={s}&fields1=f1&fields2=f51,f52,f53,f54,f55,f56&klt=101&fqt=1&beg=20250101&end=20500101")).get("data")
    return [l.split(",") for l in d["klines"]] if d and d.get("klines") else None
def run(code, rows):
    if len(rows)<70: return []
    dates=[r[0] for r in rows]; O=[float(r[1]) for r in rows]; C=[float(r[2]) for r in rows]; L=[float(r[4]) for r in rows]
    lim=0.20 if code.startswith("30") else 0.10
    ma=lambda p,k: sum(C[k-p+1:k+1])/p
    n=len(rows)
    ma5=[sum(C[k-4:k+1])/5 if k>=4 else None for k in range(n)]
    above=[ma5[k] is not None and C[k]>=ma5[k] for k in range(n)]
    hold=lambda k: above[k] or (k>0 and above[k-1])
    out=[]; i=63
    while i<n-1:
        s=0;k=i
        while k>=5 and hold(k): s+=1;k-=1
        fresh=above[i] and s==3
        up=C[i]>=ma(60,i) and ma(60,i)>ma(60,i-10)
        chg=C[i]/C[i-1]-1
        if fresh and up and chg>=-0.05 and chg<lim-0.005 and SIGNAL_START<=dates[i]<=SIGNAL_END:
            m5m10=ma(5,i)>ma(10,i)
            yang3=all(C[i-t]>O[i-t] for t in range(3))           # 连3日阳线
            up3=all(C[i-t]>C[i-t-1] for t in range(3))           # 连3日收涨
            # 卖出: B + -5%止损
            buy=C[i]; stop=buy*0.95; j=i+1; sell=None
            while j<n:
                if O[j]<=stop: sell=O[j]; break
                if L[j]<=stop: sell=stop; break
                if not (above[j] or above[j-1]): sell=C[j]; break
                j+=1
            if sell is None: sell=C[n-1]; j=n-1
            out.append((sell/buy-1-COST, m5m10, yang3, up3))
            i=j+1
        else: i+=1
    return out
def stat(name, rs):
    if not rs: print(f"  {name:<24} 无"); return
    w=[r for r in rs if r>0]; ls=[r for r in rs if r<=0]
    aw=statistics.mean(w) if w else 0; al=statistics.mean(ls) if ls else 0
    pl=aw/abs(al) if al else 99
    print(f"  {name:<24} {len(rs):>6}笔 胜率{len(w)/len(rs)*100:4.1f}% 均{statistics.mean(rs)*100:+5.2f}% 盈亏比{pl:.2f}")
def main():
    U=uni(); print(f"主板 {len(U)} 只")
    A=[]
    with ThreadPoolExecutor(max_workers=24) as ex:
        futs={ex.submit(kl,s):c for c,s in U}
        for f in as_completed(futs):
            c=futs[f]
            try:
                r=f.result()
                if r: A.extend(run(c,r))
            except Exception: pass
    print(f"\n基础(新突破+上升趋势)入场 {len(A)} 笔, 卖出=B+(-5%止损)\n")
    stat("base", [r[0] for r in A])
    stat("+MA5>MA10", [r[0] for r in A if r[1]])
    stat("+MA5>MA10+连3阳线", [r[0] for r in A if r[1] and r[2]])
    stat("+MA5>MA10+连3收涨", [r[0] for r in A if r[1] and r[3]])
    stat("(对照)+连3阳线(不加m5m10)", [r[0] for r in A if r[2]])
    stat("(对照)+连3收涨(不加m5m10)", [r[0] for r in A if r[3]])
if __name__=="__main__": main()
