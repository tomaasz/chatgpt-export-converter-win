# Instrukcja: automatyczny build EXE i Release na GitHub

Ten projekt ma workflow GitHub Actions, który po wypchnięciu taga `v*`:

- buduje plik `ChatGPTExportConverter.exe`,
- tworzy / aktualizuje Release na GitHub,
- dodaje EXE jako asset do release.

## 1. Dodaj plik workflow do repozytorium

Skopiuj plik:

```text
.github/workflows/build-release.yml
```

następnie wykonaj:

```powershell
git add .github/workflows/build-release.yml
Git commit -m "Add GitHub Actions release workflow"
git push
```

> Uwaga: jeśli wpiszesz przez pomyłkę `Git commit` zamiast `git commit`, PowerShell zwykle i tak zadziała, ale trzymaj się małych liter.

## 2. Jak wypuszczać nową wersję

Po każdej zmianie w projekcie:

```powershell
git add .
git commit -m "Opis zmian"
git push
```

Następnie utwórz tag wersji:

```powershell
git tag v1.1
git push origin v1.1
```

Dla kolejnych wersji:

```powershell
git tag v1.2
git push origin v1.2
```

## 3. Co stanie się automatycznie

Po wypchnięciu taga GitHub Actions:

1. uruchomi workflow na Windows,
2. zainstaluje zależności,
3. zbuduje:

```text
dist/ChatGPTExportConverter.exe
```

4. doda plik EXE do release przypiętego do taga.

## 4. Gdzie to sprawdzisz

- zakładka `Actions` — postęp buildu,
- zakładka `Releases` — gotowy release z EXE.

Repozytorium:

```text
https://github.com/tomaasz/chatgpt-export-converter-win
```

## 5. Pierwsze uruchomienie dla obecnego repo

Ponieważ masz już `v1.0`, najczyściej będzie zrobić kolejną wersję:

```powershell
git add .
git commit -m "Add automated release workflow"
git push
git tag v1.1
git push origin v1.1
```

## 6. Jeśli release się nie pojawi

Sprawdź:

- czy plik jest dokładnie w ścieżce:

```text
.github/workflows/build-release.yml
```

- czy `app.py` leży w katalogu głównym repo,
- czy tag zaczyna się od `v`, np. `v1.1`,
- czy workflow ma uprawnienie `contents: write`.

## 7. Jak poprawić workflow po zmianach

Jeśli edytujesz workflow:

```powershell
git add .github/workflows/build-release.yml
git commit -m "Update release workflow"
git push
```

Potem wypuść nowy tag:

```powershell
git tag v1.2
git push origin v1.2
```

## 8. Opcjonalnie: usunięcie błędnego taga

Jeśli wypchniesz zły tag, możesz usunąć go lokalnie i z GitHuba:

```powershell
git tag -d v1.1
git push origin :refs/tags/v1.1
```

Potem utwórz go ponownie:

```powershell
git tag v1.1
git push origin v1.1
```

## 9. Minimalny codzienny workflow

W praktyce wystarczą Ci te komendy:

```powershell
git add .
git commit -m "Opis zmian"
git push
git tag v1.2
git push origin v1.2
```

I to wszystko — bez ręcznej zmiany nazwy EXE i bez klikania przy release.
