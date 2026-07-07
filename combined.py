#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
合并组合回测：策略2(突破·沿MA5) + 策略3(回踩·MA20低吸) 共用仓位池。
对比 S2单跑 / S3单跑 / 合并 的资金曲线与最大回撤(同sim,同股不重复持仓)。
curl后端+低并发。
"""
import json, subprocess, statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
SIGNAL_START, SIGNAL_END = "2025-07-01", "2026-06-29"
DATA_BEG, COST = "20250101", 0.001
UA="Mozilla/5.0"
def get(u,tries=4):
    for _ in range(tries):
        p=subprocess.run(["curl","-s","-m","20","-A",UA,u],capture_output=True,text=True)
        if p.returncode==0 and p.stdout: return p.stdout
    return ""
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
    d=json.loads(get(f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={s}&fields1=f1&fields2=f51,f52,f53,f54,f55,f56&klt=101&fqt=1&beg={DATA_BEG}&end=20500101")).get("data")
    return [l.split(",") for l in d["klines"]] if d and d.get("klines") else None

def trades_of(code, rows):
    if len(rows)<70: return []
    dates=[r[0] for r in rows]; O=[float(r[1]) for r in rows]; C=[float(r[2]) for r in rows]
    L=[float(r[4]) for r in rows]; V=[float(r[5]) for r in rows]
    lim=0.20 if code.startswith("30") else 0.10
    ma=lambda p,k: sum(C[k-p+1:k+1])/p
    n=len(rows)
    ma5=[sum(C[k-4:k+1])/5 if k>=4 else None for k in range(n)]
    ma20=[sum(C[k-19:k+1])/20 if k>=19 else None for k in range(n)]
    ma60=[sum(C[k-59:k+1])/60 if k>=59 else None for k in range(n)]
    above=[ma5[k] is not None and C[k]>=ma5[k] for k in range(n)]
    hold5=lambda k: above[k] or (k>0 and above[k-1])
    out=[]
    # 策略2: 新突破(B)+MA60上行, 出场 hold5断 或 -5%
    i=63
    while i<n-1:
        s=0;k=i
        while k>=5 and hold5(k): s+=1;k-=1
        up=C[i]>=ma(60,i) and ma(60,i)>ma(60,i-10); chg=C[i]/C[i-1]-1
        if above[i] and s==3 and up and chg>=-0.05 and chg<lim-0.005 and SIGNAL_START<=dates[i]<=SIGNAL_END:
            buy=C[i]; stop=buy*0.95; j=i+1; sell=None
            while j<n:
                if O[j]<=stop: sell=O[j]; break
                if L[j]<=stop: sell=stop; break
                if not hold5(j): sell=C[j]; break
                j+=1
            if sell is None: sell=C[n-1]; j=n-1
            out.append({"code":code,"src":"S2","entry":dates[i],"exit":dates[j],"ret":sell/buy-1-COST})
            i=j+1
        else: i+=1
    # 策略3: 回踩MA20缩量, 出场 收盘破MA20 或 -5%
    i=63
    while i<n-1:
        m20,m60,m60p=ma20[i],ma60[i],ma60[i-10]
        if (C[i]>m20>m60 and m60>m60p and max(C[i-9:i+1])>=m20*1.05
            and L[i]<=m20*1.02 and C[i]>=m20 and V[i]<sum(V[i-5:i])/5
            and C[i]/C[i-1]-1>=-0.05 and C[i]/C[i-1]-1<lim-0.005 and SIGNAL_START<=dates[i]<=SIGNAL_END):
            buy=C[i]; stop=buy*0.95; j=i+1; sell=None
            while j<n:
                if O[j]<=stop: sell=O[j]; break
                if L[j]<=stop: sell=stop; break
                if C[j]<ma20[j]: sell=C[j]; break
                j+=1
            if sell is None: sell=C[n-1]; j=n-1
            out.append({"code":code,"src":"S3","entry":dates[i],"exit":dates[j],"ret":sell/buy-1-COST})
            i=j+1
        else: i+=1
    return out

def simulate(trades, N):
    by={}
    for t in trades: by.setdefault(t["entry"],[]).append(t)
    days=sorted(set([t["entry"] for t in trades]+[t["exit"] for t in trades]))
    cash=1.0; pos=[]; curve=[]
    for dt in days:
        keep=[]
        for p in pos:
            if p["exit"]==dt: cash+=p["cap"]*(1+p["ret"])
            else: keep.append(p)
        pos=keep
        held={p["code"] for p in pos}
        eq=cash+sum(p["cap"] for p in pos)
        for t in by.get(dt,[]):
            if len(pos)>=N or cash<=1e-9: break
            if t["code"] in held: continue          # 同股不重复持仓
            commit=min(eq/N,cash); cash-=commit
            pos.append({"code":t["code"],"exit":t["exit"],"cap":commit,"ret":t["ret"]}); held.add(t["code"])
        curve.append(cash+sum(p["cap"] for p in pos))
    peak=curve[0]; mdd=0
    for v in curve: peak=max(peak,v); mdd=max(mdd,(peak-v)/peak)
    return curve[-1]-1, mdd

def main():
    U=uni(); print(f"主板 {len(U)} 只，回测中...")
    A=[]; done=0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs={ex.submit(kl,s):c for c,s in U}
        for f in as_completed(futs):
            done+=1
            try:
                r=f.result()
                if r: A.extend(trades_of(futs[f],r))
            except Exception: pass
            if done%1000==0: print(f"  {done}/{len(U)} 交易{len(A)}")
    s2=[t for t in A if t["src"]=="S2"]; s3=[t for t in A if t["src"]=="S3"]
    wr=lambda x:sum(1 for t in x if t["ret"]>0)/len(x)*100
    av=lambda x:statistics.mean(t["ret"] for t in x)*100
    print(f"\n信号: S2(突破) {len(s2)}笔 胜率{wr(s2):.1f}% 均{av(s2):+.2f}%  |  S3(回踩) {len(s3)}笔 胜率{wr(s3):.1f}% 均{av(s3):+.2f}%")
    print(f"\n  资金曲线对比 (总收益 / 最大回撤):")
    for N in (5,6,8):
        for nm,tr in [("S2单跑",s2),("S3单跑",s3),("合并",A)]:
            tot,mdd=simulate(tr,N)
            print(f"   {N}仓 {nm:<6}: {tot*100:>+7.1f}%  / 回撤 {mdd*100:4.1f}%")
        print()
if __name__=="__main__": main()
