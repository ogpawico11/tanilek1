# Jakość i pochodzenie danych

| Pole | Wartość |
|---|---|
| Identyfikator | TSL-DOC-005 |
| Tytuł | Jakość i pochodzenie danych |
| Wersja | 0.3 |
| Zatwierdził | Maintainer projektu |
| Data | 2026-11-22 |
| Status | Obowiązujący |

**Historia zmian**

| Wersja | Data | Autor | Zmiana |
|---|---|---|---|
| 0.1 | 2026-11-22 | Wersja początkowa |
| 0.2 | 2026-11-22 | Rejestr produktów leczniczych jako główne źródło leków, opis formatu opakowań, nowe reguły jakości |
| 0.3 | 2026-11-22 | Korekta liczb po poprawce parsera opakowań (status „Skasowane” na końcu opisu) i uwaga o 4 produktach bez opakowań |

---

## Źródła

| Zbiór | Źródło | Plik | Użycie |
|---|---|---|---|
| Rejestr produktów leczniczych (RPL) | [dane.gov.pl](https://dane.gov.pl) | `data/raw/leki.csv` (CSV, 34 kolumny, 23 034 produkty) | nazwa, postać, substancja czynna, podmiot odpowiedzialny, opakowania (EAN, kategoria, status) |
| Wykaz leków z limitami finansowania (opcjonalnie) | [dane.gov.pl](https://dane.gov.pl) | `data/raw/leki.xlsx` (XLSX, 12 kolumn, 423 pozycje) | nazwa, postać, dawka, substancja, cena, limit |
| Rejestr aptek | [dane.gov.pl](https://dane.gov.pl) | `data/raw/apteki.csv` (CSV, cp1250, 77 kolumn, 24 033 rekordy) | adres, telefon, godziny, stan i rodzaj apteki |

Pliki nie są w repozytorium. Pobiera je `scripts/fetch_data.py` (patrz README). Licencja zbiorów jest podana na stronie
każdego zbioru w dane.gov.pl i obowiązuje dane, a nie kod aplikacji (kod: MIT).

## Profil danych i zastosowane reguły

| Problem | Skala | Reguła w ETL |
|---|---|---|
| Apteki nieaktywne, zawieszone, oczekujące | 10 332 z 24 033 | zostają tylko rekordy o stanie `AKTYWNA` |
| Apteki szpitalne, zakładowe, działy farmacji szpitalnej | 1 656 spośród aktywnych | zostają `APTEKA OGÓLNODOSTĘPNA` i `PUNKT APTECZNY` |
| Polskie znaki zastąpione `?` w źródle | 4 794 z 12 045 aptek (39,8%) w polu miejscowość | wyszukiwanie traktuje `?` jak literę z ogonkiem (`lossy_pattern`) |
| Brak nazwy apteki | 1 182 z 12 045 | nazwa zastępcza „Apteka” lub „Punkt apteczny” |
| Brak nazwy ulicy (miejscowości bez ulic) | 813 z 12 045 | adres w postaci „nr 5” |
| Nazwy zapisane WERSALIKAMI, `""` w nazwach | pojedyncze | normalizacja wielkości liter w miejscowości, usunięcie podwójnych cudzysłowów |
| Brak telefonu / godzin otwarcia | 173 / 514 z 12 045 | pole puste, nie jest wyświetlane |
| Brak kolumn dopłaty i poziomu odpłatności w wykazie leków | wszystkie 423 pozycje | dopłata = `max(cena − limit, 0)`; w tym zbiorze zawsze 0 |
| Brak dawki w części pozycji (np. diety, wyciągi alergenowe) | 29 z 423 | klucz zamiennika uwzględnia wtedy grupę limitową |
| Kodowanie pliku | CSV w cp1250, XLSX w Unicode | próba UTF-8, następnie cp1250, na końcu latin-1 |
| RPL: brak cen i refundacji | wszystkie 23 034 produkty | interfejs pokazuje kategorię dostępności (OTC / Rp / Rpz / Rpw / Lz) zamiast ceny |
| RPL: wszystkie opakowania produktu w jednej komórce | 88 725 opakowań w 23 034 komórkach (4 komórki są puste) | rozbicie na listę przez `parse_packs`; opis układów poniżej |
| RPL: opakowania skasowane | 5 687 z 88 725 opakowań (2 629 produktów ma co najmniej jedno) | nie są pokazywane; liczba wycofanych jest w polu `wycofane`; produkt bez aktywnych opakowań trafia na koniec wyników i nie jest zamiennikiem |
| RPL: brak EAN | 1 413 produktów (pozwolenia unijne, weterynaryjne) | pole `ean` puste, w karcie widać opis opakowania |
| RPL: brak substancji czynnej | 1 028 produktów | brak klucza zamiennika, więc bez zamienników |
| RPL: kilka pozycji o tej samej nazwie (np. NO-SPA) | m.in. import równoległy | pokazujemy podmiot odpowiedzialny |
| RPL: kolumna „Kod ATC” | wszystkie produkty | nie jest mapowana na `ean` |

## Rejestr produktów leczniczych: format komórki „Opakowanie”

Komórka zawiera opakowania rozdzielone spacją, a ich części znakiem `¦`. Początek opakowania to EAN i/lub kategoria
dostępności. Parser rozpoznaje układy, które występują w danych:

| Układ | Przykład |
|---|---|
| EAN, kategoria, numer i opis | `05909990437719 ¦ OTC ¦ 14232 20 tabl.` |
| ze statusem | `05909990865314 ¦ Rp ¦ Skasowane ¦ 17230 10 tabl.` |
| bez EAN, z numerem unijnym | `Rpz ¦ EU/1/15/1040/001 ¦ 111248 7 tabl.` |
| weterynaryjne, bez EAN | `OTC ¦ 46599 1 pipetka 4 ml` |
| bez kategorii | `05909990018567 ¦ Skasowane ¦ 28353 1 op. 1 kg` |
| brak EAN w źródle | `BRAK ¦ Skasowane ¦ 40044 1 fiol. 10 ml` |
| dodatki i numery importu | `… ¦ 62 1 amp.-strzyk. 1 ml ¦ 1 igła ¦ UR/Z/4c/204/24 - 05050459002044` |
| sklejona kategoria i przedrostek | `LzRp`, `bRp`, `xLzRp` |

Kontrola poprawności na pełnym pliku: 23 030 z 23 034 komórek daje co najmniej jedno opakowanie (4 produkty mają pustą komórkę: Dophacyl Avi, CEVAC REOMUNE,
Lotilaner/Milbemycin Elanco, Adstiladrin), a liczba opakowań oznaczonych jako skasowane (5 687) zgadza się z liczbą
wystąpień słowa „Skasowane” w kolumnie „Opakowanie” (status bywa też na końcu opisu, bez separatora `¦`). Numery unijne i importu
równoległego są pomijane w opisie; opisy dłuższe niż 140 znaków (zestawy z igłami i rozpuszczalnikiem) są skracane.

## Dane osobowe

Rejestr aptek zawiera imiona i nazwiska kierowników aptek, ich zastępców i właścicieli (osoby fizyczne) oraz numery NIP właścicieli.
Aplikacja **nie kopiuje** tych pól: ETL wybiera wyłącznie kolumny potrzebne pacjentowi (nazwa, adres, telefon kontaktowy
apteki, godziny). ETL mapuje tylko wymienione kolumny; kolumny `kierownik_*`, `wlasciciel_*` i `zastepca_kierownika_*` nie są w ogóle czytane,
a przy kolumnach adresowych reguły wprost wykluczają kolumny właściciela.

## Aktualność

Dane są tak aktualne, jak pobranie z dane.gov.pl. Data przetworzenia jest zapisywana w `meta.json` i pokazywana w aplikacji.
Odświeżenie: pobierz nowe pliki do `data/raw` (lub uruchom ponownie z ustawionymi `LEKI_URL` i `APTEKI_URL`); ETL uruchamia się
sam, gdy surowe pliki są nowsze od wyniku.

## Zastrzeżenie

Aplikacja jest pomocą w wyszukiwaniu, a nie poradą medyczną. Zamiennik zawsze konsultuj z lekarzem lub farmaceutą.
