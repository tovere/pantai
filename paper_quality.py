"""Validate decision inputs against the provider's trading calendar."""
import json
from datetime import datetime
from pathlib import Path
from fuyao_client import get
from limit_pool import TZ, DIR

ROOT=Path(__file__).resolve().parent


def calendar(day):
    path=ROOT/'data_cache'/('paper-calendar-'+day+'.json')
    if path.exists():
        return json.loads(path.read_text())
    rows=get('/api/a-share/calendar/trading-days')['item']
    dates=sorted({datetime.strptime(str(r['date']),'%Y%m%d').strftime('%Y-%m-%d') for r in rows})
    path.write_text(json.dumps(dates))
    return dates


def quality(series, day, dates, window=30):
    expected=[d for d in dates if d<=day][-window:]
    actual={r[0] for r in series}
    missing=[d for d in expected if d not in actual]
    valid=len(expected)>=window and not missing and day in actual
    return {'valid':valid,'missingDates':missing,'requiredBars':window,
            'lastDate':series[-1][0] if series else None,
            'reason':None if valid else '缺少所需交易日日线，暂停技术信号买入'}


def market(day):
    def read(suffix):
        path=DIR/(day+suffix+'.json')
        if not path.exists():raise ValueError('缺少同日真实涨停/炸板池')
        data=json.loads(path.read_text())
        if data['capturedAt'][:10]!=day or datetime.fromisoformat(data['capturedAt']).hour<15:
            raise ValueError('涨停/炸板池尚非收盘快照')
        return data
    sealed,broken=read(''),read('-broken')
    # Keep one consistent main-board ordinary-stock universe.
    def eligible(i):
        return str(i.get('ticker','')).startswith(('000','001','002','003','600','601','603','605')) and 'ST' not in (i.get('name') or '').upper()
    up={i['ticker']:i for i in sealed['items'] if eligible(i)}
    br={i['ticker']:i for i in broken['items'] if eligible(i) and i['ticker'] not in up}
    return {'date':day,'source':'同花顺同日收盘主板普通股池','lu':len(up),'brk':len(br),
            'max_height':max((i.get('continue_day_cnt') or 1 for i in up.values()),default=0),
            'break_rate':len(br)/(len(up)+len(br)) if up or br else None,
            'phase':None,'phase_cn':'未确认','phaseReason':'缺少连续且同口径的历史情绪输入，暂不判定阶段',
            'capturedAt':sealed['capturedAt'],'brokenCapturedAt':broken['capturedAt']}


def ensure_bars(codes, day, dates):
    import paper_agent, cache_data
    for code in sorted(set(codes)):
        if quality(paper_agent.bars(code),day,dates)["valid"]:
            continue
        try:
            cache_data.daily_kline(("1." if code.startswith(("6","5")) else "0.")+code,force=True)
        except Exception:
            pass  # Quality gate below rejects incomplete data; never substitute samples.
