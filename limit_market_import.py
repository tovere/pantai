"""Import a separate unadjusted research dataset, never mix with adjusted cache."""
import json
import shutil
from pathlib import Path
from urllib.request import urlopen
from fuyao_client import get

ROOT = Path(__file__).resolve().parent / "data_cache" / "limit_raw"


def sync():
    import duckdb
    ROOT.mkdir(parents=True, exist_ok=True)
    destination = ROOT / "daily.parquet"
    url = get("/api/dump/market-dumps/daily-k/download-url")["presigned_url"]
    temp = destination.with_suffix(".tmp")
    with urlopen(url, timeout=120) as source, temp.open("wb") as target:
        shutil.copyfileobj(source, target)
    conn = duckdb.connect()
    summary = conn.execute("SELECT count(*), min(date_ms), max(date_ms) FROM read_parquet(?)", [str(temp)]).fetchone()
    if not summary[0]:
        raise ValueError("行情文件为空")
    temp.replace(destination)
    (ROOT / "manifest.json").write_text(json.dumps({"rows": summary[0], "minDateMs": summary[1], "maxDateMs": summary[2], "adjust": "none"}))
    print(json.dumps({"rows": summary[0], "maxDateMs": summary[2]}))


if __name__ == "__main__":
    sync()
