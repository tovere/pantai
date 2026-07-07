#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略二上实盘前的两项验证：
  1) 分月稳定性：按进场月份看 底仓 / +安全做T 的胜率与均收益
  2) 资金曲线/最大回撤：5仓位等权轮动模拟（按已实现权益计回撤，偏保守低估盘中浮亏）
"""
import json, urllib.request, statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

SIGNAL_START, SIGNAL_END = "2025-07-01", "2026-06-29"
DATA_BEG, COST, T_COST, CAP = "20250101", 0.001, 0.001, 0.33
N_SLOTS = 5
UA="Mozilla/5.0"

def http_get(u):
    return urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":UA}),timeout=20).read().decode("utf-8","ignore")

def fetch_universe():
    out,pn=[],1
    while True:
        u=(f"https://push2.eastmoney.com/api/qt/clist/get?pn={pn}&pz=100&po=1&np=1"
           "&fltt=2&invt=2&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f12,f14")
        d=json.loads(http_get(u)).get("data")
        if not d or not d.get("diff"): break
        for it in d["diff"]:
            c,nm=it["f12"],it["f14"]
            if "ST" in nm or "退" in nm or "PT" in nm or c.startswith("688"): continue
            s=f"1.{c}" if c.startswith("6") else (f"0.{c}" if c.startswith(("0","3")) else None)
            if s: out.append((c,s))
        if pn*100>=d.get("total",0): break
        pn+=1
    return out

def fetch_kline(s):
    u=("https://push2his.eastmoney.com/api/qt/stock/kline/get"
       f"?secid={s}&fields1=f1&fields2=f51,f52,f53,f54,f55,f56&klt=101&fqt=1&beg={DATA_BEG}&end=20500101")
    d=json.loads(http_get(u)).get("data")
    if not d or not d.get("klines"): return None
    return [l.split(",") for l in d["klines"]]

def run_one(code, rows):
    if len(rows)<70: return []
    dates=[r[0] for r in rows]
    O=[float(r[1]) for r in rows]; C=[float(r[2]) for r in rows]; L=[float(r[4]) for r in rows]
    lim=0.20 if code.startswith(("30","688")) else 0.10
    ma=lambda p,k: sum(C[k-p+1:k+1])/p
    n=len(rows)
    ma5=[sum(C[k-4:k+1])/5 if k>=4 else None for k in range(n)]
    above=[ma5[k] is not None and C[k]>=ma5[k] for k in range(n)]
    hold=lambda k: above[k] or (k>0 and above[k-1])   # B:容忍单日浅破
    out=[]; i=63
    while i<n-1:
        s=0; k=i
        while k>=5 and hold(k): s+=1; k-=1
        fresh=above[i] and s==3
        up=C[i]>=ma(60,i) and ma(60,i)>ma(60,i-10)
        chg=C[i]/C[i-1]-1
        if fresh and up and chg>=-0.05 and chg<lim-0.005 and SIGNAL_START<=dates[i]<=SIGNAL_END:
            buy=C[i]; stop=buy*0.95               # -5%硬止损
            j=i+1; sell=None
            while j<n:
                if O[j]<=stop: sell=O[j]; break
                if L[j]<=stop: sell=stop; break
                if not hold(j): sell=C[j]; break   # 连2日破MA5→收盘卖
                j+=1
            if sell is None: sell=C[n-1]; j=n-1
            jj=j
            base=sell/buy-1-COST
            safe=0.0
            for d in range(i+1,jj+1):
                if O[d]>C[d-1] and C[d]<=O[d]:
                    g=(O[d]-L[d])/C[i]*CAP-T_COST
                    if g>0: safe+=g
            out.append({"code":code,"entry":dates[i],"exit":dates[jj],
                        "base":base,"safe":base+safe})
            i=jj+1
        else:
            i+=1
    return out

def monthly(trades, key):
    by={}
    for t in trades: by.setdefault(t["entry"][:7],[]).append(t[key])
    print(f"  {'月份':<9}{'笔数':>6}{'胜率':>8}{'均收益':>9}")
    for m in sorted(by):
        rs=by[m]; wr=sum(1 for r in rs if r>0)/len(rs)*100
        print(f"  {m:<9}{len(rs):>6}{wr:>7.1f}%{statistics.mean(rs)*100:>+8.2f}%")

def simulate(trades, key):
    by_entry={}
    for t in trades: by_entry.setdefault(t["entry"],[]).append(t)
    for v in by_entry.values(): v.sort(key=lambda x:x["code"])
    dates=sorted(set([t["entry"] for t in trades]+[t["exit"] for t in trades]))
    cash=1.0; pos=[]; curve=[]
    for dt in dates:
        keep=[]
        for p in pos:
            if p["exit"]==dt: cash+=p["cap"]*(1+p["ret"])
            else: keep.append(p)
        pos=keep
        eq=cash+sum(p["cap"] for p in pos)
        for t in by_entry.get(dt,[]):
            if len(pos)>=N_SLOTS or cash<=1e-9: break
            commit=min(eq/N_SLOTS, cash); cash-=commit
            pos.append({"exit":t["exit"],"cap":commit,"ret":t[key]})
        curve.append(cash+sum(p["cap"] for p in pos))
    peak=curve[0]; mdd=0
    for v in curve:
        peak=max(peak,v); mdd=max(mdd,(peak-v)/peak)
    return curve[-1]-1, mdd

def main():
    uni=fetch_universe(); print(f"股票池 {len(uni)} 只，回测中...")
    A=[]; done=0
    with ThreadPoolExecutor(max_workers=24) as ex:
        futs={ex.submit(fetch_kline,s):c for c,s in uni}
        for f in as_completed(futs):
            done+=1; c=futs[f]
            try:
                ks=f.result()
                if ks: A.extend(run_one(c,ks))
            except Exception: pass
            if done%1500==0: print(f"  {done}/{len(uni)} 交易{len(A)}")
    print(f"\n>> 总交易 {len(A)} 笔  区间 {SIGNAL_START}~{SIGNAL_END}\n")

    print("===== 1) 分月稳定性 · 底仓 =====")
    monthly(A,"base")
    print("\n===== 分月稳定性 · +安全做T =====")
    monthly(A,"safe")

    print(f"\n===== 2) 资金曲线 · {N_SLOTS}仓位等权轮动 =====")
    for name,key in [("底仓","base"),("+安全做T","safe")]:
        tot,mdd=simulate(A,key)
        print(f"  {name:<10} 期间总收益 {tot*100:+.1f}%   最大回撤 {mdd*100:.1f}%")
    print("  (注:回撤按已实现权益计，未marktomarket持仓浮亏，真实回撤更深)")

if __name__=="__main__": main()
