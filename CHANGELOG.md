# Changelog
Format: [Keep a Changelog](https://keepachangelog.com/), wersjonowanie SemVer.

## [Unreleased]
### Changed
- Dokumenty w `docs/` (TSL-DOC-001..005) opisują rejestr RPL jako główne źródło leków; nowe wersje i historia zmian wg ISO 10013.
- `pyproject.toml`: jawny zestaw reguł ruffa (E, F, W, I), żeby CI nie zależało od domyślnych reguł nowszych wersji.
### Fixed
- Parser opakowań RPL: status „Skasowane” na końcu opisu (bez `¦`) był ignorowany, więc 9 skasowanych opakowań wyglądało na aktywne; po poprawce 5 687 skasowanych = liczba w źródle. `ETL_VERSION` = 4, więc Parquet przebuduje się sam.
- Interfejs: wolniejsza, starsza odpowiedź nie nadpisuje już nowszej (numerowanie zapytań).
- Dokumenty TSL-DOC-001..005: skorygowane liczby (88 725 opakowań, 5 687 skasowanych, 4 produkty bez opakowań).
- Rejestr RPL: kolumna „Opakowanie” (EAN ¦ kategoria ¦ status ¦ numer + opis) jest rozbijana na listę opakowań; w karcie leku widać tylko aktywne opakowania, a nie jeden długi blok tekstu.
- Parser opakowań RPL obsługuje wszystkie układy występujące w danych (opakowania bez EAN, z numerem unijnym, weterynaryjne, bez kategorii, `BRAK`, dodatki typu „1 igła”, numery importu równoległego); sprawdzony na pełnym pliku: 88 725 opakowań, 5 687 skasowanych (zgodnie ze źródłem).
- Kategoria dostępności nie zawiera już pustych wartości (np. „Rp, ”).
- Produkty z samymi skasowanymi opakowaniami nie trafiają już do zamienników i są na końcu wyników wyszukiwania (oznaczone „wycofany z obrotu”).
- `ean` nie jest już mapowany na kolumnę „Kod ATC”.
- Brak cen w danych (RPL): zamiast pustego „–” karta pokazuje dostępność (OTC / Rp), a UI nie obiecuje „najtańszego zamiennika”.
- Karta pokazuje podmiot odpowiedzialny, żeby odróżnić kilka pozycji o tej samej nazwie (np. import równoległy).
- Docker: `meta.json` zawiera `etl_version` (obecnie 4); po zmianie układu danych kontener sam przebuduje Parquet z `data/raw`.
- Docker: strona główna nie jest cache’owana przez godzinę (po aktualizacji obrazu przeglądarka pobiera nowy `index.html`).
- `find_raw` wybiera największy plik, a nie najnowszy (mały `leki.xlsx` nie wypiera pełnego rejestru).

## [0.2.0] - 2026-11-22
### Added
- Obsługa rzeczywistych plików z dane.gov.pl (wykaz leków XLSX, rejestr aptek CSV w cp1250).
- Zamienniki wg substancji, dawki i postaci; wyszukiwanie także po nazwie grupy (polskie nazwy substancji).
- Filtr aktywnych aptek ogólnodostępnych i punktów aptecznych, godziny otwarcia, filtr po ulicy lub nazwie apteki.
- Wyszukiwanie odporne na utratę polskich znaków w danych źródłowych (`?`).
- `meta.json` (tryb DEMO, data przetworzenia), automatyczna przebudowa danych przy nowszych plikach w `data/raw`.
- `scripts/fetch_data.py`: wybór najświeższego zasobu, `url`, `auto` (`LEKI_URL`, `APTEKI_URL`); `scripts/benchmark.py`.
- Cache HTTP, dane DuckDB w pamięci, `render.yaml`, `.dockerignore`, test dymny Dockera w CI.
- Dokument TSL-DOC-005 (jakość i pochodzenie danych).
### Changed
- Dokumenty w `docs/` mają pełny nagłówek ISO 10013 (autor, zatwierdzający, status, historia zmian).
- Raport końcowy i lessons learned oparte na rzeczywistych danych (bez znaczników do uzupełnienia).
- `docker-compose.yml` bez wymogu nowej składni `env_file`.
### Fixed
- Puste pole substancji (kolumna „Nazwa międzynarodowa”) i ulica mapowana na `adres_www`.
- Rejestr aptek zawierał apteki nieaktywne i szpitalne.
- Niespójny nagłówek tabel w dokumentach (brak kolumn autora).
- Brak danych kontaktowych w `CODE_OF_CONDUCT.md`, brak właściciela praw w `LICENSE`.
### Security
- Dane osobowe kierowników i właścicieli aptek nie są przetwarzane.

## [0.1.0] - 2026-11-22
### Added
- ETL CSV/XLSX -> Parquet (DuckDB), mapowanie kolumn po słowach kluczowych.
- API: wyszukiwanie leków, zamienników (wg najniższej dopłaty), aptek.
- Frontend, Dockerfile, docker-compose, CI (ruff + pytest), dokumentacja ISO/PMI.
