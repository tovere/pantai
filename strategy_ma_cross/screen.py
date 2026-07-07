#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全市场扫描：今日触发 2上穿5金叉 + 现价>=MA13 + 龙头(近10天涨停>=2次)。"""
import json, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

TODAY = "2026-06-29"
LEADER_LOOKBACK, LEADER_MIN = 10, 1
MIN_AMOUNT = 5e7          # 今日成交额>=5千万，保证流动性
UA = "Mozilla/5.0"

def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "ignore")

def fetch_universe():
    out, pn, pz = [], 1, 100
    while True:
        url = (f"https://push2.eastmoney.com/api/qt/clist/get?pn={pn}&pz={pz}&po=1&np=1"
               "&fltt=2&invt=2&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f12,f14")
        d = json.loads(http_get(url)).get("data")
        if not d or not d.get("diff"): break
        for it in d["diff"]:
            code, name = it["f12"], it["f14"]
            if "ST" in name or "退" in name or "PT" in name: continue
            if code.startswith("688"): continue   # 排除科创板(无权限)
            if code.startswith("6"): sec = f"1.{code}"
            elif code.startswith(("0","3")): sec = f"0.{code}"
            else: continue
            out.append((code, name, sec))
        if pn*pz >= d.get("total",0): break
        pn += 1
    return out

def fetch_kline(sec):
    url = ("https://push2his.eastmoney.com/api/qt/stock/kline/get"
           f"?secid={sec}&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57"
           "&klt=101&fqt=1&beg=20250401&end=20500101")
    d = json.loads(http_get(url)).get("data")
    if not d or not d.get("klines"): return None
    return [l.split(",") for l in d["klines"]]

def klim(code): return 0.20 if code.startswith(("30","688")) else 0.10

def check(code, name, ks):
    if len(ks) < 25: return None
    dates=[k[0] for k in ks]; closes=[float(k[2]) for k in ks]
    highs=[float(k[3]) for k in ks]
    vols=[float(k[5]) for k in ks]; amts=[float(k[6]) for k in ks]
    i=len(ks)-1
    if dates[i] != TODAY: return None            # 仅今日在交易
    if amts[i] < MIN_AMOUNT: return None
    ma=lambda p,j: sum(closes[j-p+1:j+1])/p
    ma2,ma5,ma13=ma(2,i),ma(5,i),ma(13,i)
    ma2p,ma5p=ma(2,i-1),ma(5,i-1)
    if not (ma2>ma5 and ma2p<=ma5p and closes[i]>=ma13): return None   # 金叉+现价≥MA13
    lim=klim(code)
    limups=sum(1 for j in range(i-9,i+1) if closes[j]/closes[j-1]-1>=lim-0.005)
    if limups < LEADER_MIN: return None          # 龙头过滤
    c=closes[i]; chg=(c/closes[i-1]-1)*100
    v20=sum(vols[i-20:i])/20
    limit_price = round(closes[i-1]*(1+lim), 2)   # 今日涨停价
    at_limit = chg >= lim*100-0.3                 # 已涨停(买不进)
    # 炸板过滤：盘中摸到涨停价但收盘没封住 → 剔除
    if highs[i] >= limit_price-0.005 and not at_limit:
        return None
    # 趋势过滤：排除持续下跌，保留上升/转好/下跌筑底
    if i>=70:
        ma20,ma20p,ma60,ma60p=ma(20,i),ma(20,i-5),ma(60,i),ma(60,i-10)
        if c>=ma60 and ma60>=ma60p: trend="上升趋势"
        elif c>=ma60:               trend="站上MA60转好"
        elif ma20>ma20p:            trend="下跌中筑底"
        else:                       trend="下跌趋势"
    else:
        trend="次新"
    if trend=="下跌趋势": return None              # 持续下跌且无筑底→排除
    return {"code":code,"name":name,"close":round(c,3),"chg":round(chg,2),
            "limups":limups,"bias13":round((c/ma13-1)*100,1),
            "volr":round(vols[i]/v20,2),"amt":round(amts[i]/1e8,1),
            "p60":round((c/closes[i-60]-1)*100,1) if i>=60 else None,
            "trend":trend,"at_limit":at_limit}

def main():
    uni=fetch_universe(); print(f"股票池 {len(uni)} 只，扫描中...")
    hits=[]; done=0
    with ThreadPoolExecutor(max_workers=24) as ex:
        futs={ex.submit(fetch_kline,sec):(c,n) for c,n,sec in uni}
        for f in as_completed(futs):
            c,n=futs[f]; done+=1
            try:
                ks=f.result()
                if ks:
                    r=check(c,n,ks)
                    if r: hits.append(r)
            except Exception: pass
    # 排序：龙头强度→量比→低乖离
    hits.sort(key=lambda x:(-x["limups"], -x["volr"], x["bias13"]))
    print(f"\n>>> 今日({TODAY})符合 [2上穿5金叉 + 现价≥MA13 + 近10日涨停≥{LEADER_MIN}次] 共 {len(hits)} 只\n")
    print("代码    名称        现价    今日%  近10涨停  乖离MA13  量比   额(亿)  近60日%  趋势        备注")
    for h in hits:
        note = "⚠已涨停买不进" if h["at_limit"] else ""
        print(f"{h['code']}  {h['name'][:6]:<7} {h['close']:>7.3f} {h['chg']:>+6.2f} "
              f"{h['limups']:>5}    {h['bias13']:>+6.1f}% {h['volr']:>5.2f} {h['amt']:>6.1f} "
              f"{str(h['p60']):>7}  {h['trend']:<10} {note}")

if __name__=="__main__": main()
