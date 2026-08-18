# GSPN Automation

GSPN iş emri otomasyonu için Windows masaüstü uygulaması.

## Dağıtım sistemi

- Uygulama açılışında `manifest.json` üzerinden yeni sürüm kontrolü yapar.
- Yeni sürüm varsa kullanıcıya güncelleme sorulur.
- Güncelleme kabul edilirse GitHub Release içindeki `GSPN_Otomasyon.exe` indirilir.
- Eski EXE otomatik değiştirilir ve yeni sürüm yeniden açılır.
- `BUILD_RELEASE.bat` tek tuşla sürüm artırma, EXE build, Git push ve GitHub Release oluşturma işlemlerini yapar.

## İlk kurulum

1. Python, Git ve GitHub CLI (`gh`) kurulu olmalı.
2. `gh auth login` ile GitHub hesabında oturum açılmalı.
3. Repoyu bilgisayara klonlayın.
4. `python -m pip install -r requirements.txt`
5. İlk EXE/Release için `BUILD_RELEASE.bat` çalıştırın.

## Stabil taban

GUI V2.2 stabil akış temel alınmıştır.
