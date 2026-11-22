# Lessons learned (PMI)

| Pole | Wartość |
|---|---|
| Identyfikator | TSL-DOC-003 |
| Tytuł | Lessons learned (PMI) |
| Wersja | 0.4 |
| Zatwierdził | Maintainer projektu |
| Data | 2026-11-22 |
| Status | Obowiązujący |

**Historia zmian**

| Wersja | Data | Autor | Zmiana |
|---|---|---|---|
| 0.1 | 2026-11-22 | Wersja początkowa |
| 0.2 | 2026-11-22 | Uzupełnienie o obserwacje z profilowania rzeczywistych danych, usunięcie znaczników do uzupełnienia |
| 0.3 | 2026-11-22 | Lekcje z uruchomienia na rejestrze RPL: pomylone źródło, parser opakowań, stare dane w Dockerze, wybór pliku |
| 0.4 | 2026-11-22 | Lekcja z przeglądu: licznik kontrolny nie był porównany ze źródłem (9 skasowanych opakowań); wyścig odpowiedzi w interfejsie |

---

Dokument opisuje, czego nauczyło nas zderzenie założeń z rzeczywistymi plikami z dane.gov.pl.
Liczby pochodzą z profilowania dostarczonych plików (patrz [jakość danych](jakosc-danych.md)).

## Co zadziałało

- **DuckDB + Parquet bez serwera bazy.** Prosty deploy (jeden kontener) i mały wynik: poprzedni build z 24 tys. rekordów rejestru
  aptek zajął 0,63 MB wobec 15,0 MB w CSV (ok. 25 razy mniej).
- **Mapowanie kolumn po słowach kluczowych.** Dwa zbiory mają różne formaty (XLSX z nagłówkami po polsku oraz CSV w cp1250 ze 77
  kolumnami `snake_case`) i oba przeszły przez ten sam mechanizm.
- **Tryb DEMO na próbce.** Aplikacja startuje od razu, a testy i CI są szybkie, bo nie wymagają pobierania danych.
- **Normalizacja pól wyszukiwania w ETL.** Wyszukiwanie bez polskich znaków nie kosztuje nic w czasie zapytania.
- **Wyodrębnienie czystej logiki ETL w Pythonie.** Czyszczenie i filtrowanie dają się testować bez uruchamiania bazy.
- **Liczniki kontrolne na całym pliku.** Parser opakowań sprawdziliśmy na wszystkich 23 034 komórkach (liczba opakowań, liczba
  statusów „Skasowane”), a nie na kilku przykładach. To ujawniło kolejne układy komórki, których pierwszy parser nie obejmował.
  Przegląd końcowy pokazał jednak, że licznik trzeba porównywać z liczbą wystąpień w źródle, a nie tylko z wynikiem parsera:
  9 opakowań miało status „Skasowane” na końcu opisu i było pokazywanych jako aktywne.

## Co nie zadziałało

- **Założenia o schemacie bez oglądania danych.** Pierwsza wersja mapowania zakładała kolumny „substancja czynna”,
  „poziom odpłatności” i „dopłata”. Rzeczywisty wykaz ma „Nazwę międzynarodową”, „Limit” i „Cenę detaliczną”, więc substancja
  była pusta (brak zamienników), a w rejestrze aptek pole ulicy trafiało do kolumny `adres_www`.
- **Brak filtrów jakości.** Z 24 033 rekordów rejestru aptek tylko 12 045 (50%) to apteki aktywne, ogólnodostępne lub punkty
  apteczne. Reszta to apteki nieaktywne (10 tys.), szpitalne i zakładowe. Pierwszy wynik zawierał m.in. aptekę szpitalną.
- **Kodowanie znaków.** Plik z aptekami ma polskie znaki zamienione na `?` już w źródle (nie da się ich odzyskać).
  Dotyczy to 4 794 z 12 045 aptek (39,8%) w polu miejscowość. Wyszukiwanie „Łódź” nie zwracało niczego, bo w danych jest `?ód?`.
- **Zbyt idealna próbka testowa.** Testy przechodziły na wymyślonych nagłówkach, a zawodziły na prawdziwych plikach.
- **Pomylone źródło leków.** Aplikację zaprojektowano pod wykaz refundacyjny z cenami, a do uruchomienia trafił rejestr produktów
  leczniczych (RPL) bez cen. Interfejs pokazywał puste „–”, a w karcie leku cała komórka „Opakowanie” (EAN, kategoria, status)
  wyświetlała się jako jeden długi tag. Pierwsza poprawka parsera objęła tylko najczęstszy układ (94% produktów); pozostałe
  (numer unijny zamiast EAN, produkty weterynaryjne, status bez kategorii) wykryła dopiero kontrola na całym pliku.
- **Stare dane w wolumenie Dockera.** Zmiana kodu ETL nie przebudowywała Parquet w `./data`, a strona główna była
  przechowywana w przeglądarce godzinę. Rozwiązanie: `etl_version` w `meta.json` i `Cache-Control: must-revalidate`.
- **Wybór pliku po dacie.** Obok pełnego rejestru leżała mała próbka `leki.xlsx`; wybór „najnowszego pliku” mógł ją
  przypadkiem wybrać. Teraz wygrywa największy plik.
- **Wyścig odpowiedzi w interfejsie.** Szybkie pisanie wysyłało kilka zapytań, a wolniejsza, starsza odpowiedź mogła
  nadpisać nowszą (lista nie pasowała do wpisanego tekstu). Naprawiono numerowaniem zapytań po stronie przeglądarki.
- **Semantyka „dopłaty”.** Dostarczony wykaz nie zawiera dopłaty ani poziomu odpłatności; w całym zbiorze cena detaliczna nie
  przekracza limitu, więc dopłata ponad limit wynosi 0 dla każdej pozycji.

## Co zrobilibyśmy inaczej

- Zacząć od **profilowania rzeczywistych danych** (nagłówki, kodowanie, braki, rozkład wartości) i dopiero potem projektować schemat.
- Próbkę testową **wzorować na prawdziwych plikach** (te same nagłówki, `?` w miejscu polskich liter, rekordy nieaktywne).
- Od początku **mierzyć wydajność w CI** (`scripts/benchmark.py`), a nie na końcu.
- Przed pierwszym uruchomieniem sprawdzić, **który zbiór** trafia do `data/raw` (RPL czy wykaz refundacyjny) i czy ma kolumny,
  na których opiera się interfejs; pokazywać w UI tylko to, co dane faktycznie zawierają.
- Wcześniej skonsultować z osobą z domeny (farmacja, refundacja), co znaczą pola takie jak „Limit”.
- Wcześniej wdrożyć wersję demo na hosting i zbierać uwagi użytkowników.

## Rekomendacje

1. Dołożyć pełny wykaz refundacyjny z cenami, poziomem odpłatności i dopłatą pacjenta i dołączyć go do RPL po EAN; wtedy
   porównanie zamienników będzie dotyczyć realnych kosztów. Dostarczony `leki.xlsx` ma tylko 423 pozycje.
2. Zgłosić wydawcy rejestru aptek utratę polskich znaków w eksporcie (problem leży po stronie źródła).
3. Dodać cykliczne odświeżanie danych (GitHub Actions + `scripts/fetch_data.py`).
4. Wykorzystać kody `terc`/`simc` z rejestru, by wyszukiwać apteki po lokalizacji i odległości (mapa).
5. Dodać testy wydajnościowe na pełnym zbiorze i monitorować p95 po wdrożeniu.
6. Dodać audyt dostępności (WCAG) interfejsu, bo grupa docelowa to także seniorzy.
