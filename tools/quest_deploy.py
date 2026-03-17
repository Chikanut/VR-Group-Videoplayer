"""
Quest Deploy Manager v1.0
─────────────────────────
Масове розгортання додатків (APK) та файлів на підключені Oculus Quest
через ADB. Зберігає конфігурацію в JSON.

Можливості:
  • Автоматичне виявлення всіх підключених Quest
  • Встановлення APK (пропускає якщо вже встановлений)
  • Копіювання файлів (пропускає якщо вже існує і розмір збігається)
  • Реальний прогрес копіювання (fallback на розрахунок по розміру)
  • JSON конфіг для списку файлів, APK, та налаштувань
  • Логування всіх операцій

Вимоги:
  1. ADB (platform-tools): https://developer.android.com/tools/releases/platform-tools
  2. Developer Mode увімкнений на кожному Quest
  3. Quest підключені USB і дозволили USB Debugging

Конфігурація: quest_deploy_config.json (створюється автоматично)
"""

import json
import os
import re
import subprocess
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, scrolledtext
from threading import Thread, Event
from datetime import datetime
from pathlib import Path

# ═══════════════════════════════════════════════════════════
#  Константи
# ═══════════════════════════════════════════════════════════

SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(sys.argv[0])))
CONFIG_FILE = SCRIPT_DIR / "quest_deploy_config.json"
LOG_FILE = SCRIPT_DIR / "quest_deploy.log"

DEFAULT_CONFIG = {
    "adb_path": "adb",
    "files": [],       # [{"src": "C:/path/file.mp4", "dst": "/sdcard/Movies/"}, ...]
    "apks": [],         # ["C:/path/app.apk", ...]
    "devices": {},      # {"SERIAL": {"name": "Quest 3", "last_seen": "..."}}
}


# ═══════════════════════════════════════════════════════════
#  ADB обгортка
# ═══════════════════════════════════════════════════════════

class ADB:
    def __init__(self, adb_path="adb"):
        self.adb_path = adb_path

    def run(self, *args, serial=None, timeout=30):
        """Запуск ADB команди. Повертає (code, stdout, stderr)."""
        cmd = [self.adb_path]
        if serial:
            cmd += ["-s", serial]
        cmd += list(args)
        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            )
            return r.returncode, r.stdout.strip(), r.stderr.strip()
        except FileNotFoundError:
            return -1, "", "ADB не знайдено"
        except subprocess.TimeoutExpired:
            return -1, "", "Таймаут"

    def get_devices(self):
        """Повертає список (serial, status) підключених пристроїв."""
        code, out, err = self.run("devices")
        if code != 0:
            return []
        devices = []
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                devices.append(parts[0])
        return devices

    def get_model(self, serial):
        _, model, _ = self.run("shell", "getprop", "ro.product.model", serial=serial)
        return model or "Unknown"

    def get_android_version(self, serial):
        _, ver, _ = self.run("shell", "getprop", "ro.build.version.release", serial=serial)
        return ver or "?"

    def is_package_installed(self, serial, package_name):
        """Перевіряє чи APK з даним package_name встановлений."""
        code, out, _ = self.run("shell", "pm", "list", "packages", package_name, serial=serial)
        # pm list packages повертає рядки "package:com.example.app"
        return f"package:{package_name}" in out

    def get_package_name_from_apk(self, apk_path):
        """Витягує package name з APK через aapt2/aapt або adb shell."""
        # Спробуємо через aapt2 dump (якщо є в platform-tools)
        aapt_path = os.path.join(os.path.dirname(self.adb_path), "aapt2")
        if os.name == "nt":
            aapt_path += ".exe"

        if os.path.exists(aapt_path):
            try:
                r = subprocess.run(
                    [aapt_path, "dump", "packagename", apk_path],
                    capture_output=True, text=True, timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                )
                if r.returncode == 0 and r.stdout.strip():
                    return r.stdout.strip()
            except Exception:
                pass

        # Fallback: aapt dump badging
        aapt1_path = os.path.join(os.path.dirname(self.adb_path), "aapt")
        if os.name == "nt":
            aapt1_path += ".exe"

        for tool in [aapt1_path, "aapt2", "aapt"]:
            try:
                r = subprocess.run(
                    [tool, "dump", "badging", apk_path],
                    capture_output=True, text=True, timeout=15,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                )
                m = re.search(r"package:\s*name='([^']+)'", r.stdout)
                if m:
                    return m.group(1)
            except Exception:
                continue

        return None

    def remote_file_size(self, serial, remote_path):
        """Повертає розмір файлу на пристрої або -1."""
        code, out, _ = self.run("shell", "stat", "-c", "%s", remote_path, serial=serial)
        if code == 0 and out.strip().isdigit():
            return int(out.strip())
        # Альтернатива: wc -c
        code, out, _ = self.run("shell", "wc", "-c", f'"{remote_path}"', serial=serial)
        if code == 0:
            parts = out.strip().split()
            if parts and parts[0].isdigit():
                return int(parts[0])
        return -1

    def push_with_progress(self, serial, local_path, remote_path, callback=None):
        """
        adb push з відстеженням прогресу.

        callback(pct: int, speed: str, status: str) — викликається при оновленні.

        Стратегія прогресу:
          1) Парсимо stderr adb push на предмет [ XX%]
          2) Якщо adb не дає %, робимо fallback: опитуємо розмір файлу
             на пристрої кожні 2 секунди і рахуємо % самостійно.
        """
        local_size = os.path.getsize(local_path)
        cmd = [self.adb_path, "-s", serial, "push", local_path, remote_path]

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        )

        progress_re = re.compile(r'\[\s*(\d+)%\]')
        speed_re = re.compile(r'([\d.]+\s*[MKG]B/s)')
        got_adb_progress = False
        last_pct = 0

        # Fallback: потік який опитує розмір файлу на пристрої
        fallback_stop = Event()

        def fallback_progress():
            """Опитуємо розмір скопійованого файлу на пристрої."""
            time.sleep(3)  # Даємо adb час почати
            remote_file = remote_path
            if remote_path.endswith("/"):
                remote_file = remote_path + os.path.basename(local_path)

            while not fallback_stop.is_set():
                if got_adb_progress:
                    return  # adb сам дає прогрес, fallback не потрібен

                # Перевіряємо тимчасовий файл (adb пише в .tmp іноді)
                for suffix in ["", ".tmp"]:
                    size = self.remote_file_size(serial, remote_file + suffix)
                    if size > 0:
                        pct = min(int(size * 100 / local_size), 99)
                        speed_est = f"~{size / 1024 / 1024:.0f}/{local_size / 1024 / 1024:.0f} МБ"
                        if callback:
                            callback(pct, speed_est, "copying")
                        break

                fallback_stop.wait(2.5)

        fallback_thread = Thread(target=fallback_progress, daemon=True)
        fallback_thread.start()

        # Читаємо stderr adb push посимвольно
        line_buf = ""
        try:
            while True:
                ch = proc.stderr.read(1)
                if not ch:
                    break
                ch = ch.decode("utf-8", errors="replace")

                if ch in ("\r", "\n"):
                    if line_buf.strip():
                        m_pct = progress_re.search(line_buf)
                        m_spd = speed_re.search(line_buf)
                        if m_pct:
                            got_adb_progress = True
                            pct = int(m_pct.group(1))
                            last_pct = pct
                            spd = m_spd.group(1) if m_spd else ""
                            if callback:
                                callback(pct, spd, "copying")
                    line_buf = ""
                else:
                    line_buf += ch
        except Exception:
            pass

        # Фінальний рядок
        if line_buf.strip():
            m_pct = progress_re.search(line_buf)
            m_spd = speed_re.search(line_buf)
            if m_pct:
                got_adb_progress = True
                pct = int(m_pct.group(1))
                spd = m_spd.group(1) if m_spd else ""
                if callback:
                    callback(pct, spd, "copying")

        fallback_stop.set()
        proc.wait()

        stdout_text = proc.stdout.read().decode("utf-8", errors="replace") if proc.stdout else ""
        return proc.returncode, stdout_text, line_buf

    def install_apk(self, serial, apk_path, callback=None):
        """adb install з прогресом (indeterminate — install не дає %)."""
        if callback:
            callback(-1, "", "installing")

        code, out, err = self.run("install", "-r", "-g", apk_path, serial=serial, timeout=300)
        return code, out, err

    def trigger_media_scan(self, serial, file_path):
        """Оновити медіа-бібліотеку Quest."""
        self.run("shell", "am", "broadcast",
                 "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
                 "-d", f"file://{file_path}", serial=serial, timeout=10)
        folder = os.path.dirname(file_path)
        self.run("shell", "am", "broadcast",
                 "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
                 "-d", f"file://{folder}", serial=serial, timeout=10)
        self.run("shell", "content", "call",
                 "--uri", "content://media",
                 "--method", "scan_volume",
                 "--arg", "external_primary", serial=serial, timeout=15)


# ═══════════════════════════════════════════════════════════
#  Конфіг
# ═══════════════════════════════════════════════════════════

def load_config():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            # Міграція старих конфігів
            for key in DEFAULT_CONFIG:
                if key not in cfg:
                    cfg[key] = DEFAULT_CONFIG[key]
            return cfg
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════
#  GUI
# ═══════════════════════════════════════════════════════════

class QuestDeployApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Quest Deploy Manager")
        self.root.geometry("820x720")
        self.root.minsize(780, 650)

        self.config = load_config()
        self.adb = ADB(self.config.get("adb_path", "adb"))
        self.deploying = False
        self.deploy_cancel = Event()

        self._build_ui()
        self.refresh_devices()
        self.refresh_lists()

    # ── UI ────────────────────────────────────────────────

    def _build_ui(self):
        style = ttk.Style()
        style.configure("Header.TLabel", font=("Segoe UI", 11, "bold"))
        style.configure("Log.TLabel", font=("Consolas", 9))

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=6, pady=6)

        # ── Вкладка: Пристрої ────────────────────────────
        tab_devices = ttk.Frame(notebook, padding=8)
        notebook.add(tab_devices, text="  Пристрої  ")

        ttk.Label(tab_devices, text="Підключені Quest", style="Header.TLabel").pack(anchor="w")

        frame_dev = ttk.Frame(tab_devices)
        frame_dev.pack(fill="both", expand=True, pady=5)

        cols = ("serial", "model", "android", "status")
        self.dev_tree = ttk.Treeview(frame_dev, columns=cols, show="headings", height=6)
        self.dev_tree.heading("serial", text="Serial")
        self.dev_tree.heading("model", text="Модель")
        self.dev_tree.heading("android", text="Android")
        self.dev_tree.heading("status", text="Статус")
        self.dev_tree.column("serial", width=200)
        self.dev_tree.column("model", width=180)
        self.dev_tree.column("android", width=80)
        self.dev_tree.column("status", width=200)
        self.dev_tree.pack(side="left", fill="both", expand=True)

        sb = ttk.Scrollbar(frame_dev, orient="vertical", command=self.dev_tree.yview)
        sb.pack(side="right", fill="y")
        self.dev_tree.configure(yscrollcommand=sb.set)

        frame_dev_btn = ttk.Frame(tab_devices)
        frame_dev_btn.pack(fill="x", pady=5)
        ttk.Button(frame_dev_btn, text="Оновити", command=self.refresh_devices).pack(side="left", padx=3)
        ttk.Button(frame_dev_btn, text="Вибрати всі", command=self.select_all_devices).pack(side="left", padx=3)

        # ── Вкладка: Файли ───────────────────────────────
        tab_files = ttk.Frame(notebook, padding=8)
        notebook.add(tab_files, text="  Файли  ")

        ttk.Label(tab_files, text="Файли для копіювання на Quest", style="Header.TLabel").pack(anchor="w")

        frame_files = ttk.Frame(tab_files)
        frame_files.pack(fill="both", expand=True, pady=5)

        cols_f = ("src", "dst", "size")
        self.file_tree = ttk.Treeview(frame_files, columns=cols_f, show="headings", height=8)
        self.file_tree.heading("src", text="Файл на ПК")
        self.file_tree.heading("dst", text="Папка на Quest")
        self.file_tree.heading("size", text="Розмір")
        self.file_tree.column("src", width=350)
        self.file_tree.column("dst", width=250)
        self.file_tree.column("size", width=80)
        self.file_tree.pack(side="left", fill="both", expand=True)

        sb_f = ttk.Scrollbar(frame_files, orient="vertical", command=self.file_tree.yview)
        sb_f.pack(side="right", fill="y")
        self.file_tree.configure(yscrollcommand=sb_f.set)

        frame_file_btn = ttk.Frame(tab_files)
        frame_file_btn.pack(fill="x", pady=5)
        ttk.Button(frame_file_btn, text="Додати файл…", command=self.add_file).pack(side="left", padx=3)
        ttk.Button(frame_file_btn, text="Додати папку…", command=self.add_folder).pack(side="left", padx=3)
        ttk.Button(frame_file_btn, text="Видалити вибране", command=self.remove_file).pack(side="left", padx=3)

        # ── Вкладка: Додатки (APK) ──────────────────────
        tab_apks = ttk.Frame(notebook, padding=8)
        notebook.add(tab_apks, text="  Додатки (APK)  ")

        ttk.Label(tab_apks, text="APK для встановлення", style="Header.TLabel").pack(anchor="w")

        frame_apks = ttk.Frame(tab_apks)
        frame_apks.pack(fill="both", expand=True, pady=5)

        cols_a = ("path", "package", "size")
        self.apk_tree = ttk.Treeview(frame_apks, columns=cols_a, show="headings", height=8)
        self.apk_tree.heading("path", text="APK файл")
        self.apk_tree.heading("package", text="Package name")
        self.apk_tree.heading("size", text="Розмір")
        self.apk_tree.column("path", width=350)
        self.apk_tree.column("package", width=250)
        self.apk_tree.column("size", width=80)
        self.apk_tree.pack(side="left", fill="both", expand=True)

        sb_a = ttk.Scrollbar(frame_apks, orient="vertical", command=self.apk_tree.yview)
        sb_a.pack(side="right", fill="y")
        self.apk_tree.configure(yscrollcommand=sb_a.set)

        frame_apk_btn = ttk.Frame(tab_apks)
        frame_apk_btn.pack(fill="x", pady=5)
        ttk.Button(frame_apk_btn, text="Додати APK…", command=self.add_apk).pack(side="left", padx=3)
        ttk.Button(frame_apk_btn, text="Видалити вибране", command=self.remove_apk).pack(side="left", padx=3)

        # ── Вкладка: Налаштування ────────────────────────
        tab_settings = ttk.Frame(notebook, padding=8)
        notebook.add(tab_settings, text="  Налаштування  ")

        ttk.Label(tab_settings, text="Шлях до ADB:", style="Header.TLabel").pack(anchor="w", pady=(0, 5))
        frame_adb = ttk.Frame(tab_settings)
        frame_adb.pack(fill="x", pady=5)
        self.adb_path_var = tk.StringVar(value=self.config.get("adb_path", "adb"))
        ttk.Entry(frame_adb, textvariable=self.adb_path_var, width=60).pack(side="left", padx=(0, 5))
        ttk.Button(frame_adb, text="Огляд…", command=self.browse_adb).pack(side="left")
        ttk.Button(frame_adb, text="Зберегти", command=self.save_adb_path).pack(side="left", padx=5)

        ttk.Separator(tab_settings, orient="horizontal").pack(fill="x", pady=15)

        ttk.Label(tab_settings, text="Конфіг:", style="Header.TLabel").pack(anchor="w")
        ttk.Label(tab_settings, text=str(CONFIG_FILE)).pack(anchor="w", pady=3)
        frame_cfg_btn = ttk.Frame(tab_settings)
        frame_cfg_btn.pack(anchor="w", pady=5)
        ttk.Button(frame_cfg_btn, text="Відкрити конфіг", command=self.open_config).pack(side="left", padx=3)
        ttk.Button(frame_cfg_btn, text="Перезавантажити конфіг", command=self.reload_config).pack(side="left", padx=3)

        # ── Нижня панель: прогрес і лог ──────────────────
        frame_bottom = ttk.Frame(self.root, padding=6)
        frame_bottom.pack(fill="x", side="bottom")

        # Прогрес
        frame_prog = ttk.Frame(frame_bottom)
        frame_prog.pack(fill="x", pady=(0, 5))

        self.overall_label = tk.StringVar(value="Готово")
        ttk.Label(frame_prog, textvariable=self.overall_label).pack(anchor="w")

        self.overall_progress = ttk.Progressbar(frame_prog, mode="determinate", maximum=100)
        self.overall_progress.pack(fill="x", pady=2)

        self.current_label = tk.StringVar(value="")
        ttk.Label(frame_prog, textvariable=self.current_label).pack(anchor="w")

        self.current_progress = ttk.Progressbar(frame_prog, mode="determinate", maximum=100)
        self.current_progress.pack(fill="x", pady=2)

        # Кнопки Deploy
        frame_deploy = ttk.Frame(frame_bottom)
        frame_deploy.pack(fill="x", pady=5)

        self.deploy_btn = ttk.Button(frame_deploy, text="▶  Розгорнути на вибрані Quest",
                                     command=self.start_deploy)
        self.deploy_btn.pack(side="left", padx=3)

        self.cancel_btn = ttk.Button(frame_deploy, text="Скасувати", command=self.cancel_deploy,
                                     state="disabled")
        self.cancel_btn.pack(side="left", padx=3)

        # Лог
        self.log_text = scrolledtext.ScrolledText(frame_bottom, height=8, font=("Consolas", 9),
                                                   state="disabled", wrap="word")
        self.log_text.pack(fill="x", pady=3)

    # ── Лог ───────────────────────────────────────────────

    def log(self, msg, tag=None):
        ts = datetime.now().strftime("%H:%M:%S")
        full = f"[{ts}] {msg}"

        def _append():
            self.log_text.config(state="normal")
            self.log_text.insert("end", full + "\n")
            self.log_text.see("end")
            self.log_text.config(state="disabled")

        self.root.after(0, _append)

        # Також у файл
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(full + "\n")
        except Exception:
            pass

    # ── Пристрої ──────────────────────────────────────────

    def refresh_devices(self):
        def _refresh():
            self.log("Пошук підключених пристроїв…")
            serials = self.adb.get_devices()

            devices_info = []
            for s in serials:
                model = self.adb.get_model(s)
                android = self.adb.get_android_version(s)
                devices_info.append((s, model, android))

                # Зберігаємо в конфіг
                self.config.setdefault("devices", {})[s] = {
                    "name": model,
                    "last_seen": datetime.now().isoformat()
                }

            save_config(self.config)

            def _update():
                for item in self.dev_tree.get_children():
                    self.dev_tree.delete(item)
                for s, model, android in devices_info:
                    self.dev_tree.insert("", "end", iid=s,
                                        values=(s, model, android, "Готовий"))
                self.log(f"Знайдено пристроїв: {len(devices_info)}")

            self.root.after(0, _update)

        Thread(target=_refresh, daemon=True).start()

    def select_all_devices(self):
        for item in self.dev_tree.get_children():
            self.dev_tree.selection_add(item)

    def get_selected_devices(self):
        return list(self.dev_tree.selection())

    # ── Файли ─────────────────────────────────────────────

    def add_file(self):
        paths = filedialog.askopenfilenames(title="Оберіть файли")
        if not paths:
            return

        for p in paths:
            dst = self._ask_quest_path()
            if not dst:
                return
            self.config["files"].append({"src": p, "dst": dst})

        save_config(self.config)
        self.refresh_lists()

    def add_folder(self):
        """Додати всі файли з папки."""
        folder = filedialog.askdirectory(title="Оберіть папку з файлами")
        if not folder:
            return
        dst = self._ask_quest_path()
        if not dst:
            return

        for f in os.listdir(folder):
            fp = os.path.join(folder, f)
            if os.path.isfile(fp):
                self.config["files"].append({"src": fp, "dst": dst})

        save_config(self.config)
        self.refresh_lists()

    def _ask_quest_path(self):
        """Діалог введення шляху на Quest."""
        win = tk.Toplevel(self.root)
        win.title("Папка на Quest")
        win.geometry("450x200")
        win.grab_set()

        ttk.Label(win, text="Вкажіть папку призначення на Quest:").pack(pady=10)

        var = tk.StringVar(value="/sdcard/Download/")
        ttk.Entry(win, textvariable=var, width=50).pack(padx=20)

        # Пресети
        frame_p = ttk.Frame(win)
        frame_p.pack(pady=10)
        for name, path in [("Download", "/sdcard/Download/"), ("Movies", "/sdcard/Movies/"),
                           ("Music", "/sdcard/Music/"), ("Pictures", "/sdcard/Pictures/"),
                           ("Oculus", "/sdcard/Oculus/")]:
            ttk.Button(frame_p, text=name, command=lambda p=path: var.set(p)).pack(side="left", padx=2)

        result = [None]

        def ok():
            result[0] = var.get().strip()
            win.destroy()

        ttk.Button(win, text="OK", command=ok).pack(pady=10)
        win.wait_window()
        return result[0]

    def remove_file(self):
        sel = self.file_tree.selection()
        if not sel:
            return
        indices = sorted([int(s) for s in sel], reverse=True)
        for i in indices:
            if 0 <= i < len(self.config["files"]):
                self.config["files"].pop(i)
        save_config(self.config)
        self.refresh_lists()

    # ── APK ───────────────────────────────────────────────

    def add_apk(self):
        paths = filedialog.askopenfilenames(
            title="Оберіть APK файли",
            filetypes=[("APK файли", "*.apk"), ("Всі файли", "*.*")]
        )
        if not paths:
            return
        for p in paths:
            if p not in self.config["apks"]:
                self.config["apks"].append(p)
        save_config(self.config)
        self.refresh_lists()

    def remove_apk(self):
        sel = self.apk_tree.selection()
        if not sel:
            return
        indices = sorted([int(s) for s in sel], reverse=True)
        for i in indices:
            if 0 <= i < len(self.config["apks"]):
                self.config["apks"].pop(i)
        save_config(self.config)
        self.refresh_lists()

    # ── Оновлення списків ─────────────────────────────────

    def refresh_lists(self):
        # Файли
        for item in self.file_tree.get_children():
            self.file_tree.delete(item)
        for i, f in enumerate(self.config.get("files", [])):
            src = f["src"]
            dst = f["dst"]
            size = ""
            if os.path.exists(src):
                sz = os.path.getsize(src)
                size = f"{sz / 1024 / 1024:.1f} МБ" if sz > 1024 * 1024 else f"{sz / 1024:.0f} КБ"
            self.file_tree.insert("", "end", iid=str(i), values=(src, dst, size))

        # APK
        for item in self.apk_tree.get_children():
            self.apk_tree.delete(item)
        for i, apk_path in enumerate(self.config.get("apks", [])):
            pkg = ""
            size = ""
            if os.path.exists(apk_path):
                sz = os.path.getsize(apk_path)
                size = f"{sz / 1024 / 1024:.1f} МБ"
                pkg = self.adb.get_package_name_from_apk(apk_path) or "?"
            self.apk_tree.insert("", "end", iid=str(i), values=(apk_path, pkg, size))

    # ── Налаштування ──────────────────────────────────────

    def browse_adb(self):
        path = filedialog.askopenfilename(
            title="Знайти adb.exe",
            filetypes=[("ADB", "adb.exe"), ("Всі", "*.*")]
        )
        if path:
            self.adb_path_var.set(path)

    def save_adb_path(self):
        self.config["adb_path"] = self.adb_path_var.get().strip()
        self.adb = ADB(self.config["adb_path"])
        save_config(self.config)
        self.log(f"ADB шлях збережено: {self.config['adb_path']}")
        messagebox.showinfo("Збережено", "Шлях до ADB оновлено.")

    def open_config(self):
        if os.name == "nt":
            os.startfile(str(CONFIG_FILE))
        else:
            subprocess.Popen(["xdg-open", str(CONFIG_FILE)])

    def reload_config(self):
        self.config = load_config()
        self.adb = ADB(self.config.get("adb_path", "adb"))
        self.adb_path_var.set(self.config.get("adb_path", "adb"))
        self.refresh_lists()
        self.log("Конфіг перезавантажено")

    # ═══════════════════════════════════════════════════════
    #  Deploy
    # ═══════════════════════════════════════════════════════

    def start_deploy(self):
        if self.deploying:
            return

        devices = self.get_selected_devices()
        if not devices:
            # Якщо нічого не вибрано — беремо всі
            devices = list(self.dev_tree.get_children())
        if not devices:
            messagebox.showwarning("Увага", "Немає підключених пристроїв.")
            return

        files = self.config.get("files", [])
        apks = self.config.get("apks", [])

        if not files and not apks:
            messagebox.showwarning("Увага", "Додайте файли або APK для розгортання.")
            return

        self.deploying = True
        self.deploy_cancel.clear()
        self.deploy_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")

        Thread(target=self.do_deploy, args=(devices, files, apks), daemon=True).start()

    def cancel_deploy(self):
        self.deploy_cancel.set()
        self.log("Скасування…")

    def do_deploy(self, devices, files, apks):
        total_tasks = len(devices) * (len(files) + len(apks))
        done_tasks = 0

        self.log(f"═══ Початок розгортання: {len(devices)} пристроїв, "
                 f"{len(files)} файлів, {len(apks)} APK ═══")

        for serial in devices:
            if self.deploy_cancel.is_set():
                break

            model = self.config.get("devices", {}).get(serial, {}).get("name", serial)
            self.log(f"── Пристрій: {model} ({serial}) ──")
            self.update_device_status(serial, "Розгортання…")

            # ── Встановлення APK ──
            for apk_path in apks:
                if self.deploy_cancel.is_set():
                    break

                apk_name = os.path.basename(apk_path)

                if not os.path.exists(apk_path):
                    self.log(f"  ✗ APK не знайдено: {apk_path}")
                    done_tasks += 1
                    continue

                # Перевірити чи вже встановлений
                pkg = self.adb.get_package_name_from_apk(apk_path)
                if pkg and self.adb.is_package_installed(serial, pkg):
                    self.log(f"  ⏭ APK вже встановлено: {pkg}")
                    done_tasks += 1
                    self.update_overall(done_tasks, total_tasks)
                    continue

                self.update_current(f"Встановлюю {apk_name}…", -1)
                self.log(f"  ⏳ Встановлюю: {apk_name} ({pkg or '?'})…")

                code, out, err = self.adb.install_apk(serial, apk_path)
                if code == 0 and "Success" in (out + err):
                    self.log(f"  ✓ Встановлено: {apk_name}")
                else:
                    self.log(f"  ✗ Помилка встановлення {apk_name}: {err or out}")

                done_tasks += 1
                self.update_overall(done_tasks, total_tasks)

            # ── Копіювання файлів ──
            for file_entry in files:
                if self.deploy_cancel.is_set():
                    break

                src = file_entry["src"]
                dst = file_entry["dst"]
                filename = os.path.basename(src)

                if not os.path.exists(src):
                    self.log(f"  ✗ Файл не знайдено: {src}")
                    done_tasks += 1
                    continue

                local_size = os.path.getsize(src)
                remote_path = dst.rstrip("/") + "/" + filename

                # Перевірити чи вже існує з таким розміром
                remote_size = self.adb.remote_file_size(serial, remote_path)
                if remote_size == local_size:
                    self.log(f"  ⏭ Файл вже є: {filename} ({local_size / 1024 / 1024:.1f} МБ)")
                    done_tasks += 1
                    self.update_overall(done_tasks, total_tasks)
                    continue

                size_mb = local_size / 1024 / 1024
                self.log(f"  ⏳ Копіюю: {filename} ({size_mb:.1f} МБ) → {dst}")

                def progress_cb(pct, speed, status, fn=filename):
                    if pct >= 0:
                        self.update_current(f"{fn}: {pct}%  {speed}", pct)
                    else:
                        self.update_current(f"{fn}: очікування…", -1)

                code, out, err_line = self.adb.push_with_progress(
                    serial, src, remote_path, callback=progress_cb
                )

                if code == 0:
                    self.log(f"  ✓ Скопійовано: {filename}")
                    # Медіа-скан
                    self.adb.trigger_media_scan(serial, remote_path)
                else:
                    self.log(f"  ✗ Помилка копіювання {filename}: {err_line or out}")

                done_tasks += 1
                self.update_overall(done_tasks, total_tasks)

            if not self.deploy_cancel.is_set():
                self.update_device_status(serial, "✓ Готово")
            else:
                self.update_device_status(serial, "Скасовано")

        status = "Скасовано" if self.deploy_cancel.is_set() else "Завершено"
        self.log(f"═══ {status}: {done_tasks}/{total_tasks} задач ═══")

        self.root.after(0, lambda: (
            self.deploy_btn.config(state="normal"),
            self.cancel_btn.config(state="disabled"),
            self.overall_label.set(status),
            self.current_label.set(""),
            self.current_progress.config(mode="determinate", value=0),
        ))
        self.deploying = False

    # ── UI оновлення з потоку ─────────────────────────────

    def update_overall(self, done, total):
        pct = int(done * 100 / total) if total > 0 else 0
        self.root.after(0, lambda: (
            self.overall_progress.config(value=pct),
            self.overall_label.set(f"Загальний прогрес: {done}/{total} ({pct}%)")
        ))

    def update_current(self, text, pct):
        def _upd():
            self.current_label.set(text)
            if pct < 0:
                self.current_progress.config(mode="indeterminate")
                self.current_progress.start(10)
            else:
                self.current_progress.stop()
                self.current_progress.config(mode="determinate", value=pct)
        self.root.after(0, _upd)

    def update_device_status(self, serial, status):
        def _upd():
            try:
                vals = self.dev_tree.item(serial, "values")
                if vals:
                    self.dev_tree.item(serial, values=(vals[0], vals[1], vals[2], status))
            except Exception:
                pass
        self.root.after(0, _upd)


# ═══════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    root = tk.Tk()
    app = QuestDeployApp(root)
    root.mainloop()
