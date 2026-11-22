#!/usr/bin/env python3
"""Prosty pomiar wydajności działającej aplikacji (tylko biblioteka standardowa).

Użycie:
  python scripts/benchmark.py                       # http://localhost:8000
  python scripts/benchmark.py --base http://host:8000 --repeat 30 --out docs/benchmark.md

Mierzy czas odpowiedzi (ms) i rozmiar przesyłanej odpowiedzi (z gzip) dla głównych ścieżek:
pierwsze zapytanie (zimne, bez cache serwera) oraz powtórzone (cache LRU).
Wynik drukuje jako tabelę Markdown i opcjonalnie zapisuje do pliku.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.parse
import urllib.request

LEKI_QUERIES = ["metformina", "atorwastatyna", "ibuprofen", "amlodypina", "insulina", "omeprazol"]
CITIES = ["Warszawa", "Kraków", "Łódź", "Wrocław", "Poznań", "Gdańsk"]


def timed(url: str) -> tuple[float, int, bytes]:
    req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()  # rozmiar po kompresji (bez dekodowania)
    return (time.perf_counter() - t0) * 1000, len(body), body


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1)))]


def row(name: str, samples: list[tuple[float, int]]) -> str:
    ms = [s[0] for s in samples]
    kb = statistics.mean(s[1] for s in samples) / 1024
    return (
        f"| {name} | {len(ms)} | {statistics.median(ms):.1f} | {percentile(ms, 95):.1f} "
        f"| {max(ms):.1f} | {kb:.1f} |"
    )


def run(base: str, repeat: int) -> str:
    base = base.rstrip("/")
    q = urllib.parse.quote
    lines = [
        "| Scenariusz | Próby | p50 [ms] | p95 [ms] | max [ms] | Odpowiedź [KB] |",
        "|---|---|---|---|---|---|",
    ]
    page = [timed(f"{base}/")[:2] for _ in range(repeat)]
    lines.append(row("Strona główna (HTML, gzip)", page))

    cold = [timed(f"{base}/api/leki?q={q(w)}")[:2] for w in LEKI_QUERIES]
    lines.append(row("Szukaj leku, zimne zapytanie", cold))
    warm = [timed(f"{base}/api/leki?q={q(LEKI_QUERIES[0])}")[:2] for _ in range(repeat)]
    lines.append(row("Szukaj leku, z cache", warm))

    ids = []
    for w in LEKI_QUERIES:
        body = urllib.request.urlopen(f"{base}/api/leki?q={q(w)}&limit=5", timeout=30).read()
        ids += [x["id"] for x in json.loads(body)]
    if ids:
        subs = [timed(f"{base}/api/leki/{i}/zamienniki")[:2] for i in ids[: max(repeat, 10)]]
        lines.append(row("Zamienniki leku", subs))

    cold_a = [timed(f"{base}/api/apteki?miasto={q(c)}")[:2] for c in CITIES]
    lines.append(row("Szukaj apteki w mieście, zimne", cold_a))
    warm_a = [timed(f"{base}/api/apteki?miasto={q(CITIES[0])}")[:2] for _ in range(repeat)]
    lines.append(row("Szukaj apteki w mieście, z cache", warm_a))
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--repeat", type=int, default=30)
    ap.add_argument("--out", help="zapisz tabelę do pliku Markdown")
    args = ap.parse_args()
    table = run(args.base, args.repeat)
    print(table)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(table + "\n")
