import json
import os
import sys
import time
import tempfile
import subprocess
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import ttk, messagebox

RAW_MANIFEST_URL = "https://raw.githubusercontent.com/maakay38/GSPN-Automation/main/manifest.json"
API_MANIFEST_URL = "https://api.github.com/repos/maakay38/GSPN-Automation/contents/manifest.json"

def _version_tuple(v):
    nums = []
    for p in str(v).strip().lstrip("vV").split("."):
        try:
            nums.append(int(p))
        except ValueError:
            nums.append(0)
    return tuple((nums + [0, 0, 0, 0])[:4])

def _request_json(url, timeout=10):
    sep = "&" if "?" in url else "?"
    url = f"{url}{sep}_={int(time.time() * 1000)}"

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "GSPN-Automation-Updater/2",
            "Accept": "application/vnd.github+json, application/json, text/plain, */*",
            "Cache-Control": "no-cache, no-store, max-age=0",
            "Pragma": "no-cache",
        },
    )

    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8-sig")

def _load_manifest():
    errors = []

    # 1. GitHub RAW
    for attempt in range(2):
        try:
            return json.loads(_request_json(RAW_MANIFEST_URL))
        except Exception as e:
            errors.append(f"RAW[{attempt+1}]: {e}")
            time.sleep(0.5)

    # 2. GitHub Contents API fallback
    try:
        api_data = json.loads(_request_json(API_MANIFEST_URL))
        import base64
        raw = base64.b64decode(api_data["content"]).decode("utf-8-sig")
        return json.loads(raw)
    except Exception as e:
        errors.append(f"API: {e}")

    raise RuntimeError(" | ".join(errors))

def check_for_update(local_version):
    data = _load_manifest()

    remote_version = str(data.get("version", "0.0.0")).strip()
    download_url = str(data.get("download_url", "")).strip()
    notes = str(data.get("notes", "")).strip()

    if not download_url:
        raise RuntimeError("manifest.json içinde download_url boş.")

    if _version_tuple(remote_version) > _version_tuple(local_version):
        return remote_version, download_url, notes

    return None

def download_and_install(root, download_url, current_exe_name, new_version):
    if not getattr(sys, "frozen", False):
        messagebox.showinfo(
            "Güncelleme",
            "Otomatik güncelleme yalnız EXE sürümünde çalışır."
        )
        return

    exe_path = os.path.abspath(sys.executable)
    exe_dir = os.path.dirname(exe_path)
    target_name = os.path.basename(exe_path) or current_exe_name

    fd, temp_path = tempfile.mkstemp(
        prefix="GSPN_new_",
        suffix=".exe",
        dir=exe_dir,
    )
    os.close(fd)

    win = tk.Toplevel(root)
    win.title(f"GSPN Güncelleme v{new_version}")
    win.geometry("430x150")
    win.resizable(False, False)

    ttk.Label(
        win,
        text=f"Yeni sürüm indiriliyor: v{new_version}"
    ).pack(pady=(18, 8))

    pb = ttk.Progressbar(win, length=370, mode="determinate")
    pb.pack(pady=8)

    lbl = ttk.Label(win, text="%0")
    lbl.pack()

    win.transient(root)
    win.grab_set()
    win.update()

    sep = "&" if "?" in download_url else "?"
    final_url = f"{download_url}{sep}_={int(time.time() * 1000)}"

    req = urllib.request.Request(
        final_url,
        headers={
            "User-Agent": "GSPN-Automation-Updater/2",
            "Cache-Control": "no-cache, no-store",
            "Pragma": "no-cache",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=90) as r, open(temp_path, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0

            while True:
                chunk = r.read(1024 * 256)
                if not chunk:
                    break

                f.write(chunk)
                done += len(chunk)

                if total:
                    pct = min(100, done * 100 / total)
                    pb["value"] = pct
                    lbl.configure(text=f"%{pct:.0f}")
                    win.update_idletasks()

        if os.path.getsize(temp_path) < 1024 * 1024:
            raise RuntimeError(
                "İndirilen EXE beklenenden küçük. Release indirme bağlantısı kontrol edilmeli."
            )

    except Exception:
        try:
            os.remove(temp_path)
        except Exception:
            pass
        try:
            win.destroy()
        except Exception:
            pass
        raise

    updater_bat = os.path.join(exe_dir, "_gspn_update.bat")
    temp_name = os.path.basename(temp_path)

    lines = [
        "@echo off",
        "setlocal",
        f'cd /d "{exe_dir}"',
        ":waitloop",
        f'tasklist /FI "IMAGENAME eq {target_name}" | find /I "{target_name}" >nul',
        "if not errorlevel 1 (",
        "  timeout /t 1 /nobreak >nul",
        "  goto waitloop",
        ")",
        f'del /f /q "{target_name}.old" 2>nul',
        f'move /y "{target_name}" "{target_name}.old" >nul',
        f'move /y "{temp_name}" "{target_name}" >nul',
        f'if not exist "{target_name}" exit /b 2',
        f'start "" "{target_name}"',
        "timeout /t 3 /nobreak >nul",
        f'del /f /q "{target_name}.old" 2>nul',
        'del /f /q "%~f0" 2>nul',
    ]

    with open(updater_bat, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\r\n".join(lines) + "\r\n")

    subprocess.Popen(
        ["cmd.exe", "/c", updater_bat],
        cwd=exe_dir,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )

    try:
        win.destroy()
    except Exception:
        pass

    root.after(100, root.destroy)
