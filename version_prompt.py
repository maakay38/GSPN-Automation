from pathlib import Path
import re
import json

version_file = Path("version.txt")
manifest_file = Path("manifest.json")
gui_file = Path("gspn_gui.py")

old = version_file.read_text(encoding="utf-8").strip() if version_file.exists() else "2.2.0"
print(f"Mevcut sürüm: {old}")
new = input("Yeni sürüm (örn 2.3.0): ").strip()

if not re.fullmatch(r"\d+\.\d+\.\d+", new):
    print("HATA: Sürüm x.y.z formatında olmalı.")
    raise SystemExit(1)

version_file.write_text(new + "\n", encoding="utf-8")

manifest = {
    "version": new,
    "download_url": "https://github.com/maakay38/GSPN-Automation/releases/latest/download/GSPN_Otomasyon.exe",
    "notes": f"GSPN Otomasyon v{new}"
}
manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

text = gui_file.read_text(encoding="utf-8")
text = re.sub(r'APP_VERSION = "[^"]+"', f'APP_VERSION = "{new}"', text)
gui_file.write_text(text, encoding="utf-8")

print(f"Sürüm güncellendi: {new}")
