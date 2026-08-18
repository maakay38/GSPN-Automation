import json
import os
import sys
import time
import tempfile
import subprocess
import urllib.request
import tkinter as tk
from tkinter import ttk, messagebox

LATEST_RELEASE_API = "https://api.github.com/repos/maakay38/GSPN-Automation/releases/latest"
EXPECTED_ASSET = "GSPN_Otomasyon.exe"


def _version_tuple(v):
    values = []
    for part in str(v).strip().lstrip("vV").split("."):
        try:
            values.append(int(part))
        except ValueError:
            values.append(0)
    return tuple((values + [0, 0, 0, 0])[:4])


def _github_json(url, timeout=15):
    sep = "&" if "?" in url else "?"
    url = f"{url}{sep}_={int(time.time() * 1000)}"

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "GSPN-Automation-Updater/3.0",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Cache-Control": "no-cache, no-store, max-age=0",
            "Pragma": "no-cache",
        },
    )

    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8-sig"))


def check_for_update(local_version):
    """
    Güncelleme kaynağı sadece GitHub Latest Release API'dir.
    manifest.json sürüm kararı için kullanılmaz.
    """
    last_error = None

    for attempt in range(3):
        try:
            release = _github_json(LATEST_RELEASE_API)

            tag = str(release.get("tag_name", "")).strip()
            remote_version = tag.lstrip("vV")

            if not remote_version:
                raise RuntimeError("Latest Release tag_name boş.")

            download_url = ""
            assets = release.get("assets") or []

            for asset in assets:
                if str(asset.get("name", "")).strip() == EXPECTED_ASSET:
                    download_url = str(asset.get("browser_download_url", "")).strip()
                    break

            if not download_url:
                raise RuntimeError(
                    f"Latest Release içinde {EXPECTED_ASSET} bulunamadı."
                )

            notes = str(release.get("body") or release.get("name") or "").strip()

            if _version_tuple(remote_version) > _version_tuple(local_version):
                return remote_version, download_url, notes

            return None

        except Exception as e:
            last_error = e
            if attempt < 2:
                time.sleep(1)

    raise RuntimeError(f"GitHub Latest Release okunamadı: {last_error}")


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
    win.geometry("440x160")
    win.resizable(False, False)

    ttk.Label(
        win,
        text=f"Yeni sürüm indiriliyor: v{new_version}",
    ).pack(pady=(18, 8))

    progress = ttk.Progressbar(win, length=380, mode="determinate")
    progress.pack(pady=8)

    percent = ttk.Label(win, text="%0")
    percent.pack()

    win.transient(root)
    win.grab_set()
    win.update()

    sep = "&" if "?" in download_url else "?"
    final_url = f"{download_url}{sep}_={int(time.time() * 1000)}"

    req = urllib.request.Request(
        final_url,
        headers={
            "User-Agent": "GSPN-Automation-Updater/3.0",
            "Cache-Control": "no-cache, no-store",
            "Pragma": "no-cache",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as response, open(temp_path, "wb") as f:
            total = int(response.headers.get("Content-Length") or 0)
            received = 0

            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break

                f.write(chunk)
                received += len(chunk)

                if total:
                    pct = min(100, received * 100 / total)
                    progress["value"] = pct
                    percent.configure(text=f"%{pct:.0f}")
                    win.update_idletasks()

        size = os.path.getsize(temp_path)
        if size < 5 * 1024 * 1024:
            raise RuntimeError(
                f"İndirilen EXE beklenenden küçük ({size} byte)."
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

    # PID ile beklemek, aynı isimde başka GSPN EXE süreçlerinin updater'ı kilitlemesini önler.
    current_pid = os.getpid()

    lines = [
        "@echo off",
        "setlocal",
        f'cd /d "{exe_dir}"',
        ":waitpid",
        f'tasklist /FI "PID eq {current_pid}" | find "{current_pid}" >nul',
        "if not errorlevel 1 (",
        "  timeout /t 1 /nobreak >nul",
        "  goto waitpid",
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

    # EXE'nin serbest kalması için süreci tamamen sonlandır.
    root.destroy()
    os._exit(0)
