#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略三：强势股回踩MA20低吸。
  趋势: 收盘>MA20>MA60 且 MA60上行
  回踩: 近10日曾≥MA20×1.05(有过上涨) + 今日最低探到MA20(low≤MA20×1.02)但收盘守住(close≥MA20) + 缩量(量<近5日均量)
  买入: 信号日收盘; 卖出: 收盘破MA20 或 -5%硬止损
输出: 单笔统计 + 分月 + 5仓位资金曲线。curl后端+低并发避限流。
"""
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
            out.append((c, f"1.{c}" if c.startswith("6") else f"0.{c}"))
        if pn*100>=d.get("total",0): break
        pn+=1
    return out
def kl(s):
    d=json.loads(get(f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={s}&fields1=f1&fields2=f51,f52,f53,f54,f55,f56&klt=101&fqt=1&beg={DATA_BEG}&end=20500101")).get("data")
    return [l.split(",") for l in d["klines"]] if d and d.get("klines") else None
def run(code, rows):
    if len(rows)<70: return []
    dates=[r[0] for r in rows]; O=[float(r[1]) for r in rows]; C=[float(r[2]) for r in rows]
    H=[float(r[3]) for r in rows]; L=[float(r[4]) for r in rows]; V=[float(r[5]) for r in rows]
    lim=0.20 if code.startswith("30") else 0.10
    n=len(rows)
    ma20=[sum(C[k-19:k+1])/20 if k>=19 else None for k in range(n)]
    ma60=[sum(C[k-59:k+1])/60 if k>=59 else None for k in range(n)]
    out=[]; i=63
    while i<n-1:
        m20,m60,m60p=ma20[i],ma60[i],ma60[i-10]
        uptrend = C[i]>m20>m60 and m60>m60p
        pulled = max(C[i-9:i+1]) >= m20*1.05
        touch = L[i] <= m20*1.02 and C[i] >= m20
        shrink = V[i] < sum(V[i-5:i])/5
        chg=C[i]/C[i-1]-1
        if uptrend and pulled and touch and shrink and chg>=-0.05 and chg<lim-0.005 and SIGNAL_START<=dates[i]<=SIGNAL_END:
            buy=C[i]; stop=buy*0.95; j=i+1; sell=None; closed=True
            while j<n:
                if O[j]<=stop: sell=O[j]; break
                if L[j]<=stop: sell=stop; break
                if C[j]<ma20[j]: sell=C[j]; break       # 收盘破MA20
                j+=1
            if sell is None: sell=C[n-1]; j=n-1; closed=False
            out.append({"entry":dates[i],"exit":dates[j],"ret":sell/buy-1-COST,"held":j-i,"closed":closed})
            i=j+1
        else: i+=1
    return out
def simulate(trades):
    by={}
    for t in trades: by.setdefault(t["entry"],[]).append(t)
    # 不按收益排(那是未来函数)，自然顺序=中性抽样
    days=sorted(set([t["entry"] for t in trades]+[t["exit"] for t in trades]))
    cash=1.0; pos=[]; curve=[]
    for dt in days:
        keep=[]
        for p in pos:
            if p["exit"]==dt: cash+=p["cap"]*(1+p["ret"])
            else: keep.append(p)
        pos=keep; eq=cash+sum(p["cap"] for p in pos)
        for t in by.get(dt,[]):
            if len(pos)>=N_SLOTS or cash<=1e-9: break
            commit=min(eq/N_SLOTS,cash); cash-=commit
            pos.append({"exit":t["exit"],"cap":commit,"ret":t["ret"]})
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
                if r: A.extend(run(futs[f],r))
            except Exception: pass
            if done%1000==0: print(f"  {done}/{len(U)} 交易{len(A)}")
    rets=[t["ret"] for t in A]; w=[r for r in rets if r>0]; ls=[r for r in rets if r<=0]
    aw=statistics.mean(w) if w else 0; al=statistics.mean(ls) if ls else 0
    print(f"\n>> 策略三回测 {SIGNAL_START}~{SIGNAL_END}  交易{len(A)}笔\n")
    print(f"  胜率 {len(w)/len(rets)*100:.1f}%   单笔均收益 {statistics.mean(rets)*100:+.2f}%   中位 {statistics.median(rets)*100:+.2f}%")
    print(f"  平均盈利 {aw*100:+.2f}% / 平均亏损 {al*100:+.2f}%   盈亏比 {aw/abs(al):.2f}")
    print(f"  平均持有 {statistics.mean(t['held'] for t in A):.1f}天   最好/最差 {max(rets)*100:+.0f}%/{min(rets)*100:+.0f}%")
    by={}
    for t in A: by.setdefault(t["entry"][:7],[]).append(t["ret"])
    print("\n  分月:")
    for m in sorted(by):
        rs=by[m]; print(f"   {m}: {len(rs):>4}笔 胜率{sum(1 for r in rs if r>0)/len(rs)*100:4.1f}% 均{statistics.mean(rs)*100:+5.2f}%")
    tot,mdd=simulate(A)
    print(f"\n  资金曲线(5仓位等权): 总收益 {tot*100:+.1f}%   最大回撤 {mdd*100:.1f}%")
if __name__=="__main__": main()
