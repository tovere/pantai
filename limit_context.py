"""Predefined conditional-rate research model; no manual probability bonuses."""
def key(row, market):
    return (min(row["height"],4), market["phase"],
            row["height"] >= market["max_height"],
            market["break_rate"] >= .3,
            market["high_n"] >= 6)


def grouped(history, markets):
    result = {}
    for row in history:
        bucket = result.setdefault(key(row, markets[row["date"]]), [])
        bucket.append(row)
    return result


def estimate(row, market, history, markets, prior, groups=None):
    peers = (groups if groups is not None else grouped(history,markets)).get(key(row,market), [])
    n = len(peers)
    if n < 50 or prior is None:
        return None,n
    return round((sum(r["continued"] for r in peers)+50*prior)/(n+50)*100,1),n


def compare(predictions):
    rows = [r for r in predictions if r["kind"]=="sealed" and r["continued"] is not None and r.get("contextProbability") is not None and r["probability"] is not None]
    def score(field):
        return round(sum((r[field]/100-r["continued"])**2 for r in rows)/len(rows),4) if rows else None
    return {"samples":len(rows),"baselineBrier":score("probability"),"contextBrier":score("contextProbability"),
            "features":"板数、情绪阶段、是否空间板、炸板率≥30%、高板宽度≥6；同条件不足50例不输出",
            "note":"同一有效样本比较；研究模型，分箱尚未在独立保留期确认"}
