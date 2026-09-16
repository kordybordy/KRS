# KRS Monitor CGI

Projekt automatycznie monitoruje zmiany w danych KRS dla dwóch spółek CGI. Co dwa tygodnie, w czwartek o 09:00 czasu Europe/Warsaw, pobiera pełny odpis KRS, zapisuje snapshot, porównuje go z poprzednią wersją i generuje raport zmian w Markdown, JSON oraz CSV z pełną tabelą porównania wartości. Pierwsza wysyłka w tym harmonogramie przypada 1 października 2026 r.

Monitor wysyła co dwa tygodnie e-mail z wynikiem, zmienionymi wartościami na początku wiadomości oraz załączonym raportem i plikiem CSV. Wiadomość jest wysyłana również wtedy, gdy nie ma zmian, i wskazuje datę oraz odnośnik do ostatniego raportu, w którym wykryto zmiany. Nadawcą może być osobna skrzynka AgentMail, bez połączenia z prywatnym kontem Gmail. Opcjonalne issue na GitHubie nadal powstaje tylko przy wykryciu zmian. Wyniki są też zapisywane w repozytorium, commitowane przez GitHub Actions i publikowane jako artifacts.

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

- `workflow_dispatch` — ręczne uruchomienie respektujące ten sam harmonogram.
- `schedule` — sprawdzenie w każdy czwartek o 09:00 w strefie `Europe/Warsaw`; osobny etap dopuszcza raportowanie wyłącznie co 14 dni od 1 października 2026 r.

Strefa `Europe/Warsaw` zachowuje godzinę 09:00 także po zmianie czasu letniego i zimowego. GitHub może opóźnić uruchomienie względem zaplanowanej godziny. W tygodniach pomijanych kończy się wyłącznie sprawdzenie daty: główne zadanie nie pobiera danych, nie aktualizuje snapshotów, nie wysyła poczty ani nie tworzy issue. Pozwala to porównywać dane z poprzednim raportem wysłanym w dwutygodniowym cyklu.

Workflow:

1. Checkoutuje repozytorium.
2. Ustawia Python 3.12.
3. Instaluje zależności z `requirements.txt`.
4. Uruchamia `pytest`.
5. Uruchamia `python -m krs_monitor.main`.
   Następnie wywołuje moduł powiadomień SMTP dla daty raportu z tego konkretnego uruchomienia. Przy skonfigurowanej poczcie wysyła wynik co dwa tygodnie, także bez zmian. Wiadomość zawiera ostatni raport ze zmianami znaleziony w historii do bieżącej daty włącznie; raport bazowy nie jest traktowany jako wykrycie zmian. Błędy pobrania danych są oznaczane w wiadomości; błąd wysyłki powoduje niepowodzenie workflow.
6. Dopisuje najnowsze `summary.txt` do GitHub Actions job summary.
7. Uploaduje katalog `reports/` jako artifact `krs-report`.
8. Commituje zmienione pliki `data/latest`, `data/archive` i `reports`.
9. Jeżeli wykryto zmiany, tworzy GitHub issue z krótkim podsumowaniem raportu. GitHub wyśle e-mail osobom obserwującym repozytorium lub wymienionym przez GitHub username.

Commit ma format:

```text
krs-monitor: fortnightly report YYYY-MM-DD
```

Jeżeli nie ma zmian, workflow wypisuje:

```text
No changes to commit.
```

i nie kończy się błędem.

## Terminy raportowania

Moduł `src/krs_monitor/schedule.py` dopuszcza daty oddalone o wielokrotność 14 dni od `2026-10-01`, nie wcześniej niż o 09:00 czasu polskiego. Ten sposób liczenia zachowuje rytm także na przełomie roku z 53 tygodniami ISO.

| Data | Wysyłka |
| --- | --- |
| 17.09.2026 | Pominięta — wcześniej wysłano próbę |
| 24.09.2026 | Pominięta |
| 01.10.2026, 09:00 | Pierwszy raport w nowym cyklu |
| 15.10.2026, 09:00 | Kolejny raport |
| 29.10.2026, 09:00 | Kolejny raport, już w czasie zimowym |

Harmonogram można sprawdzić bez pobierania danych i bez wysyłania wiadomości: `PYTHONPATH=src python -m krs_monitor.schedule`.

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

4. `Actions → KRS Monitor → Run workflow` respektuje harmonogram: poza wyznaczonym czwartkiem od 09:00 wykona wyłącznie sprawdzenie terminu. Regularne wysyłki korzystają z dwutygodniowego cyklu opisanego powyżej; GitHub może opóźnić start względem wskazanej godziny.

E-mail zawiera podsumowanie i maksymalnie `KRS_EMAIL_MAX_DETAILS` zmian, a pełne dane są w załącznikach `report.md` i `comparison.csv`. CSV jest dołączany bez zmiany bajtów, z zachowaniem UTF-8 BOM dla polskich znaków w Excelu. Limit wiadomości SMTP AgentMail to 10 MB. Ręczne ponowienie workflow może wysłać kolejną wiadomość; po niejednoznacznym błędzie wysyłki sprawdź odbiór przed ponowieniem.

Źródła: [cennik](https://www.agentmail.to/pricing), [utworzenie skrzynki](https://docs.agentmail.to/quickstart), [konfiguracja SMTP](https://docs.agentmail.to/imap-smtp), [stopka planu Free](https://docs.agentmail.to/messages).
