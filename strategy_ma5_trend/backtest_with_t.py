#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略二 + 做T 叠加回测：
  底仓：突破买入，沿MA5持有，跌破MA5清仓（同 backtest.py）
  做T ：持有期间每日，高开(open>昨收)则 开盘卖、当日最低接回，吃 (open-low)*CAPTURE
        低开/平开不动。range太小(不值做T成本)则跳过。
注意：日线无分钟数据，'最低接回'是抓不到的上限——做T结果结构性偏乐观，见 README。
"""
import json, urllib.request, statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

SIGNAL_START, SIGNAL_END = "2025-07-01", "2026-06-29"
DATA_BEG, COST = "20250101", 0.001
T_COST = 0.001                 # 每次做T(卖+买)成本
CAPTURE_CEIL = 1.00            # 理想上限：吃满 open-low 全程
CAPTURE_REAL = 0.33            # 现实版：只吃到 ~1/3
UA = "Mozilla/5.0"

def http_get(u):
    return urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=20).read().decode("utf-8","ignore")

def fetch_universe():
    out, pn = [], 1
    while True:
        u=(f"https://push2.eastmoney.com/api/qt/clist/get?pn={pn}&pz=100&po=1&np=1"
           "&fltt=2&invt=2&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f12,f14")
        d=json.loads(http_get(u)).get("data")
        if not d or not d.get("diff"): break
        for it in d["diff"]:
            c,nm=it["f12"],it["f14"]
            if "ST" in nm or "退" in nm or "PT" in nm: continue
            if c.startswith("688"): continue
            if c.startswith("6"): s=f"1.{c}"
            elif c.startswith(("0","3")): s=f"0.{c}"
            else: continue
            out.append((c,nm,s))
        if pn*100>=d.get("total",0): break
        pn+=1
    return out

def fetch_kline(s):
    u=("https://push2his.eastmoney.com/api/qt/stock/kline/get"
       f"?secid={s}&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57"
       f"&klt=101&fqt=1&beg={DATA_BEG}&end=20500101")
    d=json.loads(http_get(u)).get("data")
    if not d or not d.get("klines"): return None
    return [l.split(",") for l in d["klines"]]

def t_parts(O, L, C, i, j, capture):
    """
    持有区间(i,j] 做T收益拆分(占成本C[i]比例)：
      safe     : 高开回落日(收盘≤开盘) 做T必成功，稳赚
      risk_win : 高开冲高日 接到低点(赚)
      risk_fly : 高开冲高日 卖飞(开盘卖、收盘追回) 的亏损(负)
    """
    safe=risk_win=risk_fly=0.0; ndays=0
    for d in range(i+1, j+1):
        if O[d] <= C[d-1]:                     # 非高开，不做T
            continue
        rng=(O[d]-L[d])/C[i]*capture
        if C[d] <= O[d]:                       # 高开回落 → 必成功
            if rng>T_COST: safe+=rng-T_COST; ndays+=1
        else:                                  # 高开冲高 → 有卖飞风险
            if rng>T_COST: risk_win+=rng-T_COST; ndays+=1
            risk_fly+=(O[d]-C[d])/C[i]-T_COST  # 卖飞：卖在open接在close(更高)，负值
    return safe, risk_win, risk_fly, ndays

def run_one(code, rows):
    if len(rows)<70: return []
    dates=[r[0] for r in rows]
    O=[float(r[1]) for r in rows]; C=[float(r[2]) for r in rows]
    H=[float(r[3]) for r in rows]; L=[float(r[4]) for r in rows]
    lim=0.20 if code.startswith(("30","688")) else 0.10
    ma=lambda p,k: sum(C[k-p+1:k+1])/p
    out=[]; i=63; n=len(rows)
    while i<n-1:
        fresh=(C[i]>ma(5,i) and C[i-1]>ma(5,i-1) and C[i-2]>ma(5,i-2) and C[i-3]<=ma(5,i-3))
        up=C[i]>=ma(60,i) and ma(60,i)>ma(60,i-10)
        chg=C[i]/C[i-1]-1
        if fresh and up and chg>=-0.05 and chg<lim-0.005 and SIGNAL_START<=dates[i]<=SIGNAL_END:
            j=i+1
            while j<n and C[j]>=ma(5,j): j+=1
            jj=j if j<n else n-1
            base=C[jj]/C[i]-1-COST
            safe,rw,rf,nd=t_parts(O,L,C,i,jj,CAPTURE_REAL)
            out.append({"base":base,
                        "safe":base+safe,                 # 只做安全的(高开回落)做T
                        "all_win":base+safe+rw,           # 全做且全接到低点(乐观)
                        "all_fly":base+safe+rf,            # 冲高日全卖飞(悲观)
                        "tdays":nd})
            i=jj+1
        else:
            i+=1
    return out

def stats(rs):
    w=[r for r in rs if r>0]
    return (len(rs), len(w)/len(rs)*100, statistics.mean(rs)*100, statistics.median(rs)*100)

def main():
    uni=fetch_universe(); print(f"股票池(剔ST/科创) {len(uni)} 只，回测中...")
    A=[]; done=0
    with ThreadPoolExecutor(max_workers=24) as ex:
        futs={ex.submit(fetch_kline,s):c for c,n_,s in uni}
        for f in as_completed(futs):
            done+=1; c=futs[f]
            try:
                ks=f.result()
                if ks: A.extend(run_one(c,ks))
            except Exception: pass
            if done%1500==0: print(f"  {done}/{len(uni)} 交易{len(A)}")

    avg_tdays=statistics.mean(t["tdays"] for t in A)
    print(f"\n>> 区间 {SIGNAL_START}~{SIGNAL_END}  底仓成本{COST*100:.2f}% 做T成本{T_COST*100:.2f}%/次 吃幅{int(CAPTURE_REAL*100)}%")
    print(f">> 交易 {len(A)} 笔，平均每笔做T {avg_tdays:.1f} 次\n")
    print(f"  {'方案':<26}{'笔数':>6}{'胜率':>8}{'均收益':>9}{'中位':>8}")
    for name,key in [("纯趋势(不做T)","base"),
                     ("+做T 只做高开回落(安全)","safe"),
                     ("+做T 全做·全接到低点(乐观)","all_win"),
                     ("+做T 冲高日全卖飞(悲观)","all_fly")]:
        n,wr,avg,med=stats([t[key] for t in A])
        print(f"  {name:<26}{n:>6}{wr:>7.1f}%{avg:>+8.2f}%{med:>+7.2f}%")

if __name__=="__main__": main()
