# KRS Monitor CGI

Projekt automatycznie monitoruje zmiany w danych KRS dla dwóch spółek CGI. Raz w tygodniu pobiera pełny odpis KRS, zapisuje snapshot, porównuje go z poprzednią wersją i generuje raport zmian w Markdown, JSON oraz CSV z pełną tabelą porównania wartości.

Monitor może wysyłać cotygodniowy e-mail z wynikiem, zmienionymi wartościami na początku wiadomości oraz załączonym raportem i plikiem CSV. Wiadomość jest wysyłana również wtedy, gdy nie ma zmian. Nadawcą może być osobna skrzynka AgentMail, bez połączenia z prywatnym kontem Gmail. Opcjonalne issue na GitHubie nadal powstaje tylko przy wykryciu zmian. Wyniki są też zapisywane w repozytorium, commitowane przez GitHub Actions i publikowane jako artifacts.

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
- `schedule` — dwa crony w UTC dobrane do miesięcy czasu zimowego i letniego: `0 8 * 1,2,3,11,12 4` oraz `0 7 * 4,5,6,7,8,9,10 4`.

Ten workflow używa wpisów harmonogramu w UTC. Nie używa osobnego guardu, więc zaplanowany run nie kończy się pustym skipem. Harmonogram przybliża czwartek `09:00` czasu `Europe/Warsaw`; w tygodniach zmiany czasu run może wypaść godzinę wcześniej albo później.

Workflow:

1. Checkoutuje repozytorium.
2. Ustawia Python 3.12.
3. Instaluje zależności z `requirements.txt`.
4. Uruchamia `pytest`.
5. Uruchamia `python -m krs_monitor.main`.
   Następnie wywołuje moduł powiadomień SMTP dla daty raportu z tego konkretnego uruchomienia. Przy skonfigurowanej poczcie wysyła wynik co tydzień, także bez zmian. Błędy pobrania danych są oznaczane w wiadomości; błąd wysyłki powoduje niepowodzenie workflow.
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

Workflow wywołuje moduł SMTP po wygenerowaniu raportu. Wymaga danych logowania lub tokenu dostawcy poczty. Jeżeli sekrety nie są ustawione, moduł pomija wysyłkę. Niepełna konfiguracja lub błąd wysyłki powoduje niepowodzenie workflow.

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

### Osobny bezpłatny nadawca: AgentMail

Według dokumentacji sprawdzonej 15 września 2026 r. plan Free obejmuje 3 skrzynki w domenie `agentmail.to`, 3000 wiadomości miesięcznie i 100 dziennie, bez karty płatniczej. Konto wymaga jednorazowej rejestracji i weryfikacji; nie wymaga hasła do Gmaila ani dostępu do prywatnej skrzynki. Wiadomości w planie Free mają stopkę „Sent via AgentMail”.

1. Utwórz konto w [AgentMail Console](https://console.agentmail.to/) i osobną skrzynkę nadawczą.
2. Utwórz klucz API AgentMail.
3. W `Settings → Secrets and variables → Actions → Secrets` ustaw:

| Sekret | Wartość |
| --- | --- |
| `KRS_EMAIL_SMTP_HOST` | `smtp.agentmail.to` |
| `KRS_EMAIL_SMTP_PORT` | `587` |
| `KRS_EMAIL_USERNAME` | Adres utworzonej skrzynki `…@agentmail.to` |
| `KRS_EMAIL_FROM` | Ten sam adres skrzynki AgentMail |
| `AGENTMAIL` | Klucz API AgentMail (można także użyć `KRS_EMAIL_PASSWORD`, który ma pierwszeństwo) |
| `KRS_EMAIL_TO` | Docelowe adresy odbiorców oddzielone przecinkiem |

STARTTLS i weryfikacja certyfikatu są włączone domyślnie. Nie umieszczaj klucza API ani listy odbiorców w plikach repozytorium. Klucz API wpisz bezpośrednio w GitHub Secrets.

4. Po włączeniu zmian na domyślnej gałęzi uruchom `Actions → KRS Monitor → Run workflow` i sprawdź odbiór pierwszej wiadomości. Kolejne uruchomienia korzystają z istniejącego tygodniowego harmonogramu; GitHub może opóźnić start względem wskazanej godziny.

E-mail zawiera podsumowanie i maksymalnie `KRS_EMAIL_MAX_DETAILS` zmian, a pełne dane są w załącznikach `report.md` i `comparison.csv`. CSV jest dołączany bez zmiany bajtów, z zachowaniem UTF-8 BOM dla polskich znaków w Excelu. Limit wiadomości SMTP AgentMail to 10 MB. Ręczne ponowienie workflow może wysłać kolejną wiadomość; po niejednoznacznym błędzie wysyłki sprawdź odbiór przed ponowieniem.

Źródła: [cennik](https://www.agentmail.to/pricing), [utworzenie skrzynki](https://docs.agentmail.to/quickstart), [konfiguracja SMTP](https://docs.agentmail.to/imap-smtp), [stopka planu Free](https://docs.agentmail.to/messages).
