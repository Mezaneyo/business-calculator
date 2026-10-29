@echo off
REM Run this on a Windows laptop that has Python installed (python.org, tick "Add Python to PATH").
echo Installing tools...
python -m pip install --upgrade pip flask pyinstaller
echo Building the app...
python -m PyInstaller --noconfirm --onefile --name BusinessCalculator --add-data "templates;templates" desktop.py
echo.
echo Done! Your app is here: dist\BusinessCalculator.exe
pause
