import json
import os
import sys
import tempfile
import subprocess
import urllib.request
import tkinter as tk
from tkinter import ttk, messagebox

MANIFEST_URL = "https://raw.githubusercontent.com/maakay38/GSPN-Automation/main/manifest.json"

def _version_tuple(v):
    parts = []
    for p in str(v).strip().lstrip("vV").split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts + [0] * (4 - len(parts)))

def check_for_update(local_version):
    req = urllib.request.Request(
        MANIFEST_URL,
        headers={"User-Agent": "GSPN-Automation-Updater"}
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        data = json.loads(r.read().decode("utf-8"))

    remote_version = str(data.get("version", "0.0.0")).strip()
    download_url = str(data.get("download_url", "")).strip()
    notes = str(data.get("notes", "")).strip()

    if not download_url:
        return None

    if _version_tuple(remote_version) > _version_tuple(local_version):
        return remote_version, download_url, notes

    return None

def download_and_install(root, download_url, current_exe_name, new_version):
    if not getattr(sys, "frozen", False):
        messagebox.showinfo(
            "Güncelleme",
            "Otomatik güncelleme EXE sürümünde çalışır.\nPython kaynak sürümü çalıştırılıyor."
        )
        return

    exe_path = os.path.abspath(sys.executable)
    exe_dir = os.path.dirname(exe_path)
    target_name = os.path.basename(exe_path) or current_exe_name

    fd, temp_path = tempfile.mkstemp(prefix="GSPN_new_", suffix=".exe", dir=exe_dir)
    os.close(fd)

    win = tk.Toplevel(root)
    win.title(f"GSPN Güncelleme v{new_version}")
    win.geometry("420x150")
    win.resizable(False, False)
    ttk.Label(win, text=f"Yeni sürüm indiriliyor: v{new_version}").pack(pady=(18, 8))
    pb = ttk.Progressbar(win, length=360, mode="determinate")
    pb.pack(pady=8)
    lbl = ttk.Label(win, text="%0")
    lbl.pack()
    win.grab_set()
    win.update()

    req = urllib.request.Request(
        download_url,
        headers={"User-Agent": "GSPN-Automation-Updater"}
    )
    with urllib.request.urlopen(req, timeout=30) as r, open(temp_path, "wb") as f:
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

    updater_bat = os.path.join(exe_dir, "_gspn_update.bat")
    lines = [
        "@echo off",
        "setlocal",
        f'cd /d "{exe_dir}"',
        "timeout /t 2 /nobreak >nul",
        f'del /f /q "{target_name}.old" 2>nul',
        f'move /y "{target_name}" "{target_name}.old" >nul',
        f'move /y "{os.path.basename(temp_path)}" "{target_name}" >nul',
        f'start "" "{target_name}"',
        "timeout /t 2 /nobreak >nul",
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

    root.destroy()
    sys.exit(0)
