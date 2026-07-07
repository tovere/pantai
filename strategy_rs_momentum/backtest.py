#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略五：相对强度选股轮动(个股版动量轮动)。
  池: 主板, 剔ST/科创/创业
  合格: 站上MA20 + 当日成交额≥1亿 + 非异动(近3日累计<20%)
  打分: 近20日涨幅; 每5交易日持最强N只; 全不达标→空仓
对比ETF轮动。毛收益(未扣个股印花税/佣金,见说明)。
"""
import json, subprocess, statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
DATA_BEG="20250101"; UA="Mozilla/5.0"; MINAMT=1e8
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
            out.append((c,nm))
        if pn*100>=d.get("total",0): break
        pn+=1
    return out
def kl(c):
    sec=f"1.{c}" if c.startswith("6") else f"0.{c}"
    d=json.loads(get(f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={sec}&fields1=f1&fields2=f51,f53,f57&klt=101&fqt=1&beg={DATA_BEG}&end=20500101")).get("data")
    if not d or not d.get("klines"): return None
    return [(x.split(",")[0],float(x.split(",")[1]),float(x.split(",")[2])) for x in d["klines"]]  # date,close,amt
def backtest(series, N, WIN, STEP):
    alld=sorted(set(d for s in series.values() for d,_,_ in s))
    idx={c:{x[0]:i for i,x in enumerate(s)} for c,s in series.items()}
    cl ={c:[x[1] for x in s] for c,s in series.items()}
    am ={c:[x[2] for x in s] for c,s in series.items()}
    eq=1.0; curve=[]
    for t in range(60,len(alld)-1,STEP):
        d=alld[t]; nxt=alld[min(t+STEP,len(alld)-1)]; sc=[]
        for c,s in series.items():
            i=idx[c].get(d)
            if i is None or i<WIN: continue
            if cl[c][i]<sum(cl[c][i-19:i+1])/20: continue       # 站上MA20
            if am[c][i]<MINAMT: continue                         # 流动性
            if cl[c][i]/cl[c][i-3]-1>=0.20: continue             # 非异动
            sc.append((cl[c][i]/cl[c][i-WIN]-1,c))
        sc.sort(reverse=True); picks=[c for _,c in sc[:N]]
        if not picks: curve.append(eq); continue
        rs=[]
        for c in picks:
            i,j=idx[c].get(d),idx[c].get(nxt)
            if i is not None and j is not None: rs.append(cl[c][j]/cl[c][i]-1)
        if rs: eq*=(1+sum(rs)/len(rs))
        curve.append(eq)
    peak=curve[0]; mdd=0
    for v in curve: peak=max(peak,v); mdd=max(mdd,(peak-v)/peak)
    return eq-1,mdd
def main():
    U=uni(); print(f"主板 {len(U)} 只，拉K线中...")
    series={}; done=0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs={ex.submit(kl,c):(c,n) for c,n in U}
        for f in as_completed(futs):
            done+=1; c,n=futs[f]
            try:
                r=f.result()
                if r and len(r)>80: series[c]=(r);
            except Exception: pass
            if done%800==0: print(f"  {done}/{len(U)}")
    NAME={c:n for c,n in U}
    print(f"\n拉到 {len(series)} 只。参数网格 (毛收益/回撤):")
    for WIN in (10,20):
        for N in (3,5,10):
            tot,mdd=backtest(series,N,WIN,5)
            print(f"  窗口{WIN}日 持{N}只 周调: {tot*100:>+7.1f}% / 回撤{mdd*100:4.1f}%")
    # 当前最强(20日窗口)
    alld=sorted(set(d for s in series.values() for d,_,_ in s)); d=alld[-1]
    idx={c:{x[0]:i for i,x in enumerate(s)} for c,s in series.items()}
    cl ={c:[x[1] for x in s] for c,s in series.items()}; am={c:[x[2] for x in s] for c,s in series.items()}
    rk=[]
    for c,s in series.items():
        i=idx[c].get(d)
        if i is None or i<20: continue
        if cl[c][i]<sum(cl[c][i-19:i+1])/20 or am[c][i]<MINAMT or cl[c][i]/cl[c][i-3]-1>=0.20: continue
        rk.append((cl[c][i]/cl[c][i-20]-1,c))
    rk.sort(reverse=True)
    print(f"\n>>> 当前({d}) 相对强度前12 (近20日涨幅, 已过滤站上MA20/流动性/非异动):")
    for mom,c in rk[:12]:
        print(f"  {c} {NAME.get(c,'')[:6]:<7} 近20日{mom*100:+6.1f}%")
if __name__=="__main__": main()
