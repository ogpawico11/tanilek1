# Rejestr dokumentów (ISO 10013)

| Pole | Wartość |
|---|---|
| Identyfikator | TSL-DOC-001 |
| Tytuł | Rejestr dokumentów (ISO 10013) |
| Wersja | 0.4 |
| Zatwierdził | Maintainer projektu |
| Data | 2026-11-22 |
| Status | Obowiązujący |

**Historia zmian**

| Wersja | Data | Autor | Zmiana |
|---|---|---|---|
| 0.1 | 2026-11-22 | Wersja początkowa |
| 0.2 | 2026-11-22 | Dodano autora i status do wszystkich dokumentów, nowy dokument TSL-DOC-005, naprawiono tabele nagłówkowe |
| 0.3 | 2026-11-22 | Nowe wersje TSL-DOC-002..005 po uruchomieniu na RPL; autor w wykazie ujednolicony z nagłówkami dokumentów |
| 0.4 | 2026-11-22 | Nowe wersje TSL-DOC-002, 003, 004, 005 po poprawce parsera opakowań i przeglądzie dokumentacji |

---

## Zasady kontroli dokumentów

Zgodnie z ISO 10013 każdy dokument w katalogu `docs/` zaczyna się tabelą z identyfikatorem,
tytułem, wersją, autorem, osobą zatwierdzającą, datą i statusem oraz tabelą **Historia zmian**.

- **Identyfikator:** `TSL-DOC-NNN`, nadawany raz i nigdy nie używany ponownie.
- **Wersja:** `0.x` dla wersji roboczych, `1.0` dla pierwszej zatwierdzonej; zmiana merytoryczna podnosi
  numer drugi (`1.1`), poprawka redakcyjna trzeci (`1.1.1`).
- **Zmiana dokumentu** to: nowa wersja + wpis w historii zmian tego dokumentu + aktualizacja tego rejestru.
- **Zatwierdzenie** odbywa się przez Pull Request zaakceptowany przez maintainera (patrz [CONTRIBUTING](../CONTRIBUTING.md)).
  Pełną historię zmian zachowuje dodatkowo git.
- **Status:** `Roboczy`, `Obowiązujący`, `Zastąpiony`.

## Wykaz dokumentów

| ID | Dokument | Plik | Wersja | Autor | Data | Status |
|---|---|---|---|---|---|---|
| TSL-DOC-001 | Rejestr dokumentów (ISO 10013) | [rejestr-dokumentow.md](rejestr-dokumentow.md) | 0.4 | 2026-11-22 | Obowiązujący |
| TSL-DOC-002 | Raport końcowy (ISO 21513) | [raport-koncowy.md](raport-koncowy.md) | 0.4  | 2026-11-22 | Obowiązujący |
| TSL-DOC-003 | Lessons learned (PMI) | [lessons-learned.md](lessons-learned.md) | 0.4  | 2026-11-22 | Obowiązujący |
| TSL-DOC-004 | Architektura | [architektura.md](architektura.md) | 0.4 | 2026-11-22 | Obowiązujący |
| TSL-DOC-005 | Jakość i pochodzenie danych | [jakosc-danych.md](jakosc-danych.md) | 0.3  | 2026-11-22 | Obowiązujący |
