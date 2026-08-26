# Mail Sorter

Router zgłoszeń pracowniczych oparty na lokalnym modelu językowym. API przyjmuje
wiadomość, agent AI interpretuje jej treść i **wywołaniem narzędzia** przekazuje
sprawę mailem do właściwego działu. Model działa lokalnie.

## Uruchomienie

```bash
docker compose up -d
```

`.env` jest opcjonalny, wszystkie zmienne mają wartości domyślne.

Pierwsze uruchomienie trwa **~5 minut** (~1,5 GB obrazu Ollamy + ~1,9 GB wag
modelu), kolejne kilkadziesiąt sekund. Postęp: `docker compose logs -f ollama-init`.
API startuje dopiero po wczytaniu modelu — pilnuje tego
`depends_on: service_completed_successfully`.

|         |                                     |
| ------- | ----------------------------------- |
| Swagger | http://localhost:8000/api/v1/docs   |
| MailHog | http://localhost:8025               |
| Health  | http://localhost:8000/api/v1/health |

## Przykład

```bash
curl -X POST http://localhost:8000/api/v1/route \
  -H "Content-Type: application/json" \
  -d '{"email": "jan.nowak@example.com", "message": "Nie działa mi komputer, nie chce się włączyć"}'
```

```json
{
  "ticket_id": "a3f9c2e1",
  "department": "help_desk",
  "recipient": "help-desk@example.com",
  "routed_by": "llm"
}
```

Opcjonalne pole `subject` — bez niego temat maila powstaje z treści zgłoszenia.
W MailHogu, w zakładce z nagłówkami, widać `Reply-To` ustawiony na oryginalnego
nadawcę.

## Architektura

```
                    👤 Klient
                 curl / Swagger UI
                        |
                        |  POST /api/v1/route
                        v
   +-----------------------------------------------------+
   |                   docker compose                    |
   |                                                     |
   |   ollama-init ........ 1. pobiera model ------.     |
   |   (jednorazowy job;                           |     |
   |    kończy się i znika)                        v     |
   |          |                                  ollama  |
   |          | 2. dopiero po sukcesie          :11434   |
   |          v                                    ^     |
   |         api  ---- HTTP / function calling ----'     |
   |        :8000                                        |
   |          |                                          |
   |          | SMTP                                     |
   |          v                                          |
   |       mailhog                                       |
   |     :1025 / :8025                                   |
   +-----------------------------------------------------+
```

Trzy kontenery, ale **kod aplikacji jest tylko w jednym**. Ollama i MailHog to komponenty
infrastrukturalne — byłyby osobnymi procesami niezależnie od decyzji architektonicznych.
`ollama-init` nie jest usługą, tylko zadaniem: pobierz wagi, rozgrzej model i zakończ się.
API startuje dopiero po jego powodzeniu, więc nie może wstać bez gotowego modelu.

### Narzędzie przyjmuje dział, nie adres

```python
send_email(department: Department) -> str
```

Model podaje jedną z pięciu wartości enuma. Mapowanie `enum → adres` jest
w `app/domain/departments.py`; `Reply-To`, `From`, temat i ticket id ustawia
aplikacja na podstawie żądania.

w efekcie mail wychodzi wewnątrz wywołania narzędzia, a model nie ma parametru,
w który mógłby wpisać adres. Prompt injection nie ma czego przestawić.

### Rozgraniczenie działów

Lista adresów zawiera dwie nakrywające się pary — `human-resources` vs `kadry`
oraz `it` vs `help-desk`. Bez opisanej polityki model 3B wybiera między nimi
losowo.

| Dział             | Zakres                                                    |
| ----------------- | --------------------------------------------------------- |
| `kadry`           | urlopy, L4, umowy, płace, PIT                             |
| `human_resources` | rekrutacja, onboarding, szkolenia, benefity               |
| `help_desk`       | pierwsza linia: sprzęt użytkownika, hasło, drukarka       |
| `it`              | infrastruktura i uprawnienia: serwery, sieć, VPN, dostępy |
| `other`           | fallback                                                  |

Prompt zawiera dodatkowo reguły dla przypadków pasujących do dwóch działów
naraz — np. „nie mam dostępu do VPN" trafia do IT, mimo że brzmi jak zgłoszenie
do help-desku. Przypadki graniczne są w `eval/cases.yaml`.

### Podział na moduły

Środowisko ma trzy kontenery, ale kod aplikacji jest tylko w kontenerze `api`.
Ollama i MailHog to zależności zewnętrzne, takie jak baza danych.

Wewnątrz aplikacji: `api/` obsługuje HTTP, `agent/` rozmawia z modelem, `mail/`
buduje i wysyła wiadomości, `domain/` trzyma działy i adresy. Moduły nie
importują się nawzajem w poprzek — `api/v1.py` nie zawiera `import httpx` ani
`import smtplib`.

Nie dzieliłem tego na osobne serwisy: przy jednym endpoincie oznaczałoby to
kontrakty HTTP i obsługę błędów sieci między własnymi komponentami.

### Model i agent

`qwen2.5:3b`, konfigurowalny przez `OLLAMA_MODEL`. Wybrany, bo wspiera function
calling (Ollama deklaruje to w `/api/tags`), mieści się w czasie odpowiedzi na
CPU i radzi sobie z polskim. CPU, bo Docker nie ma dostępu do GPU na macOS.

Czasy zmierzone na 6 rdzeniach: pierwsze żądanie ~60 s, kolejne ~12 s. Różnica
bierze się z cache'u prefiksu promptu po stronie Ollamy. Stąd
`llm_timeout_seconds = 180` — przy 120 s pierwsze żądanie na wolniejszej
maszynie mogłoby skończyć się błędem 503.

`temperature=0` i stały `seed` — inaczej to samo zgłoszenie mogłoby trafiać do
różnych działów przy kolejnych uruchomieniach.

`tool_choice="required"` nie jest ustawione. Przy `required` model nie może
odpowiedzieć tekstem, więc pętla agenta nie ma warunku zakończenia i pydantic-ai odrzuca taką konfigurację.
Zamiast tego: instrukcja w prompcie, ponowienie z ostrzejszym poleceniem, a na
końcu wysyłka na `other@` oznaczona jako `routed_by: "fallback"`.

## Bezpieczeństwo

Nie wykrywam prompt injection — ale injection nie będzie miał zadnej mocy.

| Warstwa                        | Realizacja                                                                      |
| ------------------------------ | ------------------------------------------------------------------------------- |
| Enum zamiast adresu            | model wybiera jedną z pięciu wartości                                           |
| Maks. jedna wysyłka na żądanie | licznik w kontekście; kolejne wywołania nie wysyłają                            |
| Limit kroków agenta            | `UsageLimits`, po przekroczeniu fallback                                        |
| Walidacja adresu               | odcięcie znaków sterujących; `EmailMessage` niezależnie odrzuca nagłówki z `\n` |
| Treść jako plain text          | odbiorca nie dostaje niczego wykonywalnego                                      |
| Audytowalność                  | jeden identyfikator w logach, nagłówku maila i odpowiedzi API                   |

## Jakość routingu

Router to funkcja `tekst → dział`, a model jest niedeterministyczny — nie da się
tego sprawdzić asercją. `eval/` mierzy trafność na 26 oznaczonych przypadkach:
oczywistych, granicznych, niechlujnych i próbach prompt injection.

```bash
pip install -r requirements-dev.txt && python eval/run.py
```

## Testy

```bash
pytest              # jednostkowe, bez Dockera
pytest -m e2e       # pełna ścieżka, wymaga środowiska
```

Rozdzielenie jest celowe: `tests/` sprawdza poprawność **deterministyczną**
(`Reply-To`, walidacja, limit wysyłek, fallback, kody błędów), `eval/` — jakość
**probabilistyczną**. Testy jednostkowe nie wołają modelu; atrapy pozwalają
odtworzyć scenariusze, których u prawdziwego modelu nie wywołasz na żądanie:
brak wywołania narzędzia i zapętlenie.

## Ograniczenia PoC

|                                                                 | Docelowo                                              |
| --------------------------------------------------------------- | ----------------------------------------------------- |
| SMTP bez uwierzytelniania i TLS                                 | poświadczenia + `starttls()`                          |
| **Niedostarczony mail przepada** (zostaje wpis ERROR i kod 502) | wzorzec outbox: zapis przed wysyłką, ponawianie w tle |
| Brak autoryzacji i rate limitingu                               | klucz API, limit po nadawcy i IP                      |
| Endpoint synchroniczny (~7 s)                                   | `202 Accepted` + kolejka + worker                     |
| Eval na 26 przypadkach                                          | kilkaset, oznaczonych niezależnie                     |

Świadomie pominięta **orkiestracja grafowa** — uzasadniona przy pętli
doprecyzowania z human-in-the-loop czy eskalacji między działami, ale przy jednym
kroku decyzyjnym to warstwa bez treści.

## Diagnostyka

| Objaw                                                | Przyczyna                                                                                 |
| ---------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `model_ready: false`                                 | pobieranie modelu trwa — `docker compose logs -f ollama-init`                             |
| HTTP 503 / 502                                       | niedostępny model / MailHog                                                               |
| Brak maila mimo 200                                  | sprawdź `routed_by`; przy `fallback` mail poszedł na `other@`                             |
| `Conflict. The container name ... is already in use` | osierocone kontenery z poprzedniego uruchomienia — `docker compose down --remove-orphans` |
