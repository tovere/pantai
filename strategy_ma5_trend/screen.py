#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略二·选股器：排除ST/科创 + 上升趋势 + 连续3日站上MA5 + 当前未跌破MA5。
持有规则(回测在backtest.py)：跌破MA5卖出。
数据：东方财富前复权日线。纯标准库+多线程。
"""
import json, os, subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

TODAY = os.environ.get("SCREEN_DATE", date.today().isoformat())
MIN_DAYS_ABOVE = 3        # 连续站上MA5天数
MIN_AMOUNT = 5e7          # 今日成交额≥5千万
UA = "Mozilla/5.0"

def http_get(u, tries=4, timeout=12):
    # urllib 被 East Money 针对断连，改走 curl
    for t in range(tries):
        p=subprocess.run(["curl","--http1.1","-s","-m",str(timeout),"-A",UA,u],capture_output=True,text=True)
        if p.returncode==0 and p.stdout: return p.stdout
    return ""

def http_json(u, tries=4, timeout=12):
    for _ in range(tries):
        try:
            return json.loads(http_get(u, tries=1, timeout=timeout))
        except json.JSONDecodeError:
            continue
    return {}

def fetch_universe():
    out, pn = [], 1
    while True:
        u=(f"https://push2delay.eastmoney.com/api/qt/clist/get?pn={pn}&pz=100&po=1&np=1"
           "&fltt=2&invt=2&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f12,f14")
        d=http_json(u).get("data")
        if not d or not d.get("diff"): break
        for it in d["diff"]:
            c,nm=it["f12"],it["f14"]
            if "ST" in nm or "退" in nm or "PT" in nm: continue
            if c.startswith("688"): continue      # 排除科创(无权限)
            if c.startswith("3"): continue        # 排除创业板(无权限)
            if c.startswith("6"): s=f"1.{c}"
            elif c.startswith("0"): s=f"0.{c}"
            else: continue
            out.append((c,nm,s))
        if pn*100>=d.get("total",0): break
        pn+=1
    return out

def fetch_kline(s):
    u=("https://push2his.eastmoney.com/api/qt/stock/kline/get"
       f"?secid={s}&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57"
       "&klt=101&fqt=1&beg=20250401&end=20500101")
    d=http_json(u, tries=3, timeout=8).get("data")
    if not d or not d.get("klines"): return None
    return [l.split(",") for l in d["klines"]]

def check(code, name, ks):
    if len(ks) < 70: return None
    dates=[k[0] for k in ks]; closes=[float(k[2]) for k in ks]
    vols=[float(k[5]) for k in ks]; amts=[float(k[6]) for k in ks]
    i=len(ks)-1
    if dates[i] != TODAY: return None
    if amts[i] < MIN_AMOUNT: return None
    ma=lambda p,j: sum(closes[j-p+1:j+1])/p
    a=lambda k: closes[k]>=ma(5,k)
    hold=lambda k: a(k) or (k>0 and a(k-1))        # B:容忍单日浅破,连2日破才算断
    if not a(i): return None                        # 今日须在MA5上方
    # 连续站上MA5天数(容忍单日浅破)
    streak=0; j=i
    while j>=5 and hold(j): streak+=1; j-=1
    if streak < MIN_DAYS_ABOVE: return None        # 连续3日站上MA5
    chg=(closes[i]/closes[i-1]-1)*100
    if chg < -5: return None                       # 当天大跌>5% = 破位/出货，剔除
    # 排除异动票：交易所异常波动标准 连续3日累计涨幅≥20%(主板)/≥30%(创业板)
    abn = 0.30 if code.startswith("30") else 0.20
    if closes[i]/closes[i-3]-1 >= abn: return None
    # 上升趋势：现价≥MA60 且 MA60上行 (MA5<MA10的弱票靠卖出端收紧,不在入场拦)
    ma60,ma60p=ma(60,i),ma(60,i-10)
    if not (closes[i]>=ma60 and ma60>ma60p): return None
    c=closes[i]; ma5=ma(5,i); ma10=ma(10,i); ma20=ma(20,i)
    v20=sum(vols[i-20:i])/20
    return {"code":code,"name":name,"close":round(c,3),"chg":round(chg,2),
            "streak":streak,                        # 连续站上MA5天数
            "fresh": streak==MIN_DAYS_ABOVE,        # 刚满3天=新突破/新买点
            "bias5":round((c/ma5-1)*100,1),         # 距MA5(越小越贴线/止损越近)
            "ma5":round(ma5,2),                     # MA5止损位
            "volr":round(vols[i]/v20,2),"amt":round(amts[i]/1e8,1),
            "p20":round((c/closes[i-20]-1)*100,1),
            "bull": ma5>=ma10>=ma20}                # 短期多头排列

def main():
    uni=fetch_universe(); print(f"股票池(剔ST/科创) {len(uni)} 只，扫描中...", flush=True)
    hits=[]; done=0
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs={ex.submit(fetch_kline,s):(c,n) for c,n,s in uni}
        for f in as_completed(futs):
            c,n=futs[f]; done+=1
            try:
                ks=f.result()
                if ks:
                    r=check(c,n,ks)
                    if r: hits.append(r)
            except Exception: pass
            if done%500==0: print(f"  {done}/{len(uni)} 命中{len(hits)}", flush=True)
    fresh=[h for h in hits if h["fresh"]]          # 新突破(刚满3天)
    # 新突破优先；组内按 今日涨幅 + 量比 强者靠前
    fresh.sort(key=lambda x:(-x["chg"], -x["volr"]))
    print(f"\n>>> 今日({TODAY}) 上升趋势 + 连续≥{MIN_DAYS_ABOVE}日站上MA5 + 未跌破MA5 + 当天未大跌")
    print(f"    共 {len(hits)} 只，其中【新突破(刚满3天=新买点)】 {len(fresh)} 只\n")
    print("===== 新突破（刚满3日站上MA5，最该关注的新买点）=====")
    # 固定模板：代码│名称│现价│今日%│距MA5│MA5止损位≈│量比│额(亿)│连站MA5
    print("代码    名称        现价    今日%   距MA5  MA5止损≈   量比   额(亿)  连站MA5")
    for h in fresh[:40]:
        print(f"{h['code']}  {h['name'][:6]:<7} {h['close']:>7.3f} {h['chg']:>+6.2f} "
              f"{h['bias5']:>+6.1f}% {h['ma5']:>8.2f} {h['volr']:>6.2f} {h['amt']:>6.1f} "
              f"{h['streak']:>5}日")
    if len(fresh)>40: print(f"... 另有 {len(fresh)-40} 只新突破未显示")

if __name__=="__main__": main()
