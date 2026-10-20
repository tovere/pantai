"""Previous-limit-up pullbacks: measured evidence, not inferred theory labels."""
import json
from pathlib import Path
from datetime import datetime
import paper_agent as paper
from paper_quality import calendar, quality, ensure_bars
from limit_pool import DIR, fetch
from limit_sectors import ROOT as SECTORS


def evidence(rows, day, dates):
    q=quality(rows,day,dates,130)
    if not q['valid']:
        return None
    prev,today=rows[-2:]
    if prev[0] != [d for d in dates if d<day][-1]:
        return None
    change=today[2]/prev[2]-1
    ratio=today[5]/prev[5] if prev[5]>0 else None
    if ratio is None or not (-.03<=change<0 and ratio<.8 and today[2]<today[1]):
        return None
    intact=today[4]>prev[4]
    close_position=(today[2]-today[4])/(today[3]-today[4]) if today[3]>today[4] else 0
    from strategy_chan_final import chan
    structure=chan.build([r+[0.0] if len(r)==6 else r for r in rows])
    pivots=structure['ps'] if structure else []
    pivot=pivots[-1] if pivots else None
    chan_evidence={'source':'strategy_chan_final.chan.build','level':'日线','bars':len(rows),
                   'pivotCount':len(pivots),'latestPivot':{k:pivot[k] for k in ('zg','zd','gg','dd')} if pivot else None,
                   'abovePivot':bool(pivot and today[4]>pivot['zg']),
                   'amountUsed':False,'buyPointConfirmed':False,'note':'提供严格笔中枢结构；不据两根K线认定三买，未核验30分钟确认'}
    import screen_chan_wyckoff_3buy as wy
    O,C,H,L,V=([r[k] for r in rows] for k in (1,2,3,4,5))
    box=wy.find_box_before_pullback(H,L,C,V,len(rows)-3)
    box_test=bool(box and prev[2]>box['hi'] and today[4]>=box['hi'])
    trigger=round(today[3]+.01,2)
    stop=round(max(prev[4],today[4]),2)
    ceiling=round(today[2]*1.03,2)
    return {'quality':q,'priceVolume':{'previousDate':prev[0],'pullbackPct':round(change*100,2),
              'volumeRatio':round(ratio,3),'bearishCandle':True,'closePosition':round(close_position,3),
              'previousLimitLow':prev[4],'pullbackLow':today[4],'supportIntact':intact},
            'chan':chan_evidence,
            'wyckoff':{'source':'screen_chan_wyckoff_3buy.find_box_before_pullback',
              'range':box,'breakoutRetest':box_test,'supplyContraction':ratio<.8,
              'phaseConfirmed':False,'note':'缩量测试候选；量价不能证明吸筹、主力意图或LPS已成立'},
            'invalidation':{'belowPrice':stop,'supportAlreadyBroken':not intact},
            'entry':{'triggerPrice':trigger,'maxPrice':ceiling,'stop':stop,
              'eligible':intact and close_position>=.35 and stop<trigger<=ceiling},
            'asOf':day,'close':today[2]}


def prepare(day, with_scan=False):
    dates=calendar(day)
    previous=[d for d in dates if d<day][-1]
    path=DIR/(previous+'.json')
    pool=json.loads(path.read_text()) if path.exists() else fetch(previous)
    source=[i for i in pool['items'] if str(i.get('ticker','')).startswith(('000','001','002','003','600','601','603','605')) and 'ST' not in (i.get('name') or '').upper()]
    codes={str(i['ticker']) for i in source}
    ensure_bars(codes,day,dates)
    memberships=[]
    for path in sorted((SECTORS/day).glob('*.json')):
        sector=json.loads(path.read_text())
        memberships.append((sector['sector']['name'],{str(i['ticker']) for i in sector['members']}))
    current_path=DIR/(day+'.json')
    current=json.loads(current_path.read_text())['items'] if current_path.exists() else []
    output=[]
    incomplete=0
    for stock in source:
        code=str(stock['ticker']);rows=[b for b in paper.bars(code) if b[0]<=day]
        if not quality(rows,day,dates,130)["valid"]:
            incomplete+=1
        ev=evidence(rows,day,dates)
        if not ev:continue
        matches=[]
        for name,members in memberships:
            if code not in members:continue
            leaders=sorted([s for s in current if str(s['ticker']) in members and str(s['ticker'])!=code],key=lambda s:-(s.get('continue_day_cnt') or 1))
            if leaders:matches.append({'name':name,'leaders':[str(s['ticker']) for s in leaders[:3]]})
        sector=matches[0] if matches else None
        ev['sector']={'source':'同日正式行业成分及涨停池','match':sector,'reflowConfirmed':False,
                      'note':'收盘关联不等于次日回流；买入须等待领涨股及样本同伴实时转强'}
        ev['entry']['eligible']=ev['entry']['eligible'] and bool(sector and len(sector['leaders'])>=2)
        output.append({'code':code,'name':stock['name'],'close':ev['close'],'grade':'未评级',
                       'flags':[],'height':0,'probability':None,'contextProbability':None,
                       'source':'涨停后分歧','quality':ev['quality'],'evidence':ev})
    scan={'signalDate':day,'previousLimitDate':previous,'sourceCount':len(source),
          'incompleteHistory':incomplete,'matched':len(output),
          'definition':'前交易日真实主板涨停；今日阴线、收跌不超过3%、量比<0.8；130个交易日日线校验',
          'note':'初始研究条件，尚未完成该组合规则的独立回测'}
    return {'items':output,'scan':scan} if with_scan else output


def condition(item, action, signal_day):
    ev=item['evidence'];entry=ev['entry'];sector=ev['sector']['match']
    if not entry['eligible'] or not sector:
        raise ValueError('分歧候选缺少有效支撑、入场区间或行业联动样本，只能观察')
    if not (entry['triggerPrice']<=action['max_price']<=entry['maxPrice'] and action['stop']>=entry['stop']):
        raise ValueError('分歧买单限价或止损与结构证据不符')
    return {'entryMin':entry['triggerPrice'],'invalidateBelow':entry['stop'],
            'peers':sector['leaders'],'minPositivePeers':2,'signalDate':signal_day,
            'source':'涨停后分歧','sector':sector['name']}


def triggered(condition, quote, batch):
    peers=[batch.get(c) for c in condition['peers']]
    return (quote['last']>=condition['entryMin'] and quote['last']>condition['invalidateBelow']
            and sum(bool(q and q['last']>q['prev']) for q in peers)>=condition['minPositivePeers'])


def valid_session(condition, day):
    dates=calendar(day)
    previous=[d for d in dates if d<day]
    return day in dates and bool(previous) and previous[-1]==condition['signalDate']
