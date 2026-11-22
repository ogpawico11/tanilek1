# Jak współtworzyć projekt

## Zgłaszanie błędów i pomysłów
Użyj szablonów w zakładce *Issues* (błąd lub propozycja funkcji). Opisz kroki do odtworzenia, oczekiwane zachowanie
i środowisko (system, Docker lub uruchomienie lokalne). Przy błędach w danych podaj nazwę pliku i fragment wiersza (bez danych osobowych).

## Zasady
- Żadnych kluczy, haseł ani dużych plików danych w repozytorium (zmienne środowiskowe + `scripts/`). Próbki w `tests/sample/` mają być małe.
- Dokumenty w `docs/` mają nagłówek kontroli dokumentu (identyfikator, wersja, autor, data, historia zmian); zmiana dokumentu
  oznacza nową wersję, wpis w historii i aktualizację [rejestru](docs/rejestr-dokumentow.md).
- Nie publikujemy danych osobowych (kierownicy i właściciele aptek). Patrz [jakość danych](docs/jakosc-danych.md).
- Obowiązuje [Kodeks postępowania](CODE_OF_CONDUCT.md).
