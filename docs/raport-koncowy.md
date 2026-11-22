# Raport końcowy projektu (szkielet ISO 21513)

| Pole | Wartość |
|---|---|
| Identyfikator | TSL-DOC-002 |
| Tytuł | Raport końcowy projektu (szkielet ISO 21513) |
| Wersja | 0.4 |
| Zatwierdził | Maintainer projektu |
| Data | 2026-11-22 |
| Status | Obowiązujący |

**Historia zmian**

| Wersja | Data | Autor | Zmiana |
|---|---|---|---|
| 0.1 | 2026-11-22 | Wersja początkowa |
| 0.2 | 2026-11-22 | Dane liczbowe z rzeczywistych zbiorów, tabela zgodności z kryteriami oceny, usunięcie znaczników do uzupełnienia |
| 0.3 | 2026-11-22 | Aktualizacja wyników po uruchomieniu na rejestrze RPL: dane liczbowe, odchylenia od planu, ograniczenie wpływu |
| 0.4 | 2026-11-22 | Korekta liczby opakowań po poprawce parsera (88 725, w tym 5 687 skasowanych) |

---

## 1. Cel

**Problem.** Pacjent z receptą nie wie, że lek z tą samą substancją, dawką i postacią może kosztować mniej pod inną nazwą handlową,
a informacje o aptekach są rozproszone w dużych arkuszach, które trudno przeszukać.

**Cel projektu.** Zbudować otwartą wyszukiwarkę opartą na danych z dane.gov.pl, która:
1. znajduje lek po nazwie handlowej, substancji lub nazwie grupy (także bez polskich znaków),
2. pokazuje zamienniki (ta sama substancja, dawka i postać), a gdy zbiór zawiera ceny, od najniższej dopłaty i ceny,
3. wyszukuje aktywne apteki w miejscowości wraz z telefonem i godzinami otwarcia,
4. uruchamia się jedną komendą i może być odtworzona przez każdego na podstawie publicznych danych.

## 2. Rezultaty

| Rezultat | Szczegóły |
|---|---|
| Repozytorium open source | Licencja MIT, README, CONTRIBUTING, CODE_OF_CONDUCT, CHANGELOG, `.env.example`, szablony zgłoszeń i PR |
| Pipeline danych | `scripts/fetch_data.py` → ETL (Python + DuckDB) → Parquet ZSTD → API FastAPI → interfejs WWW |
| Dane leków | RPL: 23 034 produkty, 88 725 opakowań (83 038 aktywnych i 5 687 wycofanych), 10 594 substancje czynne; 12 777 produktów ma co najmniej jeden zamiennik (2 627 grup). Opcjonalny wykaz refundacyjny (423 pozycje z cenami) obsługuje ten sam ETL |
| Dane aptek | 24 033 rekordy rejestru → **12 045** aktywnych aptek ogólnodostępnych i punktów aptecznych w 3 119 miejscowościach |
| Jakość danych | Filtr aktywnych aptek, obsługa utraty polskich znaków (`?`), pominięcie danych osobowych, patrz [jakość danych](jakosc-danych.md) |
| Testy i CI | Testy ETL, API i skryptu pobierania; GitHub Actions: `ruff`, `pytest`, budowa obrazu Dockera i test dymny |
| Deploy | `docker compose up` (tryb DEMO lub dane z `data/raw`), `render.yaml` dla darmowego hostingu |
| Dokumentacja | Ten raport, lessons learned (PMI), kontrola dokumentów (ISO 10013), architektura, jakość danych |

Data przetworzenia danych jest zapisywana w `data/processed/meta.json` i wyświetlana w stopce aplikacji.

## 3. Porównanie z planem

| Wymaganie z zadania | Plan | Stan | Dowód |
|---|---|---|---|
| Publiczne repozytorium, licencja, README | tak | zrobione | `LICENSE` (MIT), `README.md` |
| Pliki standardowe w katalogu głównym | tak | zrobione | README, LICENSE, CONTRIBUTING, CODE_OF_CONDUCT, CHANGELOG, `.env.example` |
| Kod w `src/`, testy w `tests/`, dokumentacja w `docs/` | tak | zrobione | struktura repozytorium |
| Duże dane poza repozytorium, skrypt pobierania w `scripts/` | tak | zrobione | `.gitignore`, `scripts/fetch_data.py`; w repo tylko próbka w `tests/sample/` |
| `.github/`: szablony i CI (testy + linter na PR) | tak | zrobione | `.github/workflows/ci.yml` |
| Klucze tylko w zmiennych środowiskowych | tak | zrobione | `config.py`, `.env.example` |
| Raport końcowy (ISO 21513) | tak | zrobione | ten dokument |
| Lessons learned (PMI) | tak | zrobione | [lessons-learned.md](lessons-learned.md) |
| Kontrola dokumentów (ISO 10013) | tak | zrobione | nagłówki dokumentów, [rejestr](rejestr-dokumentow.md) |
| Deploy jedną komendą | tak | zrobione | `docker compose up`, instrukcja w README |
| Wydajność i optymalizacja | tak | zrobione, pomiar skryptem | [architektura](architektura.md), `scripts/benchmark.py` |

**Odchylenia od planu:** główny zbiór leków (RPL) nie zawiera cen ani refundacji, więc interfejs pokazuje dostępność (OTC / Rp)
zamiast ceny; wykaz refundacyjny nie ma poziomu odpłatności ani dopłaty (dopłatę liczymy jako cenę ponad limit);
polskie znaki w rejestrze aptek są zgubione w źródle, więc dodano wyszukiwanie odporne na `?`.

## 4. Wpływ

**Użyteczność społeczna.** Narzędzie skraca drogę od recepty do informacji: pacjent (w tym senior) może sprawdzić, czy jest
zamiennik tej samej substancji, dawki i postaci, oraz znaleźć czynną aptekę w swojej miejscowości wraz z telefonem i godzinami.
Dane są publiczne, ale wcześniej leżały w arkuszu o 77 kolumnach (apteki) i w wykazie bez wyszukiwarki (leki).

**Ograniczenie wpływu.** Na danych z RPL narzędzie pokazuje, jakie zamienniki i opakowania są w obrocie, ale nie porównuje
cen, bo rejestr ich nie zawiera. Dostarczony wykaz refundacyjny (423 pozycje) nie ma pozycji z ceną ponad limit. Pełny efekt
(oszczędność na dopłacie) wymaga pełnego wykazu refundacyjnego z poziomem odpłatności, dołączonego do RPL po EAN.

**Wskaźniki do monitorowania po wdrożeniu:** czas odpowiedzi p50/p95 i rozmiar odpowiedzi
(`python scripts/benchmark.py`), liczba zapytań dziennie, odsetek zapytań bez wyniku, liczba zgłoszeń w Issues.

## 5. Wnioski

1. Otwarte dane mają wartość dopiero po oczyszczeniu: połowa rekordów rejestru aptek nie jest dla pacjenta
   (apteki nieaktywne, szpitalne), a prawie 40% nazw miejscowości ma zgubione polskie litery.
2. DuckDB i Parquet wystarczają do szybkiej, tanio hostowanej aplikacji bez osobnej bazy danych.
3. Testy i próbka danych muszą odzwierciedlać prawdziwe pliki, inaczej nie wykryją błędów mapowania; parser formatu
   złożonego (komórka „Opakowanie”) trzeba sprawdzać licznikami na całym pliku, a nie na przykładach.
4. Dalsze kroki i rekomendacje: [lessons learned](lessons-learned.md).
