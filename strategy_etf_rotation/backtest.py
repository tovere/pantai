#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略四：ETF热点动量轮动。
  池: 每个板块取成交额最大的代表ETF(行业/主题+宽基)
  打分: 近20日涨幅(=本月强度); 风控: 只持站上MA20的; 全不达标则空仓
  每5个交易日轮动一次, 持分数最高的 N 只。
输出: ETF池 + 不同参数回测 + 当前该持有的热点ETF。curl后端。
"""
import json, subprocess, statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
DATA_BEG="20250101"; UA="Mozilla/5.0"
def get(u,tries=4):
    for _ in range(tries):
        p=subprocess.run(["curl","-s","-m","20","-A",UA,u],capture_output=True,text=True)
        if p.returncode==0 and p.stdout: return p.stdout
    return ""
# 板块 -> 关键词(取成交额最大的匹配ETF做代表)
SECTORS=[
 ("沪深300",["沪深300"]),("中证500",["中证500"]),("中证1000",["中证1000"]),
 ("科创50",["科创50"]),("创业板",["创业板ETF","创业板50"]),("上证50",["上证50"]),
 ("半导体",["半导体","芯片"]),("通信",["通信"]),("证券",["证券","券商"]),
 ("银行",["银行"]),("创新药",["创新药"]),("医疗",["医疗"]),("医药",["医药"]),
 ("有色",["有色"]),("煤炭",["煤炭"]),("军工",["军工","国防"]),
 ("光伏",["光伏"]),("新能源车",["新能源车","新能车","电池"]),("人工智能",["人工智能","AI"]),
 ("机器人",["机器人"]),("消费电子",["消费电子"]),("游戏",["游戏","动漫"]),
 ("传媒",["传媒"]),("白酒",["白酒"]),("食品饮料",["食品饮料"]),("消费",["主要消费","消费ETF"]),
 ("地产",["房地产","地产"]),("化工",["化工"]),("钢铁",["钢铁"]),("农业",["农业","养殖","畜牧"]),
 ("电力",["电力"]),("电网",["电网"]),("黄金",["黄金"]),("红利",["红利"]),
 ("计算机",["计算机","软件"]),("家电",["家电"]),("油气",["油气","石油"]),
]
def etf_pool():
    d=json.loads(get("https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=300&po=1&np=1&fltt=2&invt=2&fid=f6&fs=b:MK0021&fields=f12,f14,f6")).get("data")
    rows=[(x["f12"],x["f14"],x["f6"]) for x in d["diff"]]   # 已按成交额降序
    pool={}; used=set()
    for label,kws in SECTORS:
        for c,nm,amt in rows:
            if c in used: continue
            if any(k in nm for k in kws):
                pool[c]=(label,nm); used.add(c); break
    return pool
def kl(c):
    sec=f"1.{c}" if c[0] in "5611" else f"0.{c}"
    sec=f"1.{c}" if c.startswith(("5","11","58")) else f"0.{c}"
    d=json.loads(get(f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={sec}&fields1=f1&fields2=f51,f53&klt=101&fqt=1&beg={DATA_BEG}&end=20500101")).get("data")
    if not d or not d.get("klines"): return None
    out=[(l.split(",")[0],float(l.split(",")[1])) for l in d["klines"]]
    return out
def backtest(series, N, WIN, STEP):
    # series: {code:[(date,close)]}; 主日历=并集
    alld=sorted(set(d for s in series.values() for d,_ in s))
    idx={c:{d:i for i,(d,_) in enumerate(s)} for c,s in series.items()}
    cl ={c:[x[1] for x in s] for c,s in series.items()}
    eq=1.0; curve=[]; rebal=range(60,len(alld)-1,STEP)
    for t in rebal:
        d=alld[t]; nxt=alld[min(t+STEP,len(alld)-1)]
        scores=[]
        for c,s in series.items():
            i=idx[c].get(d)
            if i is None or i<WIN: continue
            mom=cl[c][i]/cl[c][i-WIN]-1
            ma20=sum(cl[c][i-19:i+1])/20
            if cl[c][i]>=ma20: scores.append((mom,c))   # 站上MA20才合格
        scores.sort(reverse=True); picks=[c for _,c in scores[:N]]
        if not picks: curve.append(eq); continue        # 全不达标→空仓
        rs=[]
        for c in picks:
            i,j=idx[c].get(d),idx[c].get(nxt)
            if i is not None and j is not None: rs.append(cl[c][j]/cl[c][i]-1)
        if rs: eq*=(1+sum(rs)/len(rs))
        curve.append(eq)
    peak=curve[0]; mdd=0
    for v in curve: peak=max(peak,v); mdd=max(mdd,(peak-v)/peak)
    return eq-1, mdd
def main():
    pool=etf_pool(); print(f"ETF池(每板块取最活跃) {len(pool)} 只:")
    for c,(lab,nm) in pool.items(): print(f"  {c} {lab:<8} {nm}")
    series={}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for c,r in zip(pool, ex.map(kl, pool)):
            if r and len(r)>80: series[c]=r
    print(f"\n拉到K线 {len(series)} 只。区间 {series[list(series)[0]][0][0]} ~ {series[list(series)[0]][-1][0]}")
    print("\n参数网格 (总收益 / 最大回撤):")
    for WIN in (10,20):
        for N in (1,2,3):
            tot,mdd=backtest(series,N,WIN,5)
            print(f"  排名窗口{WIN}日 持{N}只 周调: {tot*100:>+7.1f}% / 回撤{mdd*100:4.1f}%")
    # 当前最强(用20日窗口)
    alld=sorted(set(d for s in series.values() for d,_ in s)); d=alld[-1]
    idx={c:{x[0]:i for i,x in enumerate(s)} for c,s in series.items()}
    cl ={c:[x[1] for x in s] for c,s in series.items()}
    rk=[]
    for c,s in series.items():
        i=idx[c].get(d)
        if i is None or i<20: continue
        mom=cl[c][i]/cl[c][i-20]-1; ma20=sum(cl[c][i-19:i+1])/20
        rk.append((mom,c,cl[c][i]>=ma20))
    rk.sort(reverse=True)
    print(f"\n>>> 当前({d}) 板块强度排名 (近20日涨幅, 站上MA20才可买):")
    for mom,c,ok in rk[:10]:
        print(f"  {pool[c][0]:<8}{pool[c][1]:<22} {c}  近20日{mom*100:+5.1f}%  {'✓站上MA20' if ok else '✗破位'}")
if __name__=="__main__": main()
