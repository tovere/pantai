#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
裸信号 + 次日早盘竞价买 + 条件卖出：
  卖出日(i+2)  高开 -> 卖在最高点(理想上限) / 收盘卖(现实)
              低开 -> 开盘附近卖(代理"10分钟后", 日线无分钟数据)
数据：东方财富前复权日线。注意：'卖在最高点'是抓不到的上限，仅作天花板参考。
"""
import json, urllib.request, statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

SIGNAL_START, SIGNAL_END = "2025-07-01", "2026-06-29"
DATA_BEG, COST = "20250401", 0.001
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

def klim(c): return 0.20 if c.startswith(("30","688")) else 0.10

def run_one(code, rows):
    if len(rows)<25: return []
    O=[float(r[1]) for r in rows]; C=[float(r[2]) for r in rows]
    H=[float(r[3]) for r in rows]; dates=[r[0] for r in rows]
    ma=lambda p,j: sum(C[j-p+1:j+1])/p
    lim=klim(code); out=[]
    for i in range(13, len(rows)-2):
        if not (SIGNAL_START<=dates[i]<=SIGNAL_END): continue
        ma2,ma5,ma13=ma(2,i),ma(5,i),ma(13,i); ma2p,ma5p=ma(2,i-1),ma(5,i-1)
        if not (ma2>ma5 and ma2p<=ma5p and C[i]>=ma13): continue   # 裸信号
        buy=O[i+1]
        if buy/C[i]-1 >= lim-0.005: continue        # 次日一字板买不进
        gap = O[i+2]/C[i+1]-1                        # 卖出日高开/低开
        rec={"gap_up": gap>0}
        if gap>0:   # 高开
            rec["sell_best"]  = H[i+2]/buy-1-COST    # 卖最高点(上限)
            rec["sell_close"] = C[i+2]/buy-1-COST    # 收盘卖
        else:       # 低开
            rec["sell_low_proxy"] = O[i+2]/buy-1-COST  # 开盘附近(代理10分钟)
        out.append(rec)
    return out

def stats(rs):
    if not rs: return None
    w=[r for r in rs if r>0]
    return {"n":len(rs),"wr":len(w)/len(rs),"avg":statistics.mean(rs),"med":statistics.median(rs),
            "best":max(rs),"worst":min(rs)}

def pr(t,s):
    if not s: print(f"  {t:<22}: 无"); return
    print(f"  {t:<22}: {s['n']:>5}笔 胜率{s['wr']*100:4.1f}% 均{s['avg']*100:+5.2f}% 中位{s['med']*100:+5.2f}% 最好{s['best']*100:+.0f}% 最差{s['worst']*100:+.0f}%")

def main():
    uni=fetch_universe(); print(f"股票池 {len(uni)} 只，扫描中...")
    all_recs=[]; done=0
    with ThreadPoolExecutor(max_workers=24) as ex:
        futs={ex.submit(fetch_kline,s):c for c,n,s in uni}
        for f in as_completed(futs):
            c=futs[f]; done+=1
            try:
                ks=f.result()
                if ks: all_recs.extend(run_one(c,ks))
            except Exception: pass
            if done%1000==0: print(f"  {done}/{len(uni)} 信号{len(all_recs)}")

    ups=[r for r in all_recs if r["gap_up"]]
    downs=[r for r in all_recs if not r["gap_up"]]
    n=len(all_recs)
    print(f"\n>> 裸信号(可买) {n} 笔  其中卖出日 高开 {len(ups)}({len(ups)/n*100:.0f}%) / 低开 {len(downs)}({len(downs)/n*100:.0f}%)\n")
    print("--- 分组结果 ---")
    pr("高开·卖在最高点(上限)", stats([r["sell_best"]  for r in ups]))
    pr("高开·收盘卖(现实)",     stats([r["sell_close"] for r in ups]))
    pr("低开·开盘附近卖(代理)",  stats([r["sell_low_proxy"] for r in downs]))
    print("\n--- 组合整套规则 ---")
    ideal=[r["sell_best"] if r["gap_up"] else r["sell_low_proxy"] for r in all_recs]
    real =[r["sell_close"] if r["gap_up"] else r["sell_low_proxy"] for r in all_recs]
    pr("理想上限(高开必中最高点)", stats(ideal))
    pr("现实版(高开吃到收盘)",     stats(real))

if __name__=="__main__": main()
