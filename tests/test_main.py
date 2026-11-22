import json

from tanszylek import __main__ as app_main
from tanszylek import config, etl


def _prepare(tmp_path, monkeypatch, version):
    processed = tmp_path / "processed"
    processed.mkdir()
    (processed / "leki.parquet").write_bytes(b"x")
    (processed / "apteki.parquet").write_bytes(b"x")
    meta = processed / "meta.json"
    meta.write_text(json.dumps({"demo": False, "etl_version": version}), encoding="utf-8")
    raw = tmp_path / "raw.csv"
    raw.write_text("x")
    old = 1_000_000_000  # surowe pliki starsze niż Parquet
    import os

    os.utime(raw, (old, old))
    monkeypatch.setattr(config, "PROCESSED_DIR", processed)
    return meta, (raw, raw)


def test_stale_when_etl_version_changed(tmp_path, monkeypatch):
    meta, raw = _prepare(tmp_path, monkeypatch, version=etl.ETL_VERSION - 1)
    assert app_main._stale(meta, raw) is True


def test_not_stale_when_version_matches(tmp_path, monkeypatch):
    meta, raw = _prepare(tmp_path, monkeypatch, version=etl.ETL_VERSION)
    assert app_main._stale(meta, raw) is False
