import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tanszylek import api, config, etl

SAMPLE = Path(__file__).parent / "sample"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    etl.build(SAMPLE / "leki_sample.csv", SAMPLE / "apteki_sample.csv", tmp_path)
    (tmp_path / "meta.json").write_text(json.dumps({"demo": True}), encoding="utf-8")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path)
    api.reset()
    yield TestClient(api.app)
    api.reset()


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_meta(client):
    m = client.get("/api/meta").json()
    assert m["demo"] is True and m["leki"] == 8 and m["apteki"] == 5


def test_index_served_with_cache_header(client):
    r = client.get("/")
    assert r.status_code == 200 and "tanszylek" in r.text
    assert "max-age" in r.headers["cache-control"]


def test_search_by_polish_substance_name_without_diacritics(client):
    # w grupie limitowej substancja jest po polsku, w kolumnie substancji po łacinie
    assert len(client.get("/api/leki", params={"q": "atorwastatyna"}).json()) == 3
    assert len(client.get("/api/leki", params={"q": "atorvastatinum"}).json()) == 3


def test_search_by_name_prefix_first(client):
    names = [x["nazwa"] for x in client.get("/api/leki", params={"q": "tul"}).json()]
    assert names == ["Tulip"]


def test_wildcards_in_query_are_not_special(client):
    assert client.get("/api/leki", params={"q": "%%"}).json() == client.get(
        "/api/leki", params={"q": ""}
    ).json()


def test_zamienniki_same_dose_sorted_by_surcharge_then_price(client):
    first = client.get("/api/leki", params={"q": "metformax"}).json()[0]
    z = client.get(f"/api/leki/{first['id']}/zamienniki").json()
    assert [x["nazwa"] for x in z] == ["Siofor 500", "Glucophage"]
    assert [x["doplata"] for x in z] == [0.0, 3.4]


def test_zamienniki_do_not_mix_doses(client):
    atoris20 = next(
        x for x in client.get("/api/leki", params={"q": "atoris"}).json() if x["dawka"] == "20 mg"
    )
    z = client.get(f"/api/leki/{atoris20['id']}/zamienniki").json()
    assert [(x["nazwa"], x["dawka"]) for x in z] == [("Tulip", "20 mg")]


def test_zamienniki_empty_when_unique(client):
    amlozek = client.get("/api/leki", params={"q": "amlozek"}).json()[0]
    assert client.get(f"/api/leki/{amlozek['id']}/zamienniki").json() == []


def test_apteki_exclude_inactive_and_hospital(client):
    r = client.get("/api/apteki", params={"miasto": "warszawa"}).json()
    assert len(r) == 3
    assert all(x["nazwa"] not in {"Apteka Zamknięta", "Apteka Szpitalna"} for x in r)


def test_apteki_city_with_lost_polish_letters(client):
    for typed in ("lodz", "Łódź"):
        r = client.get("/api/apteki", params={"miasto": typed}).json()
        assert [x["miejscowosc"] for x in r] == ["?ód?"], typed


def test_apteki_filter_by_street(client):
    r = client.get("/api/apteki", params={"miasto": "warszawa", "q": "pulawska"}).json()
    assert [x["nazwa"] for x in r] == ["Apteka Zdrowie"]


def test_404(client):
    assert client.get("/api/leki/9999/zamienniki").status_code == 404


@pytest.fixture()
def rpl_client(tmp_path, monkeypatch):
    etl.build(SAMPLE / "leki_rpl_sample.csv", SAMPLE / "apteki_sample.csv", tmp_path)
    (tmp_path / "meta.json").write_text(json.dumps({"demo": True}), encoding="utf-8")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path)
    api.reset()
    yield TestClient(api.app)
    api.reset()


def test_rpl_search_returns_pack_list_and_puts_retired_last(rpl_client):
    r = rpl_client.get("/api/leki", params={"q": "drotaverini"}).json()
    assert [x["nazwa"] for x in r][-1] == "Metafen rozkurczowy"
    nospa = next(x for x in r if x["nazwa"] == "NO-SPA")
    assert nospa["opakowania"] == [{"ean": "05909990437719", "kat": "OTC", "opis": "20 tabl."}]
    assert nospa["cena"] is None and nospa["aktywne"] == 1 and nospa["wycofane"] == 1


def test_rpl_zamienniki_skip_retired_products(rpl_client):
    nospa = next(
        x for x in rpl_client.get("/api/leki", params={"q": "no-spa"}).json()
        if x["nazwa"] == "NO-SPA"
    )
    z = rpl_client.get(f"/api/leki/{nospa['id']}/zamienniki").json()
    assert [x["nazwa"] for x in z] == ["Drotapil"]  # bez skasowanego Metafenu i innej postaci


def test_index_is_revalidated(client):
    cc = client.get("/").headers["cache-control"]
    assert "max-age=0" in cc and "must-revalidate" in cc
