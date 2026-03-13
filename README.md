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

## Uruchamianie lokalne

### Wymagania
- Windows
- Python 3.11+

### Instalacja
```bash
pip install -r requirements.txt