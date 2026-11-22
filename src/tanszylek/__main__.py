"""Uruchomienie: python -m tanszylek

Buduje dane (jeśli ich brak lub surowe pliki są nowsze) i startuje serwer.
Bez plików w data/raw działa w trybie DEMO na próbce z tests/sample.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import uvicorn

from . import api, config, etl


def _stale(meta_path: Path, raw: tuple[Path, Path]) -> bool:
    """Czy dane przetworzone trzeba zbudować od nowa?"""
    parquet = [config.PROCESSED_DIR / "leki.parquet", config.PROCESSED_DIR / "apteki.parquet"]
    if not meta_path.exists() or not all(p.exists() for p in parquet):
        return True
    built = min(p.stat().st_mtime for p in parquet)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if meta.get("etl_version") != etl.ETL_VERSION:  # stary układ Parquet (np. w wolumenie Dockera)
        return True
    return meta.get("demo", False) or any(p.stat().st_mtime > built for p in raw)


def _meta_current(meta_path: Path) -> bool:
    """Czy istnieją dane przetworzone w aktualnym układzie (bez surowych plików brak odbudowy)."""
    if not meta_path.exists() or not (config.PROCESSED_DIR / "leki.parquet").exists():
        return False
    return json.loads(meta_path.read_text(encoding="utf-8")).get("etl_version") == etl.ETL_VERSION


def ensure_data() -> None:
    leki = etl.find_raw(config.RAW_DIR, "leki")
    apteki = etl.find_raw(config.RAW_DIR, "apteki")
    meta_path = config.PROCESSED_DIR / "meta.json"
    has_raw = bool(leki and apteki)
    if has_raw and not _stale(meta_path, (leki, apteki)):
        return
    if not has_raw:
        if _meta_current(meta_path):
            return
        print("Brak danych w data/raw -> tryb DEMO na próbce z tests/sample")
        leki = config.SAMPLE_DIR / "leki_sample.csv"
        apteki = config.SAMPLE_DIR / "apteki_sample.csv"
    stats = etl.build(leki, apteki, config.PROCESSED_DIR)
    meta = {
        "demo": not has_raw,
        "etl_version": etl.ETL_VERSION,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rows": stats,
        "sources": {"leki": leki.name, "apteki": apteki.name},
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("ETL:", stats)


if __name__ == "__main__":
    ensure_data()
    api.reset()
    uvicorn.run(api.app, host="0.0.0.0", port=config.PORT)
