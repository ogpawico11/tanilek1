#!/usr/bin/env python3
"""Pobiera zbiory z API dane.gov.pl do data/raw/ (duże pliki nie trafiają do repozytorium).

Użycie:
  python scripts/fetch_data.py search "leki refundowane"   # lista pasujących zbiorów (ID)
  python scripts/fetch_data.py resources 1234              # zasoby zbioru o ID 1234
  python scripts/fetch_data.py download 1234 leki          # pobiera CSV/XLSX do data/raw/
  python scripts/fetch_data.py download 5678 apteki
  python scripts/fetch_data.py url leki <URL>              # pobranie z bezpośredniego linku
  python scripts/fetch_data.py auto                        # LEKI_URL / APTEKI_URL ze środowiska

`auto` służy do wdrożeń (np. na darmowym hostingu): pobiera tylko brakujące pliki i nic nie robi,
gdy zmienne nie są ustawione. ID zbiorów znajdziesz poleceniem `search`; skrypt nie ma ich
zaszytych, bo wydawca aktualizuje zbiory cyklicznie. Odpowiedzi JSON:API są czytane defensywnie.
Klucz API (opcjonalny) tylko ze zmiennej środowiskowej DANE_API_KEY.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

API = os.getenv("DANE_API_URL", "https://api.dane.gov.pl/1.4").rstrip("/")
KEY = os.getenv("DANE_API_KEY", "")
RAW = Path(os.getenv("DATA_DIR", "data")) / "raw"
KINDS = ("leki", "apteki")
UA = "tanszylek/0.2"


def _request(url: str, accept: str = "*/*") -> urllib.request.Request:
    headers = {"Accept": accept, "User-Agent": UA}
    if KEY:
        headers["Authorization"] = f"Bearer {KEY}"
    return urllib.request.Request(url, headers=headers)


def _get(url: str) -> dict:
    with urllib.request.urlopen(_request(url, "application/vnd.api+json"), timeout=60) as r:
        return json.load(r)


def _institution(attrs: dict) -> str:
    inst = attrs.get("institution")
    return str(inst.get("title", "")) if isinstance(inst, dict) else str(inst or "")


def search(query: str) -> list[dict]:
    qs = urllib.parse.urlencode({"q": query, "per_page": 20})
    data = _get(f"{API}/datasets?{qs}").get("data", [])
    for d in data:
        a = d.get("attributes", {})
        print(f"{str(d.get('id')):>8}  {a.get('title')}  [{_institution(a)}]")
    return data


def resources(dataset_id: str) -> list[dict]:
    out = _get(f"{API}/datasets/{dataset_id}/resources?per_page=100").get("data", [])
    for r in out:
        a = r.get("attributes", {})
        rid = str(r.get("id"))
        print(f"{rid:>8}  {a.get('format')}  {a.get('title')}  {a.get('download_url')}")
    return out


def pick_resource(items: list[dict]) -> dict | None:
    """Wybiera najświeższy zasób CSV/XLSX (po `data_date`, a gdy go brak: pierwszy)."""
    ok = []
    for r in items:
        a = r.get("attributes", {})
        fmt = (a.get("format") or "").lower()
        if fmt in {"csv", "xlsx"} and (a.get("download_url") or a.get("link")):
            ok.append(r)
    return max(ok, key=lambda r: str(r["attributes"].get("data_date") or ""), default=None)


def _extension(url: str, content_disposition: str | None) -> str:
    for text in (content_disposition or "", urllib.parse.urlparse(url).path):
        m = re.search(r"\.(csv|xlsx)\b", text, re.I)
        if m:
            return m.group(1).lower()
    return "csv"


def fetch_url(kind: str, url: str) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(_request(url), timeout=300) as r:
        ext = _extension(url, r.headers.get("Content-Disposition"))
        tag = hashlib.sha1(url.encode()).hexdigest()[:8]
        target = RAW / f"{kind}_{tag}.{ext}"
        print(f"-> {target}")
        target.write_bytes(r.read())
    return target


def download(dataset_id: str, kind: str) -> Path:
    chosen = pick_resource(resources(dataset_id))
    if chosen is None:
        sys.exit("Nie znaleziono zasobu CSV/XLSX w tym zbiorze.")
    a = chosen["attributes"]
    return fetch_url(kind, a.get("download_url") or a.get("link"))


def auto() -> None:
    """Pobiera brakujące pliki wskazane zmiennymi LEKI_URL i APTEKI_URL."""
    for kind in KINDS:
        url = os.getenv(f"{kind.upper()}_URL", "")
        have = any(
            kind in p.name.lower() and p.suffix.lower() in {".csv", ".xlsx", ".xlsm"}
            for p in RAW.glob("*")
        )
        if url and not have:
            fetch_url(kind, url)
        elif not url and not have:
            print(f"Pomijam {kind}: brak pliku w {RAW} i zmiennej {kind.upper()}_URL.")


if __name__ == "__main__":
    cmd, *args = sys.argv[1:] or ["help"]
    if cmd == "search" and args:
        search(" ".join(args))
    elif cmd == "resources" and args:
        resources(args[0])
    elif cmd == "download" and len(args) == 2 and args[1] in KINDS:
        download(*args)
    elif cmd == "url" and len(args) == 2 and args[0] in KINDS:
        fetch_url(*args)
    elif cmd == "auto":
        auto()
    else:
        print(__doc__)
