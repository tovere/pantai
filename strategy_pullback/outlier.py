#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""策略三 outlier 验证：top大肉是否数据毛刺(超物理上限) + 剔掉头部后期望是否还正。"""
import json, subprocess, statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
SIGNAL_START, SIGNAL_END = "2025-07-01", "2026-06-29"
DATA_BEG, COST = "20250101", 0.001
N_SLOTS=5; UA="Mozilla/5.0"
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
            out.append((c,nm, f"1.{c}" if c.startswith("6") else f"0.{c}"))
        if pn*100>=d.get("total",0): break
        pn+=1
    return out
def kl(s):
    d=json.loads(get(f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={s}&fields1=f1&fields2=f51,f52,f53,f54,f55,f56&klt=101&fqt=1&beg={DATA_BEG}&end=20500101")).get("data")
    return [l.split(",") for l in d["klines"]] if d and d.get("klines") else None
def run(code, name, rows):
    if len(rows)<70: return []
    dates=[r[0] for r in rows]; O=[float(r[1]) for r in rows]; C=[float(r[2]) for r in rows]
    L=[float(r[4]) for r in rows]; V=[float(r[5]) for r in rows]
    lim=0.20 if code.startswith("30") else 0.10
    n=len(rows)
    ma20=[sum(C[k-19:k+1])/20 if k>=19 else None for k in range(n)]
    ma60=[sum(C[k-59:k+1])/60 if k>=59 else None for k in range(n)]
    out=[]; i=63
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
            out.append({"code":code,"name":name,"entry":dates[i],"exit":dates[j],
                        "held":j-i,"buy":round(buy,2),"sell":round(sell,2),"ret":sell/buy-1-COST})
            i=j+1
        else: i+=1
    return out
def main():
    U=uni(); print(f"主板 {len(U)} 只，回测中...")
    A=[]
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs={ex.submit(kl,s):(c,nm) for c,nm,s in U}
        for f in as_completed(futs):
            c,nm=futs[f]
            try:
                r=f.result()
                if r: A.extend(run(c,nm,r))
            except Exception: pass
    A.sort(key=lambda t:t["ret"], reverse=True)
    print(f"\n交易{len(A)}笔。Top 15 大肉 (物理上限=1.1^持有天数):")
    print("  收益    持有  买入→卖出     上限     代码 名称        进场~出场")
    for t in A[:15]:
        maxposs=(1.10**t["held"]-1)*100
        flag="⚠超上限=毛刺" if (t["ret"]+COST)*100 > maxposs*1.05 else "真实"
        print(f"  {t['ret']*100:>+6.0f}%  {t['held']:>3}天 {t['buy']:>7.2f}→{t['sell']:>7.2f}  ≤{maxposs:>5.0f}%  {flag:<10} {t['code']} {t['name'][:6]:<7} {t['entry']}~{t['exit']}")
    rets=sorted([t["ret"] for t in A])
    n=len(rets)
    def mean(x): return statistics.mean(x)*100 if x else 0
    print(f"\n  全部 {n}笔 均收益 {mean(rets):+.2f}%")
    print(f"  剔掉最赚的1% ({n//100}笔) 后 均收益 {mean(rets[:n-n//100]):+.2f}%")
    print(f"  剔掉最赚的5% ({n//20}笔) 后 均收益 {mean(rets[:n-n//20]):+.2f}%")
    # 物理毛刺总览
    glitch=[t for t in A if (t["ret"]+COST) > (1.10**t["held"])-1 + 0.02]
    print(f"\n  疑似数据毛刺(超物理上限)的交易: {len(glitch)} 笔 / {n}")
    if glitch:
        print(f"  剔掉毛刺后 均收益 {mean([t['ret'] for t in A if t not in glitch]):+.2f}%")
if __name__=="__main__": main()
