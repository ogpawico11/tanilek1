"""API (FastAPI) + statyczny frontend. Dane czytane z Parquet przez DuckDB (w pamięci)."""
from __future__ import annotations

import json
import threading
from functools import lru_cache
from pathlib import Path

import duckdb
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse

from . import __version__, config
from .etl import lossy_pattern, norm

STATIC = Path(__file__).parent / "static"
LEKI_COLS = (
    "id, ean, nazwa, postac, dawka, substancja, opakowanie, grupa_limitowa, grupa_nazwa, "
    "cena_zbytu, limit_ceny, cena, doplata, poziom, "
    "podmiot, kategoria, aktywne, wycofane, opakowania"
)
APTEKI_COLS = "id, nazwa, rodzaj, miejscowosc, wojewodztwo, kod, ulica, telefon, godziny"

_lock = threading.Lock()
_con: duckdb.DuckDBPyConnection | None = None


def _sql_str(path: Path) -> str:
    return path.as_posix().replace("'", "''")


def get_con() -> duckdb.DuckDBPyConnection:
    """Jedno połączenie na proces; Parquet ładowany do pamięci raz (tabele, nie widoki)."""
    global _con
    with _lock:
        if _con is None:
            d = config.PROCESSED_DIR
            con = duckdb.connect()
            for name in ("leki", "apteki"):
                src = _sql_str(d / f"{name}.parquet")
                con.execute(f"CREATE TABLE {name} AS SELECT * FROM read_parquet('{src}')")
            _con = con
        return _con


def _rows(sql: str, params: list) -> list[dict]:
    cur = get_con().cursor()  # osobny kursor na zapytanie => bezpieczne wątkowo
    res = cur.execute(sql, params)
    names = [d[0] for d in res.description]
    return [dict(zip(names, r)) for r in res.fetchall()]


def _out(rows: tuple) -> list[dict]:
    """Krotki z cache -> słowniki do JSON; opakowania (tekst JSON w Parquet) -> lista."""
    result = []
    for r in rows:
        d = dict(r)
        raw = d.get("opakowania")
        d["opakowania"] = json.loads(raw) if raw else []
        result.append(d)
    return result


def _freeze(rows: list[dict]) -> tuple:
    return tuple(tuple(r.items()) for r in rows)


@lru_cache(maxsize=2048)
def _leki(q: str, limit: int) -> tuple:
    like = f"%{q}%"
    sql = (
        f"SELECT {LEKI_COLS} FROM leki WHERE nazwa_search LIKE ? OR substancja_search LIKE ? "
        "OR grupa_search LIKE ? ORDER BY CASE WHEN aktywne = 0 THEN 1 ELSE 0 END, "
        "CASE WHEN nazwa_search LIKE ? THEN 0 ELSE 1 END, "
        "doplata NULLS LAST, cena NULLS LAST, nazwa, id LIMIT ?"
    )
    return _freeze(_rows(sql, [like, like, like, f"{q}%", limit]))


@lru_cache(maxsize=2048)
def _zamienniki(lek_id: int) -> tuple:
    base = _rows("SELECT klucz_zamiennika FROM leki WHERE id = ?", [lek_id])
    if not base or not base[0]["klucz_zamiennika"]:
        return ()
    sql = (
        f"SELECT {LEKI_COLS} FROM leki WHERE klucz_zamiennika = ? AND id <> ? AND aktywne > 0 "
        "ORDER BY doplata NULLS LAST, cena NULLS LAST, nazwa, id"
    )
    return _freeze(_rows(sql, [base[0]["klucz_zamiennika"], lek_id]))


@lru_cache(maxsize=2048)
def _apteki(q: str, miasto: str, limit: int) -> tuple:
    where: list[str] = []
    params: list = []
    order = "miejscowosc, ulica"
    if miasto:
        pattern = lossy_pattern(miasto)
        where.append("regexp_matches(miejscowosc_search, ?)")
        params.append(pattern)
        order = "CASE WHEN regexp_full_match(miejscowosc_search, ?) THEN 0 ELSE 1 END, " + order
        order_params = [pattern]
    else:
        order_params = []
    if q:
        where.append("regexp_matches(nazwa_search, ?)")
        params.append(lossy_pattern(q))
    sql = f"SELECT {APTEKI_COLS} FROM apteki"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += f" ORDER BY {order} LIMIT ?"
    return _freeze(_rows(sql, params + order_params + [limit]))


@lru_cache(maxsize=1)
def _meta() -> dict:
    path = config.PROCESSED_DIR / "meta.json"
    info = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    con = get_con()
    return {
        "demo": bool(info.get("demo", False)),
        "built_at": info.get("built_at"),
        "leki": con.execute("SELECT count(*) FROM leki").fetchone()[0],
        "apteki": con.execute("SELECT count(*) FROM apteki").fetchone()[0],
        "zrodlo": "dane.gov.pl",
    }


def reset() -> None:
    """Zamyka połączenie i czyści cache (po przebudowie danych oraz w testach)."""
    global _con
    with _lock:
        if _con is not None:
            _con.close()
        _con = None
    for fn in (_leki, _zamienniki, _apteki, _meta):
        fn.cache_clear()


def _clean_q(q: str) -> str:
    return norm(q.replace("%", " ").replace("_", " "))


app = FastAPI(title="tanszylek", version=__version__)
app.add_middleware(GZipMiddleware, minimum_size=500)


@app.middleware("http")
async def cache_headers(request: Request, call_next):
    """Dane zmieniają się tylko przy przebudowie, więc przeglądarka może je krótko trzymać."""
    response = await call_next(request)
    path = request.url.path
    if request.method == "GET" and "cache-control" not in response.headers:
        if path.startswith("/api/") and path != "/api/health":
            response.headers["Cache-Control"] = "public, max-age=300"
        elif path == "/":
            # strona zmienia się razem z obrazem Dockera: zawsze sprawdzaj, czy nie ma nowej wersji
            response.headers["Cache-Control"] = "public, max-age=0, must-revalidate"
    return response


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/meta")
def meta():
    return _meta()


@app.get("/api/leki")
def leki(q: str = Query("", max_length=100), limit: int = Query(50, ge=1, le=200)):
    return _out(_leki(_clean_q(q), limit))


@app.get("/api/leki/{lek_id}/zamienniki")
def zamienniki(lek_id: int):
    if not _rows("SELECT 1 AS x FROM leki WHERE id = ?", [lek_id]):
        raise HTTPException(404, "Nie znaleziono leku")
    return _out(_zamienniki(lek_id))


@app.get("/api/apteki")
def apteki(
    miasto: str = Query("", max_length=100),
    q: str = Query("", max_length=100),
    limit: int = Query(50, ge=1, le=200),
):
    return [dict(r) for r in _apteki(norm(q), norm(miasto), limit)]


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")
