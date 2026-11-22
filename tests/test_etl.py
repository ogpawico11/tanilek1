import json
import re
from pathlib import Path

import duckdb

from tanszylek import etl

SAMPLE = Path(__file__).parent / "sample"
REAL_LEKI_HEADER = [
    "GTIN", "Nazwa", "Postać", "Dawka", "Nazwa międzynarodowa", "Opakowanie",
    "Identyfikator grupy limitowej", "Nazwa grupy limitowej", "Cena zbytu", "Limit",
    "Cena detaliczna", "Czy lek jest podstawą limitu",
]
REAL_APTEKI_HEADER = [
    "identyfikator_apteki", "nazwa_apteki", "stan_apteki", "rodzaj_apteki", "nazwa_ulicy",
    "numer_budynku", "miejscowosc", "kod_pocztowy", "adres_www", "wlasciciel_miejscowosc",
    "wlasciciel_nazwa_ulicy", "kierownik_imie", "telefon",
]


def test_norm():
    assert etl.norm("Łódź") == "lodz"
    assert etl.norm(None) == ""


def test_map_real_leki_header():
    m = etl.map_columns(REAL_LEKI_HEADER, etl.LEKI_RULES)
    assert m["substancja"] == "Nazwa międzynarodowa"
    assert m["nazwa"] == "Nazwa"
    assert m["ean"] == "GTIN"
    assert m["grupa_limitowa"] == "Identyfikator grupy limitowej"
    assert m["limit_ceny"] == "Limit"
    assert m["cena"] == "Cena detaliczna"
    assert "doplata" not in m


def test_map_legacy_leki_header():
    cols = ["Substancja czynna", "Nazwa, postać i dawka", "Cena detaliczna", "Kod EAN"]
    m = etl.map_columns(cols, etl.LEKI_RULES)
    assert m["substancja"] == "Substancja czynna"
    assert m["nazwa"] == "Nazwa, postać i dawka"
    assert m["ean"] == "Kod EAN"
    assert "postac" not in m


def test_map_real_apteki_header_ignores_owner_and_www():
    m = etl.map_columns(REAL_APTEKI_HEADER, etl.APTEKI_RULES)
    assert m["nazwa"] == "nazwa_apteki"
    assert m["miejscowosc"] == "miejscowosc"
    assert m["nazwa_ulicy"] == "nazwa_ulicy"  # nie adres_www ani adres właściciela
    assert not any("kierownik" in c or "wlasciciel" in c for c in m.values())


def test_lossy_pattern_matches_question_marks():
    pattern = re.compile(etl.lossy_pattern("Łódź"))
    assert pattern.search("?od?")
    assert pattern.search("lodz")
    assert not pattern.search("krakow")
    assert re.fullmatch(etl.lossy_pattern("a.b"), "a.b")  # znaki specjalne są escapowane


def test_prepare_leki_computes_surcharge_and_keys():
    rows, stats = etl.prepare_leki(SAMPLE / "leki_sample.csv")
    assert stats == {"read": 8, "kept": 8, "skipped": 0}
    by_name = {r[2]: r for r in rows}
    cols = etl.LEKI_COLUMNS
    glucophage = dict(zip(cols, by_name["Glucophage"]))
    assert glucophage["cena"] == "15.9"
    assert glucophage["doplata"] == "3.4"  # cena powyżej limitu 12,50
    assert dict(zip(cols, by_name["Siofor 500"]))["doplata"] == "0.0"
    keys = {r[2]: r[-1] for r in rows if r[2] != "Atoris"}
    assert keys["Metformax"] == keys["Glucophage"] == keys["Siofor 500"]
    assert keys["Tulip"] != keys["Metformax"]


def test_prepare_apteki_filters_and_formats():
    rows, stats = etl.prepare_apteki(SAMPLE / "apteki_sample.csv")
    assert stats == {"read": 7, "kept": 5, "dropped": 2}  # bez nieaktywnej i szpitalnej
    recs = [dict(zip(etl.APTEKI_COLUMNS, r)) for r in rows]
    first = recs[0]
    assert first["ulica"] == "ul. Marszałkowska 10/5"
    assert first["godziny"] == "pn–pt: 08:00 - 20:00 · sob: 09:00 - 15:00"
    assert recs[3]["nazwa"] == "Punkt apteczny" and recs[3]["ulica"] == "nr 5"
    assert recs[3]["miejscowosc"] == "Krynki"  # WERSALIKI -> Wielka litera
    assert recs[4]["nazwa"] == 'APTEKA "ZŁOTA"'
    assert "kierownik" not in " ".join(etl.APTEKI_COLUMNS)


def test_build(tmp_path):
    stats = etl.build(SAMPLE / "leki_sample.csv", SAMPLE / "apteki_sample.csv", tmp_path)
    assert stats == {"leki": 8, "apteki": 5}
    row = duckdb.sql(f"SELECT cena FROM '{tmp_path / 'leki.parquet'}' WHERE id = 1").fetchall()[0]
    assert row[0] == 12.5


def test_map_rpl_header_does_not_take_atc_as_ean():
    header = ["Nazwa Produktu Leczniczego", "Kod ATC", "Podmiot odpowiedzialny", "Opakowanie",
              "Podmiot odpowiedzialny w kraju eksportu", "Substancja czynna"]
    m = etl.map_columns(header, etl.LEKI_RULES)
    assert "ean" not in m
    assert m["podmiot"] == "Podmiot odpowiedzialny"  # nie kraj eksportu


def test_parse_packs_splits_blob_and_flags_deleted():
    blob = "05909990865314 ¦ Rp ¦ Skasowane ¦ 17230 10 tabl. 05909991187040 ¦ Rp ¦ 103460 50 tabl."
    packs = etl.parse_packs(blob)
    assert packs == [
        {"ean": "05909990865314", "kat": "Rp", "skasowane": True, "opis": "10 tabl."},
        {"ean": "05909991187040", "kat": "Rp", "skasowane": False, "opis": "50 tabl."},
    ]
    assert etl.parse_packs("60 szt.") == []  # zwykły tekst (wykaz refundacyjny) bez zmian


def test_prepare_leki_rpl_packs():
    rows, stats = etl.prepare_leki(SAMPLE / "leki_rpl_sample.csv")
    assert stats["kept"] == 4
    recs = {r["nazwa"]: r for r in (dict(zip(etl.LEKI_COLUMNS, row)) for row in rows)}
    nospa = recs["NO-SPA"]
    assert nospa["ean"] == "05909990437719"  # z opakowania, nie "A03AD02"
    assert nospa["opakowanie"] == "" and nospa["kategoria"] == "OTC"
    assert nospa["aktywne"] == "1" and nospa["wycofane"] == "1"
    assert json.loads(nospa["opakowania"]) == [
        {"ean": "05909990437719", "kat": "OTC", "opis": "20 tabl."}
    ]
    assert nospa["podmiot"] == "Sanofi"
    assert recs["Metafen rozkurczowy"]["aktywne"] == "0"


def test_find_raw_prefers_largest_file(tmp_path):
    (tmp_path / "leki.csv").write_text("x" * 1000)
    small = tmp_path / "leki.xlsx"
    small.write_text("x")
    small.touch()  # nowsza data, ale mały plik
    assert etl.find_raw(tmp_path, "leki") == tmp_path / "leki.csv"


def _kinds(blob):
    return [(p["ean"], p["kat"], p["skasowane"], p["opis"]) for p in etl.parse_packs(blob)]


def test_parse_packs_eu_number_without_ean():
    blob = "Rpz ¦ EU/1/15/1040/001 ¦ 111248 7 tabl. Rpz ¦ EU/1/15/1040/002 ¦ 111249 28 tabl."
    assert _kinds(blob) == [("", "Rpz", False, "7 tabl."), ("", "Rpz", False, "28 tabl.")]


def test_parse_packs_veterinary_without_ean_or_eu():
    assert _kinds("OTC ¦ 46599 1 pipetka 4 ml OTC ¦ 46600 2 pipetki 4 ml") == [
        ("", "OTC", False, "1 pipetka 4 ml"),
        ("", "OTC", False, "2 pipetki 4 ml"),
    ]


def test_parse_packs_keeps_extras_and_drops_import_numbers():
    blob = (
        "05909990794843 ¦ Rp ¦ EU/1/96/020/007 ¦ 62 1 amp.-strzyk. 1 ml ¦ 1 igła ¦ "
        "UR/Z/4c/204/24 - 05050459002044 ¦ UR/Z/4c/002/25 - 05050459002044 "
        "05909990794850 ¦ Rp ¦ EU/1/96/020/008 ¦ 63 10 amp.-strzyk. 1 ml"
    )
    assert _kinds(blob) == [
        ("05909990794843", "Rp", False, "1 amp.-strzyk. 1 ml · 1 igła"),
        ("05909990794850", "Rp", False, "10 amp.-strzyk. 1 ml"),
    ]


def test_parse_packs_status_without_category_and_brak_placeholder():
    blob = (
        "05909990018543 ¦ OTC ¦ 28352 1 butelka 35 g "
        "05909990018567 ¦ Skasowane ¦ 28353 1 op. 1 kg "
        "BRAK ¦ Skasowane ¦ 40044 1 fiol. 10 ml"
    )
    assert _kinds(blob) == [
        ("05909990018543", "OTC", False, "1 butelka 35 g"),
        ("05909990018567", "", True, "1 op. 1 kg"),
        ("", "", True, "1 fiol. 10 ml"),
    ]


def test_parse_packs_glued_category_and_ean_with_eu_but_no_category():
    assert _kinds("1 pipetka 0,67 ml bRp ¦ Skasowane ¦ 30298 1 pipetka 1,34 ml") == [
        ("", "Rp", True, "1 pipetka 1,34 ml")
    ]
    assert _kinds("xLzRp ¦ Skasowane ¦ 865 3 amp. 1 ml")[0][1] == "Lz/Rp"
    assert _kinds("5391537750823 ¦ EU/2/08/080/004 ¦ 112766 1 butelka 30 tabl.") == [
        ("5391537750823", "", False, "1 butelka 30 tabl.")
    ]


def test_parse_packs_truncates_very_long_kit_description():
    blob = "05909990000011 ¦ Rp ¦ 1 " + " · ".join(["1 fiol. 10 ml"] * 40).replace(" · ", " ¦ ")
    (pack,) = etl.parse_packs(blob)
    assert len(pack["opis"]) <= etl.MAX_PACK_TEXT and pack["opis"].endswith("…")


def test_parse_packs_status_at_end_of_description():
    blob = (
        "05909990671946 ¦ OTC ¦ 30545 1 op. 50 g Skasowane ¦ 30546 1 op. 1 kg Skasowane "
        "¦ 30548 1 op. 5 kg 05909990671960 ¦ OTC ¦ 46850 1 op. 100 g"
    )
    assert _kinds(blob) == [
        ("05909990671946", "OTC", True, "1 op. 50 g"),
        ("", "OTC", True, "1 op. 1 kg"),
        ("", "OTC", False, "1 op. 5 kg"),
        ("05909990671960", "OTC", False, "1 op. 100 g"),
    ]
    blob = "05909990030637 ¦ OTC ¦ 28481 1 butelka 38 ml Skasowane ¦ 28482 1 butelka 100 g"
    assert _kinds(blob) == [
        ("05909990030637", "OTC", True, "1 butelka 38 ml"),
        ("", "OTC", False, "1 butelka 100 g"),
    ]
