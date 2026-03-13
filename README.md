# ChatGPT Export Converter v2

Windowsowy program do lokalnego przetwarzania oficjalnego eksportu ChatGPT.

## Co obsługuje

- `conversations.json` — stary format eksportu
- `conversations-000.json`, `conversations-001.json`, ... — nowy format dzielony na wiele plików
- ZIP z oficjalnym eksportem
- rozpakowany folder eksportu
- awaryjnie `chat.html`

## Co generuje

- `per_chat/` — osobny Markdown dla każdej rozmowy
- `bundles/` — większe pliki zbiorcze do NotebookLM / AI
- `index.csv` — indeks rozmów i metadanych
- `stats.md` — statystyki zbioru
- `career_profile_seed.md` — roboczy szkic profilu zawodowego na podstawie heurystyk

## Uruchomienie z Pythona

```bash
py -m pip install -r requirements.txt
py app.py
```

## Budowa EXE

```bat
build_exe.bat
```

Gotowy plik będzie w katalogu `dist/`.

## Uwagi

- Ścieżki z `/` i `\` na Windows są normalne — Python i Windows akceptują oba formaty.
- Dla dużych eksportów najlepiej wskazać cały ZIP albo folder po rozpakowaniu.
- `career_profile_seed.md` jest szkicem roboczym; do finalnego CV użyj własnego promptu analitycznego na plikach z `bundles/`.
