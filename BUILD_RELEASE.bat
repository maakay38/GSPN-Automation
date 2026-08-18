@echo off
setlocal
title GSPN AUTOMATION - BUILD & RELEASE
color 0A
cd /d "%~dp0"

echo ==========================================
echo GSPN BUILD / RELEASE
echo ==========================================

where git >nul 2>nul || (
  echo HATA: Git bulunamadi.
  pause
  exit /b 1
)

where gh >nul 2>nul || (
  echo HATA: GitHub CLI ^(gh^) bulunamadi.
  echo https://cli.github.com/ adresinden kurup gh auth login yapin.
  pause
  exit /b 1
)

python -m pip show pyinstaller >nul 2>nul || (
  echo PyInstaller kuruluyor...
  python -m pip install pyinstaller
)

python version_prompt.py || (
  echo Surum islemi basarisiz.
  pause
  exit /b 1
)

for /f %%i in (version.txt) do set VERSION=%%i
set TAG=v%VERSION%

rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
rmdir /s /q release 2>nul
mkdir release

echo ==========================================
echo EXE BUILD
echo ==========================================

pyinstaller --onefile --noconsole --clean ^
  --name GSPN_Otomasyon ^
  --collect-all selenium ^
  --collect-submodules selenium ^
  --hidden-import selenium.webdriver.chrome.options ^
  --hidden-import selenium.webdriver.chrome.service ^
  --hidden-import selenium.webdriver.common.by ^
  --hidden-import selenium.webdriver.common.keys ^
  --hidden-import selenium.webdriver.support.ui ^
  --hidden-import selenium.webdriver.support.expected_conditions ^
  gspn_gui.py

if not exist dist\GSPN_Otomasyon.exe (
  echo HATA: EXE olusmadi.
  pause
  exit /b 1
)

copy /y dist\GSPN_Otomasyon.exe release\GSPN_Otomasyon.exe >nul

echo ==========================================
echo GIT PUSH
echo ==========================================

git add gspn_gui.py gspn_engine.py auto_update.py manifest.json version.txt version_prompt.py BUILD_RELEASE.bat requirements.txt README.md .gitignore
git commit -m "release %VERSION%"
git push origin main

if errorlevel 1 (
  echo HATA: Git push basarisiz.
  pause
  exit /b 1
)

echo ==========================================
echo GITHUB RELEASE
echo ==========================================

gh release delete %TAG% -y 2>nul
gh release create %TAG% release\GSPN_Otomasyon.exe ^
  --repo maakay38/GSPN-Automation ^
  --title "GSPN Otomasyon %VERSION%" ^
  --notes "GSPN Otomasyon v%VERSION%"

if errorlevel 1 (
  echo HATA: Release olusturulamadi.
  pause
  exit /b 1
)

echo ==========================================
echo TAMAMLANDI
echo Surum: %VERSION%
echo ==========================================
pause
