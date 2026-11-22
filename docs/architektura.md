# Architektura

| Pole | Wartość |
|---|---|
| Identyfikator | TSL-DOC-004 |
| Tytuł | Architektura |
| Wersja | 0.4 |
| Zatwierdził | Maintainer projektu |
| Data | 2026-11-22 |
| Status | Obowiązujący |

**Historia zmian**

| Wersja | Data | Zmiana |
|---|---|---|---|
| 0.1 | 2026-11-22 | Wersja początkowa |
| 0.2 | 2026-11-22 | Nowy model danych (zamienniki wg substancji, dawki i postaci), filtr aptek, wyszukiwanie odporne na utratę polskich znaków, cache HTTP |
| 0.3 | 2026-11-22 | Dwa formaty źródła leków (RPL i wykaz refundacyjny), parser opakowań, `etl_version` w `meta.json`, wybór największego pliku w `data/raw`, cache strony głównej |
| 0.4 | 2026-11-22 |  `ETL_VERSION` 4 (parser opakowań rozpoznaje status na końcu opisu), numerowanie zapytań we froncie, odnośnik do pomiaru wydajności |

---

## Przepływ danych

```
dane.gov.pl API ──> scripts/fetch_data.py ──> data/raw (CSV/XLSX, poza gitem)
  ──> etl.py (Python: mapowanie kolumn, czyszczenie, filtrowanie; DuckDB: typy + Parquet ZSTD)
  ──> data/processed/*.parquet + meta.json
  ──> api.py (FastAPI; DuckDB ładuje Parquet do pamięci raz)
  ──> static/index.html (jeden plik, bez frameworka)
```

Przy starcie `python -m tanszylek` buduje dane, jeśli ich brak, surowe pliki są nowsze od wyniku ETL albo zmienił się
układ danych: `meta.json` zapisuje `etl_version`, a różnica względem `ETL_VERSION` w kodzie wymusza przebudowę. Dzięki temu
wolumen Dockera (`./data`) ze starymi plikami Parquet odświeża się sam po aktualizacji obrazu. Gdy w `data/raw` leży kilka
plików `leki*`, używany jest największy, więc mała próbka (np. `leki.xlsx`) nie wypiera pełnego rejestru.
Bez plików w `data/raw` aplikacja działa w trybie DEMO na próbce z `tests/sample/`
(`meta.json` zapamiętuje tryb, więc baner DEMO nie znika po restarcie).

## Model danych

**leki**: `id, ean, nazwa, postac, dawka, substancja, opakowanie, grupa_limitowa, grupa_nazwa, cena_zbytu, limit_ceny,
cena, doplata, poziom, podmiot, kategoria, aktywne, wycofane, opakowania` oraz kolumny pomocnicze
`nazwa_search, substancja_search, grupa_search, klucz_zamiennika`. Ten sam ETL obsługuje dwa formaty źródła:

- **Rejestr produktów leczniczych (RPL)**: jedna pozycja = jeden produkt, a wszystkie jego opakowania leżą w jednej komórce.
  ETL (`parse_packs`) rozbija ją na listę (`opakowania`: EAN, kategoria OTC/Rp/Rpz/Rpw/Lz, opis), liczy opakowania
  aktywne (`aktywne`) i skasowane (`wycofane`) oraz zapisuje podmiot odpowiedzialny (`podmiot`). Format komórki opisano w kodzie
  i w [jakości danych](jakosc-danych.md). RPL nie zawiera cen ani refundacji.
- **Wykaz refundacyjny** (opcjonalny): jedna pozycja = jedno opakowanie z ceną, limitem i grupą limitową.

- `doplata`: jeśli zbiór jej nie zawiera, liczymy `max(cena − limit, 0)` (cena detaliczna ponad limit).
- `klucz_zamiennika` = substancja + dawka + postać (gdy brak dawki: dodatkowo grupa limitowa).
  Zamiennik to pozycja o tym samym kluczu, więc nie łączymy różnych dawek ani postaci.

**apteki**: `id, nazwa, rodzaj, miejscowosc, wojewodztwo, kod, ulica, telefon, godziny` oraz
`nazwa_search` (nazwa + ulica) i `miejscowosc_search`.

- Do wyniku trafiają tylko apteki **aktywne** o rodzaju *apteka ogólnodostępna* lub *punkt apteczny*.
- Dane osobowe kierowników i właścicieli (imiona, nazwiska, NIP) nie są kopiowane do wyniku.

## API

| Metoda i ścieżka | Opis |
|---|---|
| `GET /api/leki?q=&limit=` | Wyszukiwanie po nazwie, substancji lub nazwie grupy (bez polskich znaków), max 200 wyników; produkty bez aktywnych opakowań na końcu |
| `GET /api/leki/{id}/zamienniki` | Zamienniki o tym samym kluczu, tylko z aktywnymi opakowaniami; od najniższej dopłaty, potem ceny; 404 dla nieznanego `id` |
| `GET /api/apteki?miasto=&q=&limit=` | Apteki w miejscowości, opcjonalnie filtr po nazwie lub ulicy |
| `GET /api/meta` | Liczebność zbiorów, tryb DEMO, data przetworzenia |
| `GET /api/health` | Sprawdzenie stanu (healthcheck Dockera i hostingu) |

## Techniki optymalizacji

- **Parquet + ZSTD**: kolumnowy, mały i szybki w odczycie (poprzedni build z 24 tys. rekordów: 0,63 MB wobec 15,0 MB CSV).
- **Dane w pamięci**: DuckDB ładuje Parquet do tabel w pamięci raz przy starcie, zapytania nie dotykają dysku.
- **Wstępnie znormalizowane kolumny `*_search`**: normalizacja liczona raz w ETL, a nie przy każdym zapytaniu.
- **Cache LRU** (2048 wpisów) wyników zapytań, z kluczem po normalizacji zapytania.
- **Cache HTTP** (`Cache-Control`): API 5 minut; strona główna z `must-revalidate`, żeby po aktualizacji obrazu przeglądarka nie trzymała starego `index.html`. **Gzip** odpowiedzi.
- **Filtrowanie w ETL**: do aplikacji trafia ok. połowa rekordów rejestru aptek (tylko aktywne i dla pacjentów).
- **Kursor na zapytanie** (bezpieczne wątkowo), limit wyników (max 200), parametryzowane zapytania SQL.
- **Frontend bez frameworka**: jeden plik HTML, brak zewnętrznych zasobów, debounce 250 ms przy pisaniu; numerowanie zapytań
  sprawia, że spóźniona odpowiedź nie nadpisuje nowszej.

Pomiar: `python scripts/benchmark.py --out docs/benchmark.md` (p50/p95 i rozmiar odpowiedzi dla głównych ścieżek).

## Wyszukiwanie odporne na utratę polskich znaków

W rejestrze aptek litery ą, ć, ę, ł, ń, ś, ź, ż są w pliku źródłowym zapisane jako `?`
(patrz [jakość danych](jakosc-danych.md)). Zapytanie `Łódź` jest zamieniane na wyrażenie regularne
`[l?][o?]d[z?]`, które pasuje zarówno do `Łódź`, jak i do `?ód?`.

## Bezpieczeństwo

- Klucze i adresy tylko w zmiennych środowiskowych (`.env.example`), `.env` jest w `.gitignore`.
- Zapytania SQL są parametryzowane; fragmenty SQL są stałe, a ze znaków specjalnych w zapytaniu
  użytkownika jest budowane tylko escapowane wyrażenie regularne.
- Frontend escapuje wszystkie dane przed wstawieniem do HTML.

## Znane ograniczenia

- RPL (główny zbiór leków) nie zawiera cen ani refundacji, więc interfejs pokazuje dostępność (OTC / Rp) zamiast ceny i nie
  wskazuje „najtańszego zamiennika”. Dołączenie wykazu refundacyjnego po EAN jest opisane w rekomendacjach ([lessons learned](lessons-learned.md)).
- Wykaz refundacyjny z dostarczonej próbki ma 423 pozycje i nie ma kolumn poziomu odpłatności ani dopłaty; cena detaliczna
  nie przekracza limitu, więc obliczona dopłata wynosi 0 i porównanie opiera się na cenie.
- 1 413 z 23 034 produktów RPL nie ma EAN (produkty z pozwoleniem unijnym, weterynaryjne); pokazujemy dla nich opis opakowania.
- Brak geolokalizacji: aptek szukamy po nazwie miejscowości, bez odległości.
- Mapowanie kolumn zależy od nagłówków; zmianę formatu przez wydawcę wykryje test z nagłówkami rzeczywistych plików.
