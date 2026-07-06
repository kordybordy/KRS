# KRS Monitor CGI

Projekt automatycznie monitoruje zmiany w danych KRS dla dwóch spółek CGI. Raz w tygodniu pobiera pełny odpis KRS, zapisuje snapshot, porównuje go z poprzednią wersją i generuje raport zmian w Markdown, JSON oraz CSV z pełną tabelą porównania wartości.

Obecna wersja może opcjonalnie tworzyć issue na GitHubie z krótkim podsumowaniem zmian, bez używania osobnych danych logowania do poczty. Wyniki są też zapisywane w repozytorium, commitowane przez GitHub Actions i publikowane jako artifacts.

## Monitorowane spółki

| Spółka | KRS |
| --- | --- |
| CGI Information Systems and Management Consultants (Polska) Sp. z o.o. | `0000078664` |
| CGI Polska S.A. | `0000307263` |

## Źródło danych i wybrany endpoint PRS

Źródłem danych jest wyłącznie oficjalne PRS KRS OpenAPI dostępne pod adresem:

```text
https://prs.ms.gov.pl/krs/openApi
```

Wybrany endpoint:

```text
GET https://api-krs.ms.gov.pl/api/krs/OdpisPelny/{krs}?rejestr=P&format=json
```

Uzasadnienie:

Dokumentacja PRS KRS OpenAPI wskazuje osobną usługę „Pobranie odpisu pełnego” pod endpointem `/api/krs/OdpisPelny/{krs}`. Zakres tej usługi odpowiada odpisowi pełnemu KRS, czyli obejmuje także dane wykreślone. Parametr `rejestr=P` wybiera rejestr przedsiębiorców, właściwy dla monitorowanych spółek, a `format=json` zwraca dane jako JSON.

Projekt nie scrapuje publicznych stron HTML KRS.

## Uruchomienie lokalne

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src python -m krs_monitor.main
```

Opcjonalnie można ustawić poziom logowania:

```bash
LOG_LEVEL=DEBUG PYTHONPATH=src python -m krs_monitor.main
```

## Testy

Testy jednostkowe nie korzystają z live API PRS i bazują na danych lokalnych.

```bash
PYTHONPATH=src pytest
```

## Jak działa monitor

Program wykonywany przez `python -m krs_monitor.main`:

1. Wczytuje listę monitorowanych spółek z `src/krs_monitor/config.py`.
2. Pobiera pełny odpis KRS dla każdego numeru KRS z oficjalnego PRS KRS OpenAPI.
3. Zapisuje surowy payload w archiwum.
4. Normalizuje JSON przez rekurencyjne sortowanie kluczy, normalizację whitespace i usunięcie oczywistych metadanych technicznych, w tym czasu wygenerowania odpisu (`dataCzasOdpisu`).
5. Porównuje aktualny snapshot z poprzednim plikiem `data/latest/<krs>.json`.
6. Zapisuje nowy snapshot w `data/latest/` tylko po poprawnym pobraniu i normalizacji danych.
7. Generuje `report.md`, `report.json`, `summary.txt` i `comparison.csv` z kolumnami starej wartości, nowej wartości oraz statusem `changed`/`no_change`/`added`/`removed`.
8. Wypisuje krótkie podsumowanie do stdout.

Jeżeli pobranie jednego podmiotu się nie powiedzie, program loguje błąd, oznacza go w raporcie i nadal próbuje przetworzyć pozostałe spółki. Uszkodzony lub niepobrany payload nie jest zapisywany jako nowy `latest` snapshot.

## Ścieżki zapisu danych

```text
data/latest/<krs>.json
data/archive/<krs>/<timestamp>.json
reports/YYYY-MM-DD/report.md
reports/YYYY-MM-DD/report.json
reports/YYYY-MM-DD/summary.txt
reports/YYYY-MM-DD/comparison.csv
```

Przykład:

```text
data/archive/0000078664/2026-06-04T08-17-00+02-00.json
data/latest/0000078664.json
reports/2026-06-04/report.md
reports/2026-06-04/report.json
reports/2026-06-04/summary.txt
reports/2026-06-04/comparison.csv
```

## GitHub Actions

Workflow znajduje się w `.github/workflows/krs-monitor.yml`.

Dostępne triggery:

- `workflow_dispatch` — ręczne uruchomienie.
- `schedule` — dwa crony w UTC: `0 7 * * 4` i `0 8 * * 4`.

GitHub Actions używa czasu UTC, dlatego workflow stosuje guard w Bashu. Dla uruchomień planowanych właściwe monitorowanie przechodzi dalej tylko wtedy, gdy lokalny czas `Europe/Warsaw` to czwartek między `09:00` a `09:59`. Obsługuje to różnicę między czasem letnim i zimowym oraz typowe opóźnienia schedulerów GitHub Actions. Uruchomienia ręczne nie są blokowane przez ten guard.

Workflow:

1. Checkoutuje repozytorium.
2. Ustawia Python 3.12.
3. Instaluje zależności z `requirements.txt`.
4. Uruchamia `pytest`.
5. Uruchamia `python -m krs_monitor.main`.
6. Dopisuje najnowsze `summary.txt` do GitHub Actions job summary.
7. Uploaduje katalog `reports/` jako artifact `krs-report`.
8. Commituje zmienione pliki `data/latest`, `data/archive` i `reports`.
9. Jeżeli wykryto zmiany, tworzy GitHub issue z krótkim podsumowaniem raportu. GitHub wyśle e-mail osobom obserwującym repozytorium lub wymienionym przez GitHub username.

Commit ma format:

```text
krs-monitor: weekly report YYYY-MM-DD
```

Jeżeli nie ma zmian, workflow wypisuje:

```text
No changes to commit.
```

i nie kończy się błędem.

## Zmiana częstotliwości na dwutygodniową

Najprościej zostawić tygodniowy cron i dodać w Pythonie guard oparty o numer tygodnia ISO, np. na początku `main()`:

```python
from datetime import date

if date.today().isocalendar().week % 2 != 0:
    print("Skipping this week due to biweekly schedule.")
    return 0
```

W takim wariancie workflow uruchamia się co tydzień, ale właściwe monitorowanie działa tylko w wybrane tygodnie parzyste lub nieparzyste.

## Powiadomienia przez GitHub

Workflow może tworzyć GitHub issue tylko wtedy, gdy raport wykryje zmiany. Nie wymaga to sekretów SMTP ani hasła do poczty, bo używany jest wbudowany `GITHUB_TOKEN`.

Jeżeli chcesz, aby GitHub dodatkowo wysłał maila konkretnej osobie, ta osoba musi otrzymywać powiadomienia GitHub dla repozytorium albo trzeba ją wymienić po GitHub username. W repository variables można ustawić:

```text
KRS_GITHUB_NOTIFY_USERS
KRS_GITHUB_MAX_DETAILS
```

`KRS_GITHUB_NOTIFY_USERS` może zawierać jeden username albo kilka username'ów oddzielonych przecinkami, np.:

```text
przemek-github, marcin-github
```

Adres e-mail nie wystarczy do wymuszenia powiadomienia przez GitHub issue. GitHub nie pozwala wysyłać maili do dowolnych adresów z `GITHUB_TOKEN`.

## Powiadomienia SMTP

Opcjonalny moduł SMTP nadal jest dostępny, jeżeli kiedyś będzie potrzebna bezpośrednia wysyłka e-maili. Wymaga jednak danych logowania lub tokenu dostawcy poczty. Jeżeli sekrety nie są ustawione, workflow nie używa SMTP.

W GitHub repository settings dodaj sekrety:

```text
KRS_EMAIL_SMTP_HOST
KRS_EMAIL_SMTP_PORT
KRS_EMAIL_USERNAME
KRS_EMAIL_PASSWORD
KRS_EMAIL_FROM
KRS_EMAIL_TO
```

`KRS_EMAIL_TO` może zawierać jeden adres albo kilka adresów oddzielonych przecinkami. Opcjonalne sekrety:

```text
KRS_EMAIL_USE_TLS
KRS_EMAIL_USE_SSL
KRS_EMAIL_SUBJECT_PREFIX
KRS_EMAIL_MAX_DETAILS
```

Domyślnie używany jest port `587` i STARTTLS. Dla SMTP over SSL ustaw `KRS_EMAIL_USE_SSL=true` oraz `KRS_EMAIL_USE_TLS=false`.
