@echo off
setlocal

py -m pip install --upgrade pip
py -m pip install pyinstaller tkinterdnd2

pyinstaller --noconfirm --onefile --windowed --name ChatGPTExportConverter app.py

echo.
echo Gotowe. Plik EXE znajdziesz w folderze dist\ChatGPTExportConverter.exe
pause
