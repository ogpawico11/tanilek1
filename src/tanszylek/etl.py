"""ETL: surowe CSV/XLSX z dane.gov.pl -> znormalizowane pliki Parquet (ZSTD).

Zbiory publiczne mają niestandardowe nagłówki i kodowania, dlatego:
* kolumny mapujemy po słowach kluczowych (bez polskich znaków), a nie po sztywnych nazwach,
* czyszczenie i filtrowanie robimy w Pythonie (łatwe do testowania),
* DuckDB służy do typowania kolumn i zapisu Parquet (ZSTD).

Dane osobowe (imiona i nazwiska kierowników oraz właścicieli aptek) są świadomie pomijane:
do wyniku trafiają wyłącznie kolumny potrzebne pacjentowi.
"""
from __future__ import annotations

import csv
import io
import json
import re
import tempfile
import unicodedata
from pathlib import Path

import duckdb

Rules = dict[str, list[tuple[str, ...]]]

# Podnieś, gdy zmienia się układ danych przetworzonych: przy starcie kontener przebuduje Parquet
# z istniejących plików w data/raw (wolumen Dockera zachowuje stare Parquet między wersjami).
ETL_VERSION = 4

# kanoniczna kolumna -> lista krotek słów kluczowych (pierwsze dopasowanie wygrywa).
# Słowo z przedrostkiem "-" oznacza: nazwa kolumny NIE może go zawierać.
LEKI_RULES: Rules = {
    "substancja": [("substancja",), ("miedzynarodowa",), ("powszechnie",)],
    "nazwa": [("nazwa", "-miedzynarodowa", "-grup")],
    "postac": [("postac", "-dawk")],
    "dawka": [("dawka",)],
    # bez ("kod",): w rejestrze RPL pasowałoby do kolumny "Kod ATC". EAN-y czytamy z opakowań.
    "ean": [("gtin",), ("ean",)],
    "podmiot": [("podmiot", "odpowiedzialny", "-eksport")],
    "opakowanie": [("zawartosc",), ("opakowan",)],
    "grupa_limitowa": [("identyfikator", "grup")],
    "grupa_nazwa": [("nazwa", "grup")],
    "cena_zbytu": [("cena", "zbytu")],
    "limit_ceny": [("limit", "-grup", "-podstaw")],
    "cena": [("cena", "detaliczna"), ("cena", "-zbytu")],
    "poziom": [("poziom", "odplatnosci"), ("odplatnosc",)],
    "doplata": [("doplat",)],
}
APTEKI_RULES: Rules = {
    "nazwa": [("nazwa", "apteki"), ("nazwa", "-ulic", "-wlasciciel", "-grup")],
    "stan": [("stan", "apteki"), ("stan",)],
    "rodzaj": [("rodzaj", "apteki")],
    "wojewodztwo": [("wojewodztwo", "-wlasciciel")],
    "miejscowosc": [("miejscowosc", "-wlasciciel"), ("miasto",)],
    "kod": [("kod", "pocztowy", "-wlasciciel"), ("kod", "-wlasciciel")],
    "typ_ulicy": [("typ", "ulicy", "-wlasciciel")],
    "nazwa_ulicy": [
        ("nazwa", "ulicy", "-wlasciciel"),
        ("ulica", "-wlasciciel"),
        ("adres", "-www", "-wlasciciel"),
    ],
    "numer_budynku": [("numer", "budynku", "-wlasciciel")],
    "numer_lokalu": [("numer", "lokalu", "-wlasciciel")],
    "telefon": [("telefon", "-wlasciciel")],
    "godz_pn": [("godziny", "poniedzialek")],
    "godz_wt": [("godziny", "wtorek")],
    "godz_sr": [("godziny", "sroda")],
    "godz_cz": [("godziny", "czwartek")],
    "godz_pt": [("godziny", "piatek")],
    "godz_sb": [("godziny", "sobota")],
    "godz_nd": [("godziny", "niedziela")],
}
REQUIRED = {"leki": ["nazwa"], "apteki": ["miejscowosc"]}

LEKI_COLUMNS = [
    "id", "ean", "nazwa", "postac", "dawka", "substancja", "opakowanie", "grupa_limitowa",
    "grupa_nazwa", "cena_zbytu", "limit_ceny", "cena", "doplata", "poziom",
    "podmiot", "kategoria", "aktywne", "wycofane", "opakowania",
    "nazwa_search", "substancja_search", "grupa_search", "klucz_zamiennika",
]
LEKI_NUMERIC = {"cena_zbytu", "limit_ceny", "cena", "doplata"}
LEKI_INT = {"aktywne", "wycofane"}
APTEKI_COLUMNS = [
    "id", "nazwa", "rodzaj", "miejscowosc", "wojewodztwo", "kod", "ulica", "telefon",
    "godziny", "nazwa_search", "miejscowosc_search",
]

# W rejestrze aptek polskie znaki bywają zamienione na "?" (utrata w pliku źródłowym).
# Takie litery wyszukiwarka traktuje jak dżokera, patrz lossy_pattern().
LOSSY_LETTERS = set("acelnosz")
ACTIVE_STATES = {"aktywna"}
PATIENT_FACING = ("apteka ogolnodost", "punkt apteczny")


def norm(text: str | None) -> str:
    """Małe litery, bez znaków diakrytycznych (także ł)."""
    if text is None:
        return ""
    text = unicodedata.normalize("NFKD", str(text).lower().replace("ł", "l"))
    return "".join(c for c in text if not unicodedata.combining(c)).strip()


def lossy_pattern(text: str) -> str:
    """Wyrażenie regularne dla tekstu, w którym litery z możliwym ogonkiem pasują też do "?"."""
    out = []
    for ch in norm(text):
        if ch in LOSSY_LETTERS:
            out.append(f"[{ch}?]")
        elif ch in ".^$*+?()[]{}|\\":
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp1250"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")  # nigdy nie zgłasza błędu


def _delimiter(text: str) -> str:
    lines = text.splitlines()
    first = lines[0] if lines else ""
    return max(";,\t|", key=first.count)


def _cell(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def read_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    """Wczytuje CSV (UTF-8 lub cp1250) albo XLSX do (nagłówek, wiersze) jako tekst."""
    if path.suffix.lower() in {".xlsx", ".xlsm"}:
        import openpyxl

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            it = wb.active.iter_rows(values_only=True)
            header = [_cell(v) for v in next(it, ())]
            rows = [[_cell(v) for v in r] for r in it]
        finally:
            wb.close()
    else:
        text = _decode(path.read_bytes())
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=_delimiter(text))
        header = [_cell(v) for v in next(reader, [])]
        rows = [[_cell(v) for v in r] for r in reader]
    width = len(header)
    rows = [(r + [""] * width)[:width] for r in rows if any(r)]
    return header, rows


def map_columns(columns: list[str], rules: Rules) -> dict[str, str]:
    """Dopasowuje kanoniczne nazwy do nagłówków pliku (każda kolumna użyta najwyżej raz)."""
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for canon, options in rules.items():
        for words in options:
            need = [w for w in words if not w.startswith("-")]
            ban = [w[1:] for w in words if w.startswith("-")]
            hit = next(
                (
                    c
                    for c in columns
                    if c and c not in used
                    and all(w in norm(c) for w in need)
                    and not any(w in norm(c) for w in ban)
                ),
                None,
            )
            if hit:
                mapping[canon] = hit
                used.add(hit)
                break
    return mapping


def _records(header: list[str], rows: list[list[str]], rules: Rules, kind: str):
    mapping = map_columns(header, rules)
    missing = [c for c in REQUIRED[kind] if c not in mapping]
    if missing:
        raise ValueError(f"Brak wymaganych kolumn {missing}; znaleziono: {header}")
    idx = {canon: header.index(col) for canon, col in mapping.items()}
    for row in rows:
        yield {canon: row[i] for canon, i in idx.items()}


def to_number(text: str | None) -> float | None:
    """'1 048,68' -> 1048.68; puste lub błędne -> None."""
    if text is None:
        return None
    cleaned = re.sub(r"[\s\u00a0]", "", str(text)).replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _num_str(value: float | None) -> str:
    return "" if value is None else repr(round(value, 2))


def zamiennik_key(rec: dict[str, str]) -> str:
    """Klucz równoważności: ta sama substancja, dawka i postać (gdy brak dawki: grupa limitowa)."""
    subst = norm(rec.get("substancja"))
    if not subst:
        return ""
    key = f"{subst}|{norm(rec.get('dawka'))}|{norm(rec.get('postac'))}"
    if not rec.get("dawka"):
        key += f"|{rec.get('grupa_limitowa', '')}"
    return key


# Rejestr RPL trzyma wszystkie opakowania produktu w jednej komórce. Początek opakowania to
# EAN i/lub kategoria dostępności, dalej segmenty rozdzielone znakiem "¦":
#   "05909990437719 ¦ OTC ¦ 14232 20 tabl."                      EAN ¦ kategoria ¦ numer + opis
#   "05909990865314 ¦ Rp ¦ Skasowane ¦ 17230 10 tabl."           ... ze statusem
#   "Rpz ¦ EU/1/15/1040/001 ¦ 111248 7 tabl."                    bez EAN, z numerem unijnym
#   "OTC ¦ 46599 1 pipetka 4 ml"                                 weterynaryjne, bez EAN
#   "05909990018567 ¦ Skasowane ¦ 28353 1 op. 1 kg"               bez kategorii
#   "BRAK ¦ Skasowane ¦ 40044 1 fiol. 10 ml"                      brak EAN w źródle
#   "... ¦ 62 1 amp.-strzyk. 1 ml ¦ 1 igła ¦ UR/Z/4c/204/24 - 0505..."  dodatki i numery importu
# W źródle trafiają się też sklejone kategorie ("LzRp") i śmieciowy przedrostek ("bRp", "xLzRp").
MAX_PACK_TEXT = 140
_CAT = r"[A-Za-z]{0,3}(?:OTC|Rpz|Rpw|Rp|Lz)+"
PACK_START = re.compile(
    rf"(?:(?<=\s)|^)(?:"
    # EAN, a po nim kategoria albo od razu status / numer unijny (np. "EAN ¦ Skasowane ¦ ...")
    rf"(?P<ean>\d{{8,14}}|BRAK)\s*¦\s*(?=(?:{_CAT})\s*¦|Skasowane|EU/)(?:(?P<kat>{_CAT})\s*¦)?"
    rf"|(?P<kat2>{_CAT})\s*¦)"
)
_KAT = re.compile(r"OTC|Rpz|Rpw|Rp|Lz")
_CODE = re.compile(r"^(?:EU|[A-Z]{2})/")  # numer pozwolenia unijnego lub importu równoległego


_SUBPACK = re.compile(r"^\d+\s+\d")  # kolejne opakowanie bez własnego EAN: "numer ilość ..."
_TRAILING_STATUS = re.compile(r"\s+Skasowane$")  # status na końcu opisu, bez separatora "¦"


def parse_packs(text: str | None) -> list[dict]:
    """Rozbija komórkę "Opakowanie" z RPL na listę opakowań (pusta, gdy to zwykły tekst)."""
    text = text or ""
    starts = list(PACK_START.finditer(text))
    packs = []
    for n, m in enumerate(starts):
        end = starts[n + 1].start() if n + 1 < len(starts) else len(text)
        kat = "/".join(_KAT.findall(m.group("kat") or m.group("kat2") or ""))
        ean = "" if m.group("ean") in (None, "BRAK") else m.group("ean")
        # grupy segmentów: [części opisu, czy skasowane]; opakowania bez EAN bywają sklejone
        groups: list[list] = [[[], False]]
        prev_inline = False
        for seg in (x.strip() for x in text[m.end():end].split("¦")):
            if not seg:
                continue
            if norm(seg) == "skasowane":
                groups[-1][1] = True
                continue
            if _CODE.match(seg):
                continue
            inline = _TRAILING_STATUS.search(seg)
            if inline:
                seg = seg[: inline.start()].rstrip()
            # po opakowaniu ze statusem na końcu opisu następny "numer ilość" to nowe opakowanie
            if prev_inline and _SUBPACK.match(seg):
                groups.append([[], False])
            groups[-1][0].append(seg)
            if inline:
                groups[-1][1] = True
            prev_inline = bool(inline)
        for i, (parts, deleted) in enumerate(groups):
            if not parts:
                continue
            # pierwszy segment zaczyna się od numeru wewnętrznego opakowania
            parts[0] = re.sub(r"^\d+\s+(?=\S)", "", parts[0])
            opis = " · ".join(x for j, x in enumerate(parts) if j == 0 or x[:1].isdigit())
            if len(opis) > MAX_PACK_TEXT:  # zestawy (proszek + rozpuszczalnik + igły) bywają długie
                opis = opis[: MAX_PACK_TEXT - 1].rstrip() + "…"
            packs.append(
                {"ean": ean if i == 0 else "", "kat": kat, "skasowane": deleted, "opis": opis}
            )
    return packs


def prepare_leki(path: Path) -> tuple[list[list[str]], dict[str, int]]:
    header, rows = read_rows(path)
    out: list[list[str]] = []
    skipped = 0
    for rec in _records(header, rows, LEKI_RULES, "leki"):
        if not rec.get("nazwa"):
            skipped += 1
            continue
        nums = {k: to_number(rec.get(k)) for k in LEKI_NUMERIC}
        if nums["doplata"] is None and nums["cena"] is not None and nums["limit_ceny"] is not None:
            # lista nie zawiera dopłaty: liczymy ją jako cenę detaliczną ponad limit
            nums["doplata"] = max(nums["cena"] - nums["limit_ceny"], 0.0)
        line = {k: rec.get(k, "") for k in LEKI_COLUMNS}
        line.update({k: _num_str(v) for k, v in nums.items()})
        line["id"] = str(len(out) + 1)
        line["nazwa_search"] = norm(rec["nazwa"])
        line["substancja_search"] = norm(rec.get("substancja"))
        line["grupa_search"] = norm(rec.get("grupa_nazwa"))
        line["klucz_zamiennika"] = zamiennik_key(rec)
        packs = parse_packs(rec.get("opakowanie"))
        if packs:
            active = [p for p in packs if not p["skasowane"]]
            shown = active or packs
            line["opakowanie"] = ""  # surowy ciąg zastępuje lista w kolumnie "opakowania"
            line["ean"] = line["ean"] or next((p["ean"] for p in shown if p["ean"]), "")
            line["kategoria"] = ", ".join(dict.fromkeys(p["kat"] for p in shown if p["kat"]))
            line["aktywne"] = str(len(active))
            line["wycofane"] = str(len(packs) - len(active))
            line["opakowania"] = json.dumps(
                [{"ean": p["ean"], "kat": p["kat"], "opis": p["opis"]} for p in active],
                ensure_ascii=False,
                separators=(",", ":"),
            )
        else:  # np. wykaz refundacyjny: jedno opakowanie w osobnym wierszu, zawsze aktywne
            line["aktywne"], line["wycofane"] = "1", "0"
        out.append([line[c] for c in LEKI_COLUMNS])
    return out, {"read": len(rows), "kept": len(out), "skipped": skipped}


def format_hours(rec: dict[str, str]) -> str:
    week = [rec.get(k, "") for k in ("godz_pn", "godz_wt", "godz_sr", "godz_cz", "godz_pt")]
    parts = []
    if all(week) and len(set(week)) == 1:
        parts.append(f"pn–pt: {week[0]}")
    else:
        parts += [f"{d}: {h}" for d, h in zip(("pn", "wt", "śr", "czw", "pt"), week) if h]
    if rec.get("godz_sb"):
        parts.append(f"sob: {rec['godz_sb']}")
    if rec.get("godz_nd"):
        parts.append(f"niedz. handlowa: {rec['godz_nd']}")
    return " · ".join(parts)


def format_street(rec: dict[str, str]) -> str:
    number = rec.get("numer_budynku", "")
    if rec.get("numer_lokalu"):
        number = f"{number}/{rec['numer_lokalu']}" if number else rec["numer_lokalu"]
    street = ""
    if rec.get("nazwa_ulicy"):  # sam typ ("ul.") bez nazwy to wieś bez ulic
        street = f"{rec.get('typ_ulicy', '')} {rec['nazwa_ulicy']}".strip()
    if street:
        return f"{street} {number}".strip()
    return f"nr {number}" if number else ""


def _is_patient_facing(rec: dict[str, str]) -> bool:
    if "stan" in rec and norm(rec["stan"]) not in ACTIVE_STATES:
        return False
    if "rodzaj" in rec and not norm(rec["rodzaj"]).startswith(PATIENT_FACING):
        return False
    return True


def prepare_apteki(path: Path) -> tuple[list[list[str]], dict[str, int]]:
    header, rows = read_rows(path)
    out: list[list[str]] = []
    dropped = 0
    for rec in _records(header, rows, APTEKI_RULES, "apteki"):
        if not _is_patient_facing(rec) or not rec.get("miejscowosc"):
            dropped += 1
            continue
        city = rec["miejscowosc"].title() if rec["miejscowosc"].isupper() else rec["miejscowosc"]
        rodzaj = "Punkt apteczny" if norm(rec.get("rodzaj")).startswith("punkt") else "Apteka"
        name = rec.get("nazwa", "").replace('""', '"').strip() or rodzaj
        street = format_street(rec)
        line = {
            "id": str(len(out) + 1),
            "nazwa": name,
            "rodzaj": rodzaj,
            "miejscowosc": city,
            "wojewodztwo": rec.get("wojewodztwo", "").lower(),
            "kod": rec.get("kod", ""),
            "ulica": street,
            "telefon": rec.get("telefon", ""),
            "godziny": format_hours(rec),
            "nazwa_search": norm(f"{name} {street}"),
            "miejscowosc_search": norm(city),
        }
        out.append([line[c] for c in APTEKI_COLUMNS])
    return out, {"read": len(rows), "kept": len(out), "dropped": dropped}


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _sql_str(path: Path) -> str:
    return path.as_posix().replace("'", "''")


def write_parquet(
    con: duckdb.DuckDBPyConnection,
    columns: list[str],
    rows: list[list[str]],
    numeric: set[str],
    target: Path,
    workdir: Path,
    ints: frozenset[str] | set[str] = frozenset(),
) -> None:
    csv_path = workdir / (target.stem + ".csv")
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(rows)
    select = []
    for c in columns:
        if c == "id" or c in ints:
            select.append(f"TRY_CAST({_q(c)} AS BIGINT) AS {_q(c)}")
        elif c in numeric:
            select.append(f"TRY_CAST(NULLIF({_q(c)}, '') AS DOUBLE) AS {_q(c)}")
        else:
            select.append(f"NULLIF({_q(c)}, '') AS {_q(c)}")
    con.execute(
        f"CREATE OR REPLACE TABLE out AS SELECT {', '.join(select)} "
        "FROM read_csv(?, header=true, all_varchar=true, delim=',', quote='\"', escape='\"')",
        [str(csv_path)],
    )
    con.execute(f"COPY out TO '{_sql_str(target)}' (FORMAT PARQUET, COMPRESSION ZSTD)")


def build(raw_leki: Path, raw_apteki: Path, out_dir: Path) -> dict[str, int]:
    """Buduje leki.parquet i apteki.parquet; zwraca liczbę wierszy w każdym z nich."""
    out_dir.mkdir(parents=True, exist_ok=True)
    leki, _ = prepare_leki(raw_leki)
    apteki, _ = prepare_apteki(raw_apteki)
    with tempfile.TemporaryDirectory() as tmp:
        con = duckdb.connect()
        try:
            write_parquet(
                con, LEKI_COLUMNS, leki, LEKI_NUMERIC, out_dir / "leki.parquet", Path(tmp), LEKI_INT
            )
            write_parquet(con, APTEKI_COLUMNS, apteki, set(), out_dir / "apteki.parquet", Path(tmp))
        finally:
            con.close()
    return {"leki": len(leki), "apteki": len(apteki)}


def find_raw(directory: Path, kind: str) -> Path | None:
    """Największy plik CSV/XLSX, którego nazwa zawiera `kind` ("leki" lub "apteki").

    Rozmiar, a nie data: po skopiowaniu danych do wolumenu Dockera daty plików bywają dowolne,
    a przypadkowy mały plik (np. próbka leki.xlsx) nie powinien wypierać pełnego zbioru.
    """
    found = [
        p
        for p in directory.glob("*")
        if kind in p.name.lower() and p.suffix.lower() in {".csv", ".xlsx", ".xlsm"}
    ]
    return max(found, key=lambda p: (p.stat().st_size, p.stat().st_mtime), default=None)
