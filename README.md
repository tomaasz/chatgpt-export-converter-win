# ChatGPT Export Converter for Windows

Narzędzie desktopowe dla Windows do lokalnego przetwarzania oficjalnych eksportów danych z ChatGPT.

## Funkcje

- obsługa nowych eksportów ChatGPT dzielonych na pliki `conversations-000.json`, `conversations-001.json` itd.
- obsługa pojedynczego `conversations.json`
- obsługa ZIP z eksportem
- konwersja rozmów do Markdown
- generowanie paczek do dalszej analizy, np. w NotebookLM
- działanie lokalne, bez wysyłania danych na zewnętrzne serwery

## Jak pobrać eksport z ChatGPT

1. Otwórz [chatgpt.com](https://chatgpt.com)
2. Kliknij ikonę profilu → **Ustawienia**
3. Wybierz **Eksport danych** → **Potwierdź eksport**
4. Poczekaj na e-mail z linkiem do pobrania pliku ZIP

## Wejście

Program przyjmuje:
- ZIP z oficjalnym eksportem ChatGPT
- rozpakowany folder eksportu
- pojedynczy plik `conversations.json`

## Wyjście

Program generuje:
- `per_chat/` – osobne rozmowy w Markdown
- `bundles/` – większe paczki Markdown do analizy
- `index.csv` – indeks rozmów
- `stats.md` – statystyki zbioru
- `career_profile_seed.md` – roboczy szkic profilu zawodowego

## Windows SmartScreen

Przy pierwszym uruchomieniu pliku `.exe` Windows może wyświetlić ostrzeżenie SmartScreen („System Windows ochronił ten komputer"). Jest to normalne zachowanie dla aplikacji bez płatnego certyfikatu podpisu cyfrowego. Aby uruchomić program, kliknij **Więcej informacji** → **Uruchom mimo to**. Aplikacja działa w pełni lokalnie i nie wysyła żadnych danych.

## Uruchamianie lokalne

### Wymagania
- Windows
- Python 3.11+

### Instalacja
```bash
pip install -r requirements.txt

<!-- VERIFIED-PROJECT-OVERVIEW:BEGIN -->
## Opis projektu i technologii

**Cel:** Lokalne przetwarzanie oficjalnych eksportów danych z ChatGPT w aplikacji dla Windows.

**Sprawdzono:** 2026-10-11, na podstawie plików repozytorium z [commitu `398f44ac14`](https://github.com/tomaasz/chatgpt-export-converter-win/commit/398f44ac14d523f7c0033ae4d96dbaeaa4db54e1).
Opis plików nie potwierdza, że aplikacja jest wdrożona, działa bez błędów ani że wszystkie zadeklarowane narzędzia są używane.

### Technologie i narzędzia

- Główny język według GitHuba: **Python**.
- Rozpoznane technologie w wybranych manifestach: Python, pytest.
- Narzędzia zadeklarowane w wybranych plikach: GitHub Actions.

### Wybrane pakiety

| Pakiet | Wymaganie z manifestu | Plik |
|---|---|---|
| pytest | >=9.1.1 | requirements-dev.txt |
| pytest-cov | >=7.1.0 | requirements-dev.txt |
| tkinterdnd2 | >=0.6.3 | requirements.txt |
| google-api-python-client | >=2.201.0 | requirements.txt |
| google-auth-oauthlib | >=1.5.0 | requirements.txt |

To wybrane deklaracje, nie pełna lista i nie wynik pomiaru wersji uruchomionej aplikacji. Pełny wykaz zależności oraz lockfile, jeżeli istnieje, pozostają w repozytorium.

### Skąd pochodzą informacje

- [`README.md`](README.md).
- [`requirements-dev.txt`](requirements-dev.txt).
- [`requirements.txt`](requirements.txt).
- [`.github/workflows/bot-fixer-automerge.yml`](.github/workflows/bot-fixer-automerge.yml).
- [`.github/workflows/build-release.yml`](.github/workflows/build-release.yml).
- [`.github/workflows/ci.yml`](.github/workflows/ci.yml).
- [`.github/workflows/codeql.yml`](.github/workflows/codeql.yml).
- [`.github/workflows/dependabot-automerge.yml`](.github/workflows/dependabot-automerge.yml).
- [`.github/workflows/sonarqube.yml`](.github/workflows/sonarqube.yml).
- [`.github/workflows/stale.yml`](.github/workflows/stale.yml).

### Zakres sprawdzenia

Przegląd obejmuje wybrane pliki gałęzi domyślnej. Nie uruchamiano aplikacji ani nie zmieniano wdrożeń. Limity przeglądu mogą pomijać część modułów; brak pozycji w tym opisie nie dowodzi braku funkcji lub narzędzia.
<!-- VERIFIED-PROJECT-OVERVIEW:END -->
