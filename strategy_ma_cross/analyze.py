#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量技术面分析：趋势/乖离/量能/均线信号。东方财富前复权日线。"""
import sys, json, urllib.request

UA = "Mozilla/5.0"
def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "ignore")

def secid(code):
    if code.startswith("6") or code.startswith("51") or code.startswith("11"):
        return f"1.{code}"
    return f"0.{code}"

def klimit(code):
    return 0.20 if code.startswith("30") or code.startswith("688") else 0.10

def analyze(code):
    url = ("https://push2his.eastmoney.com/api/qt/stock/kline/get"
           f"?secid={secid(code)}&fields1=f1,f2,f3,f4,f5,f6"
           "&fields2=f51,f52,f53,f54,f55,f56,f57"
           "&klt=101&fqt=1&beg=20250101&end=20500101")
    d = json.loads(http_get(url)).get("data")
    if not d or not d.get("klines"):
        print(f"\n##### {code}  无数据"); return
    ks = [l.split(",") for l in d["klines"]]
    dates = [k[0] for k in ks]; closes = [float(k[2]) for k in ks]
    vols = [float(k[5]) for k in ks]; amts = [float(k[6]) for k in ks]
    n = len(ks); i = n - 1
    ma = lambda p, j: sum(closes[j-p+1:j+1])/p if j+1 >= p else None
    c = closes[i]
    ma2, ma5, ma13, ma20 = ma(2,i), ma(5,i), ma(13,i), ma(20,i)
    ma2p, ma5p = ma(2,i-1), ma(5,i-1)
    chg = (c/closes[i-1]-1)*100
    hi, lo = max(closes), min(closes)
    v20 = sum(vols[i-20:i])/20 if i >= 20 else sum(vols[:i])/max(1,i)
    lim = klimit(code)
    limups = sum(1 for j in range(max(1,i-9), i+1) if closes[j]/closes[j-1]-1 >= lim-0.005)

    print(f"\n##### {code}  {d.get('name')}")
    print(f" 最新 {c:.4f}  当日{chg:+.2f}%  ({dates[i]})")
    rng = lambda x: round((c/x-1)*100,1)
    perf = {p: round((c/closes[i-p]-1)*100,1) for p in (5,10,20,60) if i >= p}
    print(f" 涨幅 近5日{perf.get(5,'-')}% 近10日{perf.get(10,'-')}% 近20日{perf.get(20,'-')}% 近60日{perf.get(60,'-')}%")
    print(f" 区间高{hi:.4f} 低{lo:.4f}  距高{rng(hi)}% 距低{rng(lo)}%")
    print(f" 均线 MA5={ma5:.4f} MA13={ma13:.4f} MA20={ma20:.4f}")
    print(f" 乖离 vsMA5 {rng(ma5):+}%  vsMA13 {rng(ma13):+}%  vsMA20 {rng(ma20):+}%")
    print(f" 量能 今日{vols[i]/1e4:.0f}万手 量比20日 {vols[i]/v20:.2f}x  额{amts[i]/1e8:.2f}亿")
    print(f" 近10日涨停次数(龙头指标) {limups}")
    cross = ma2 > ma5 and ma2p <= ma5p
    print(f" 策略信号: 2上穿5金叉={cross}  现价≥MA13={c>=ma13}  >>>买入信号={cross and c>=ma13}")
    # 趋势定性
    above = c > ma5 > ma13 > ma20
    bias13 = rng(ma13)
    if above and bias13 > 15: tag = "强势但严重超买(乖离大)"
    elif above and bias13 > 5: tag = "多头排列 上升趋势"
    elif above: tag = "温和多头"
    elif c < ma20 and ma5 < ma20: tag = "空头/下降趋势"
    else: tag = "震荡/方向不明"
    print(f" 定性: {tag}")

if __name__ == "__main__":
    for code in sys.argv[1:]:
        analyze(code)
