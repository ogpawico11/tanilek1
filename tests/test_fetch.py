import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "fetch_data", Path(__file__).parents[1] / "scripts" / "fetch_data.py"
)
fetch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fetch)


def _res(rid, fmt, url, date=None):
    attrs = {"format": fmt, "download_url": url, "data_date": date}
    return {"id": rid, "attributes": attrs}


def test_pick_resource_prefers_newest_csv_or_xlsx():
    items = [
        _res("1", "pdf", "https://x/doc.pdf", "2026-12-01"),
        _res("2", "csv", "https://x/old.csv", "2025-01-01"),
        _res("3", "xlsx", "https://x/new.xlsx", "2026-06-01"),
        _res("4", "csv", None, "2027-01-01"),  # bez linku do pobrania
    ]
    assert fetch.pick_resource(items)["id"] == "3"


def test_pick_resource_none_when_no_tabular_file():
    assert fetch.pick_resource([_res("1", "pdf", "https://x/doc.pdf")]) is None


def test_extension_from_header_or_url():
    assert fetch._extension("https://x/get?id=1", 'attachment; filename="lista.XLSX"') == "xlsx"
    assert fetch._extension("https://x/dane.csv", None) == "csv"
    assert fetch._extension("https://x/download/123", None) == "csv"


def test_institution_handles_dict_and_string():
    assert fetch._institution({"institution": {"title": "GIF"}}) == "GIF"
    assert fetch._institution({"institution": "MZ"}) == "MZ"
    assert fetch._institution({}) == ""


def test_search_prints_ids(monkeypatch, capsys):
    payload = {"data": [{"id": 42, "attributes": {"title": "Rejestr aptek", "institution": None}}]}
    monkeypatch.setattr(fetch, "_get", lambda url: payload)
    fetch.search("apteki")
    assert "42" in capsys.readouterr().out


def test_auto_without_urls_does_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(fetch, "RAW", tmp_path)
    monkeypatch.delenv("LEKI_URL", raising=False)
    monkeypatch.delenv("APTEKI_URL", raising=False)
    fetch.auto()
    assert "Pomijam" in capsys.readouterr().out
    assert list(tmp_path.iterdir()) == []
