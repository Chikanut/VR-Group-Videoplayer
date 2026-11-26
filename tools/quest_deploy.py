"""
Quest Deploy Manager
────────────────────
Масове розгортання додатків (APK) та файлів на підключені Oculus Quest
через ADB. Зберігає конфігурацію в JSON. Інтерфейс — локальна сторінка
(tools/deploy_ui/index.html) в окремому вікні Edge/Chrome, у тому ж вигляді, що й панель керування.

Можливості:
  • Автоматичне виявлення всіх підключених Quest
  • Встановлення APK (пропускає якщо вже встановлений)
  • Копіювання файлів (пропускає якщо вже існує і розмір збігається)
  • Реальний прогрес копіювання (fallback на розрахунок по розміру)
  • JSON конфіг для списку файлів, APK, та налаштувань
  • Логування всіх операцій
  • Відкат окулярів: видалити плеєр і повернути все, що змінювало налаштування
  • Оновлення плеєра і самого менеджера з GitHub Releases

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
import shutil
import tempfile
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Lock, Thread, Timer
from datetime import datetime
from pathlib import Path

# ═══════════════════════════════════════════════════════════
#  Константи
# ═══════════════════════════════════════════════════════════

SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(sys.argv[0])))
CONFIG_FILE = SCRIPT_DIR / "quest_deploy_config.json"
PLAYER_PACKAGE = "com.vrclass.player"
# Перша настройка Meta. На роутері без інтернету вона нескінченно перевіряє portal.fb.com,
# і поки вона відкрита, Quest нічого не показує і блокує запуск будь-яких додатків
# (logcat: "Launch is blocked because: a Reprojected OS dialog is currently showing").
# Окуляри вже налаштовані, тож її можна вимкнути; повернути: adb shell pm enable com.oculus.firsttimenux
META_FIRST_TIME_SETUP = "com.oculus.firsttimenux"
# Підказки Meta (JITEBillboardActivity): без інтернету чекають токен Meta і так само блокують
# запуск (бачили 2026-11-26). Повернути: adb shell pm enable com.oculus.guidebook
META_GUIDE = "com.oculus.guidebook"
# Системні вікна Meta, які вимикаємо: закрити їх може лише adb, не сам плеєр.
META_BLOCKING_DIALOGS = (META_FIRST_TIME_SETUP, META_GUIDE)
# Що робити з автозапуском плеєра під час налаштування (значення лежать у конфігу як є).
AUTOSTART_KEEP, AUTOSTART_ON, AUTOSTART_OFF = "не змінювати", "увімкнути", "вимкнути"
LOG_FILE = SCRIPT_DIR / "quest_deploy.log"
DEPLOY_VERSION = "2.0.0"  # тег релізу GitHub, з яким іде цей exe
PORT = 8765               # сторінка UI: http://127.0.0.1:8765/
GITHUB_LATEST_URL = "https://api.github.com/repos/Chikanut/VR-Group-Videoplayer/releases/latest"
PLAYER_ASSET = "VRClassroomPlayer-Quest.apk"
DEPLOY_ASSET = "QuestDeployManager.exe"

DEFAULT_CONFIG = {
    "adb_path": "adb",
    "files": [],       # [{"src": "C:/path/file.mp4", "dst": "/sdcard/Movies/"}, ...]
    "apks": [],         # ["C:/path/app.apk", ...]
    "devices": {},      # {"SERIAL": {"name": "Quest 3", "last_seen": "..."}}
    "wifi_networks": [], # [{"ssid": "MyWifi", "password": "pass", "security": "wpa2"}]
    "wifi_auto_deploy": False, # застосовувати Wi-Fi перед кожним деплоєм
    "force_reinstall": False,  # видаляти встановлений APK перед встановленням
    "deploy_content": "all",   # all | files | apks
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
        # Спробуємо через aapt2 dump (platform-tools або SDK build-tools)
        exe = ".exe" if os.name == "nt" else ""
        aapt_candidates = [os.path.join(os.path.dirname(self.adb_path), "aapt2" + exe)]
        build_tools = os.path.join(os.path.dirname(os.path.dirname(self.adb_path)), "build-tools")
        if os.path.isdir(build_tools):
            for ver in sorted(os.listdir(build_tools), reverse=True):
                aapt_candidates.append(os.path.join(build_tools, ver, "aapt2" + exe))

        for aapt_path in aapt_candidates:
            if not os.path.exists(aapt_path):
                continue
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

    def setup_player(self, serial, apk_path, package_name, autostart=None):
        """Одноразове налаштування плеєра для автозапуску і тихого самооновлення.

        - плеєр має бути сам собі «інсталятором» (інакше самооновлення питає підтвердження
          в окулярах). `pm set-installer` заборонено, тому перевстановлюємо з `-i`;
        - дозвіл «поверх інших вікон» дає запускати плеєр з фону (сторож після ввімкнення);
        - дозвіл встановлювати APK для самооновлення;
        - WRITE_SECURE_SETTINGS: плеєр сам застосовує системні налаштування, які задає сервер
          (Налаштування → «Системні налаштування окулярів»), тож кабель для них більше не потрібен.
        autostart: True/False вмикає/вимикає автозапуск плеєра сторожем (потім його можна
        перемкнути з сервера), None не чіпає.
        Оновлювач Meta вимкнути не можна: `pm disable-user com.oculus.updater` на Horizon OS v209
        відповідає "Cannot disable a protected package".
        Повертає список помилок (порожній = все добре).
        """
        errors = []
        _, out, _ = self.run("shell", "dumpsys", "package", package_name, serial=serial, timeout=20)
        if f"installerPackageName={package_name}" not in out:
            code, out, err = self.run("install", "-r", "-g", "-i", package_name, apk_path, serial=serial, timeout=300)
            if code != 0 or "Success" not in out + err:
                errors.append(f"install -i: {(err or out).strip()}")
        errors += self.grant_player_permissions(serial, package_name)
        # Роутер без інтернету, що перенаправляє перевірку зв'язку, Quest вважає мережею «з входом»
        # (captive portal). Ставимо одразу по кабелю, щоб діяло ще до першого підключення до
        # сервера (той самий рядок є в його профілі налаштувань). Скасувати:
        # adb shell settings delete global captive_portal_mode
        code, out, err = self.run("shell", "settings", "put", "global", "captive_portal_mode", "0",
                                  serial=serial, timeout=20)
        if code != 0 or (err or out).strip():
            errors.append(f"captive_portal_mode: {(err or out).strip()[:200]}")
        error = self.disable_meta_dialogs(serial)
        if error:
            errors.append(f"вікна Meta: {error}")
        # Стартуємо сторожа: він відкриє плеєр, щойно окуляри вдягнуть (поки вони лежать,
        # Quest не відкриває жодних додатків).
        self.run("shell", "am", "broadcast", "-n", f"{package_name}/.BootReceiver", serial=serial, timeout=20)
        if autostart is not None:
            error = self.set_autostart(serial, autostart)
            if error:
                errors.append(f"автозапуск (потрібен плеєр 1.8.2+): {error}")
        return errors

    def grant_player_permissions(self, serial, package_name):
        """Дозволи плеєра, які видаються лише по кабелю. Повертає список помилок."""
        errors = []
        # MANAGE_EXTERNAL_STORAGE: агент сам завантажує відео з сервера в /sdcard/Movies і може
        # замінити файли, які колись скопіювали кабелем (плеєр 1.9.0+).
        # GET_USAGE_STATS: сторож бачить, що поверх плеєра відкрився магазин Meta, і повертає плеєр (1.9.2+).
        for op in ("SYSTEM_ALERT_WINDOW", "REQUEST_INSTALL_PACKAGES", "MANAGE_EXTERNAL_STORAGE", "GET_USAGE_STATS"):
            code, out, err = self.run("shell", "appops", "set", package_name, op, "allow", serial=serial, timeout=20)
            if code != 0:
                errors.append(f"appops {op}: {(err or out).strip()}")
        code, out, err = self.run("shell", "pm", "grant", package_name,
                                  "android.permission.WRITE_SECURE_SETTINGS", serial=serial, timeout=20)
        if code != 0 or "Exception" in out + err:
            errors.append(f"grant WRITE_SECURE_SETTINGS (потрібен плеєр 1.8.3+): {(err or out).strip()[:200]}")
        return errors

    def has_stale_data(self, serial, package_name):
        """True, якщо в /sdcard/Android/data/<пакет> є папки іншого uid (лишились від видаленої копії).

        Плеєр не може в них писати, і Unity зависає на старті ("VRPlayer isn't responding").
        """
        _, out, _ = self.run("shell", "dumpsys", "package", package_name, serial=serial, timeout=20)
        m = re.search(r"userId=(\d+)", out)
        if not m:
            return False
        base = f"/sdcard/Android/data/{package_name}"
        _, out, _ = self.run("shell", f"stat -c %u {base} {base}/* {base}/files/* 2>/dev/null",
                             serial=serial, timeout=20)
        return any(uid != m.group(1) for uid in out.split())

    def disable_meta_dialogs(self, serial):
        """Вимикає першу настройку й підказки Meta (META_BLOCKING_DIALOGS). Повертає помилку або None.

        Перевірено на Quest 3S, Horizon OS v209: вимикаються, лишаються вимкненими після
        перезавантаження, сон / пробудження й головний екран працюють.
        """
        errors = []
        for package in META_BLOCKING_DIALOGS:
            code, out, err = self.run("shell", "pm", "disable-user", "--user", "0", package,
                                      serial=serial, timeout=20)
            if code != 0 or "disabled" not in out + err:
                errors.append(f"{package}: {(err or out).strip()[:200] or 'pm disable-user не вдався'}")
        return "; ".join(errors) or None

    def recover(self, serial, package_name):
        """Знімає зависле системне вікно, яке не дає відкрити плеєр, і знову запускає сторожа.

        Повертає список (ок, текст) для журналу.
        """
        steps = []
        for package in META_BLOCKING_DIALOGS + ("com.oculus.store",):
            code, out, err = self.run("shell", "am", "force-stop", package, serial=serial, timeout=20)
            if code != 0:
                steps.append((False, f"force-stop {package}: {(err or out).strip()}"))
        steps.append((True, "закрито вікна Meta (перша настройка, підказки, магазин)"))
        if self.has_stale_data(serial, package_name):
            # Очищає дані плеєра (адресу сервера та ім'я він знову отримає від сервера); відео не чіпає.
            code, out, err = self.run("shell", "pm", "clear", package_name, serial=serial, timeout=60)
            errors = self.grant_player_permissions(serial, package_name) if code == 0 else [(err or out).strip()]
            steps.append((not errors, "прибрано старі дані плеєра після перевстановлення" if not errors
                          else f"очищення даних плеєра: {'; '.join(errors)}"))
        error = self.disable_meta_dialogs(serial)
        steps.append((error is None, "першу настройку й підказки Meta вимкнено" if error is None else f"вимкнення: {error}"))
        self.run("shell", "am", "broadcast", "-n", f"{package_name}/.BootReceiver", serial=serial, timeout=20)
        code, out, err = self.run("shell", "monkey", "-p", package_name, "-c", "android.intent.category.LAUNCHER", "1",
                                  serial=serial, timeout=20)
        steps.append((code == 0, "плеєр запущено" if code == 0 else f"запуск плеєра: {(err or out).strip()[:200]}"))
        return steps

    def reboot(self, serial):
        return self.run("reboot", serial=serial, timeout=20)

    def set_autostart(self, serial, enabled):
        """Перемикає автозапуск через сторожа плеєра (порт 8081 окулярів, прокинутий по USB).

        Прапорець лежить у приватній теці застосунку, куди adb не пише, тому просимо самого
        сторожа. Повертає текст помилки або None.
        """
        code, out, err = self.run("forward", "tcp:0", "tcp:8081", serial=serial, timeout=10)
        port = out.strip()
        if code != 0 or not port.isdigit():
            return (err or out).strip() or "adb forward не вдався"
        url = f"http://127.0.0.1:{port}/autostart/{'on' if enabled else 'off'}"
        error = "сторож не відповів"
        try:
            for _ in range(8):  # сторож щойно запущено, даємо йому піднятись
                try:
                    with urllib.request.urlopen(urllib.request.Request(url, method="POST"), timeout=3) as resp:
                        if json.load(resp).get("autostart") is enabled:
                            return None
                        error = "сторож не змінив стан"
                except Exception as exc:
                    error = str(exc)
                time.sleep(1)
            return error
        finally:
            self.run("forward", "--remove", f"tcp:{port}", serial=serial, timeout=10)

    def uninstall_package(self, serial, package_name):
        """adb uninstall. Видаляє застосунок разом з його даними.

        Спершу pm clear: Quest при видаленні лишає частину /sdcard/Android/data/<пакет> зі старим
        uid; новий застосунок не може туди писати, і Unity зависає на старті ("isn't responding").
        """
        self.run("shell", "pm", "clear", package_name, serial=serial, timeout=60)
        return self.run("uninstall", package_name, serial=serial, timeout=60)

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

    def connect_wifi(self, serial, ssid, password, security="wpa2"):
        """
        Підключити пристрій до Wi-Fi мережі через ADB.
        Використовує 'cmd wifi connect-network' (Android 10+, Quest 2/3/Pro).
        security: wpa2 | wpa3 | open
        """
        if security == "open":
            code, out, err = self.run(
                "shell", "cmd", "wifi", "connect-network",
                ssid, "open",
                serial=serial, timeout=20
            )
        else:
            code, out, err = self.run(
                "shell", "cmd", "wifi", "connect-network",
                ssid, security, password,
                serial=serial, timeout=20
            )
        return code, out, err

    def get_wifi_status(self, serial):
        """Повертає поточну Wi-Fi мережу пристрою."""
        code, out, err = self.run(
            "shell", "cmd", "wifi", "status",
            serial=serial, timeout=10
        )
        if code == 0:
            for line in out.splitlines():
                if "Wifi is connected" in line or "SSID" in line:
                    return line.strip()
        return "Невідомо"

    def enable_wifi(self, serial):
        """Увімкнути Wi-Fi на пристрої."""
        return self.run("shell", "cmd", "wifi", "set-wifi-enabled", "enabled",
                        serial=serial, timeout=10)

    def enable_tcpip(self, serial, port=5555):
        """Перевести ADB в TCP/IP режим для wireless підключення."""
        return self.run("tcpip", str(port), serial=serial, timeout=10)


    def get_player_version(self, serial):
        _, out, _ = self.run("shell", "dumpsys", "package", PLAYER_PACKAGE, serial=serial, timeout=20)
        m = re.search(r"versionName=(\S+)", out)
        return m.group(1) if m else ""

    def rollback(self, serial, package_name, remove_player=True, enable_meta=True, restore_settings=True,
                 video_paths=(), wifi_ssids=()):
        """Повертає окуляри до стану до VR Classroom: все, що зробили setup_player() і плеєр.

        Видалення плеєра забирає й усе, що видавалось саме йому (appops, WRITE_SECURE_SETTINGS,
        інсталятор, сторож автозапуску, ім'я окулярів). Рядки профілю системних налаштувань сервера,
        крім captive_portal_mode, плеєр повертає сам, коли профіль на сервері порожній; після
        видалення він цього вже не зробить. Повертає список (ок, текст) для журналу.
        """
        steps = []

        def step(ok, text):
            steps.append((ok, text))

        if remove_player:
            # Плеєр тримав окуляри «вдягнутими» (prox_close): повертаємо звичайний датчик.
            self.run("shell", "am", "broadcast", "-a", "com.oculus.vrpowermanager.automation_disable",
                     serial=serial, timeout=20)
            if self.is_package_installed(serial, package_name):
                code, out, err = self.uninstall_package(serial, package_name)
                ok = code == 0 and "Success" in out + err
                step(ok, "плеєр видалено разом з даними і дозволами" if ok
                     else f"видалення плеєра: {(err or out).strip()[:200]}")
            else:
                step(True, "плеєр не встановлено")
            self.run("shell", "rm", "-rf", f"/sdcard/Android/data/{package_name}", serial=serial, timeout=30)
        if enable_meta:
            errors = []
            for package in META_BLOCKING_DIALOGS:
                code, out, err = self.run("shell", "pm", "enable", package, serial=serial, timeout=20)
                if code != 0 or "enabled" not in out + err:
                    errors.append(f"{package}: {(err or out).strip()[:200] or 'pm enable не вдався'}")
            step(not errors, "першу настройку й підказки Meta знову увімкнено" if not errors else "; ".join(errors))
        if restore_settings:
            code, out, err = self.run("shell", "settings", "delete", "global", "captive_portal_mode",
                                      serial=serial, timeout=20)
            step(code == 0, "captive_portal_mode повернуто до стандартного" if code == 0
                 else f"captive_portal_mode: {(err or out).strip()[:200]}")
        if video_paths:
            removed = 0
            for path in video_paths:
                code, _, _ = self.run("shell", "rm", "-f", path, serial=serial, timeout=30)
                removed += code == 0
            # Недокачані відео агента (ContentSync.java).
            self.run("shell", "rm -f /sdcard/Movies/.partial-*", serial=serial, timeout=30)
            self.run("shell", "content", "call", "--uri", "content://media", "--method", "scan_volume",
                     "--arg", "external_primary", serial=serial, timeout=15)
            step(removed == len(video_paths), f"видалено відео: {removed} з {len(video_paths)}")
        if wifi_ssids:
            _, out, _ = self.run("shell", "cmd", "wifi", "list-networks", serial=serial, timeout=15)
            forgotten = []
            for line in out.splitlines()[1:]:
                # "Network Id  SSID  Security type": SSID may hold single spaces, columns are 2+ apart.
                m = re.match(r"\s*(\d+)\s+(.+?)(?:\s{2,}\S.*)?$", line)
                if m and m.group(2).strip() in wifi_ssids:
                    code, _, _ = self.run("shell", "cmd", "wifi", "forget-network", m.group(1), serial=serial, timeout=15)
                    if code == 0:
                        forgotten.append(m.group(2).strip())
            step(True, f"забуто мережі: {', '.join(forgotten) or 'немає таких на окулярах'}")
        return steps


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
#  Оновлення з GitHub Releases
# ═══════════════════════════════════════════════════════════

def parse_version(text):
    return tuple(int(part) for part in re.findall(r"\d+", text or "")[:3])


def fetch_latest_release():
    """Останній реліз з GitHub: {version, notes, url, assets: {name: {url, size}}}. Кидає виняток без інтернету."""
    req = urllib.request.Request(GITHUB_LATEST_URL, headers={
        "Accept": "application/vnd.github+json", "User-Agent": "QuestDeployManager"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.load(resp)
    return {
        "version": (data.get("tag_name") or "").lstrip("v"),
        "notes": data.get("body") or "",
        "url": data.get("html_url") or "",
        "assets": {a["name"]: {"url": a["browser_download_url"], "size": a.get("size", 0)}
                   for a in data.get("assets") or [] if a.get("browser_download_url")},
    }


def download_file(url, dest, progress):
    """Завантажує у dest через .part (обрив не лишає битий файл). progress(done, total)."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "QuestDeployManager"})
    with urllib.request.urlopen(req, timeout=30) as resp, open(part, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            progress(done, total)
    if total and done != total:
        raise RuntimeError("завантаження обірвалось")
    os.replace(part, dest)


def swap_script(new_exe, exe):
    """.bat, який чекає, поки exe звільниться, підміняє його новим і запускає."""
    return (
        "@echo off\r\nset n=0\r\n:retry\r\n"
        f'move /y "{new_exe}" "{exe}" >nul 2>&1 && goto run\r\n'
        "set /a n+=1\r\nif %n% geq 60 goto end\r\ntimeout /t 1 /nobreak >nul\r\ngoto retry\r\n"
        f':run\r\nstart "" "{exe}"\r\n:end\r\ndel "%~f0"\r\n'
    )


# ═══════════════════════════════════════════════════════════
#  Сервіс: стан і дії (UI — tools/deploy_ui/index.html)
# ═══════════════════════════════════════════════════════════

_dialog_lock = Lock()


def native_dialog(kind, **kwargs):
    """Системний діалог вибору файлу/папки. tkinter лише для цього: окремий Tk на кожен виклик."""
    import tkinter as tk
    from tkinter import filedialog
    with _dialog_lock:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            return getattr(filedialog, kind)(parent=root, **kwargs)
        finally:
            root.destroy()


def human_size(size):
    return f"{size / 1024 / 1024:.1f} МБ" if size > 1024 * 1024 else f"{size / 1024:.0f} КБ"


class DeployService:
    def __init__(self):
        self.lock = Lock()
        self.config = load_config()
        self.adb = ADB(self.config.get("adb_path", "adb"))
        self.devices = []        # [{serial, model, android, player, status}]
        self.log_lines = []      # [(seq, text)]
        self.log_seq = 0
        self.deploying = False
        self.busy = ""           # назва довгої дії, що зараз іде (кнопки вимикаються)
        self.deploy_cancel = Event()
        self.overall = {"done": 0, "total": 0, "label": "Готово"}
        self.current = {"text": "", "pct": 0}
        self.release = None
        self.release_error = ""
        self.update_job = None
        self.apk_packages = {}   # шлях → package name (aapt повільний, рахуємо раз)

    # ── журнал ─────────────────────────────────────────
    def log(self, msg):
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
        with self.lock:
            self.log_seq += 1
            self.log_lines.append((self.log_seq, line))
            del self.log_lines[:-500]
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def model(self, serial):
        return self.config.get("devices", {}).get(serial, {}).get("name", serial)

    def set_status(self, serial, status):
        for dev in self.devices:
            if dev["serial"] == serial:
                dev["status"] = status

    def background(self, name, fn, *args):
        """Запуск довгої дії в потоці; поки вона йде, інші довгі дії не стартують."""
        with self.lock:
            if self.busy or self.deploying:
                return {"ok": False, "error": f"Зачекайте: {self.busy or 'розгортання'}"}
            self.busy = name

        def run():
            try:
                fn(*args)
            except Exception as exc:
                self.log(f"✗ {name}: {exc}")
            finally:
                self.busy = ""
        Thread(target=run, daemon=True).start()
        return {"ok": True}

    # ── стан для UI ────────────────────────────────────
    def state(self, since=0):
        cfg = self.config
        files = []
        for f in cfg.get("files", []):
            size = human_size(os.path.getsize(f["src"])) if os.path.exists(f["src"]) else "немає файлу"
            files.append({"src": f["src"], "dst": f["dst"], "size": size})
        apks = []
        for path in cfg.get("apks", []):
            exists = os.path.exists(path)
            if exists and path not in self.apk_packages:
                self.apk_packages[path] = self.adb.get_package_name_from_apk(path) or "?"
            apks.append({"path": path, "package": self.apk_packages.get(path, "") if exists else "",
                         "size": human_size(os.path.getsize(path)) if exists else "немає файлу"})
        with self.lock:
            log = [line for seq, line in self.log_lines if seq > since]
            seq = self.log_seq
        return {
            "version": DEPLOY_VERSION,
            "devices": self.devices,
            "files": files,
            "apks": apks,
            "wifi": [{"ssid": n["ssid"], "security": n.get("security", "wpa2")} for n in cfg.get("wifi_networks", [])],
            "options": {
                "deploy_content": cfg.get("deploy_content", "all"),
                "force_reinstall": cfg.get("force_reinstall", False),
                "autostart": cfg.get("autostart", AUTOSTART_KEEP),
                "wifi_auto_deploy": cfg.get("wifi_auto_deploy", False),
            },
            "autostart_choices": [AUTOSTART_KEEP, AUTOSTART_ON, AUTOSTART_OFF],
            "adb_path": cfg.get("adb_path", "adb"),
            "config_path": str(CONFIG_FILE),
            "deploying": self.deploying,
            "busy": self.busy,
            "overall": self.overall,
            "current": self.current,
            "log": log,
            "log_seq": seq,
            "update": self.update_state(),
        }

    def update_state(self):
        rel = self.release
        return {
            "current": DEPLOY_VERSION,
            "latest": {k: rel[k] for k in ("version", "notes", "url")} if rel else None,
            "has_player": bool(rel and PLAYER_ASSET in rel["assets"]),
            "self_available": bool(rel and DEPLOY_ASSET in rel["assets"]
                                   and parse_version(rel["version"]) > parse_version(DEPLOY_VERSION)),
            "can_self_update": bool(getattr(sys, "frozen", False)) and os.name == "nt",
            "error": self.release_error,
            "job": self.update_job,
        }

    # ── пристрої ───────────────────────────────────────
    def refresh_devices(self):
        self.log("Пошук підключених пристроїв…")
        devices = []
        for serial in self.adb.get_devices():
            model = self.adb.get_model(serial)
            devices.append({"serial": serial, "model": model,
                            "android": self.adb.get_android_version(serial),
                            "player": self.adb.get_player_version(serial), "status": "Готовий"})
            self.config.setdefault("devices", {})[serial] = {"name": model, "last_seen": datetime.now().isoformat()}
        save_config(self.config)
        self.devices = devices
        self.log(f"Знайдено пристроїв: {len(devices)}")

    def targets(self, serials):
        known = [d["serial"] for d in self.devices]
        chosen = [s for s in serials or [] if s in known]
        return chosen or known

    def recover(self, serials):
        self.log("═══ Відновлення окулярів ═══")
        for serial in serials:
            for ok, text in self.adb.recover(serial, PLAYER_PACKAGE):
                self.log(f"  {'✓' if ok else '✗'} {self.model(serial)} ({serial}): {text}")
        self.log("Якщо інтерфейс не повернувся за хвилину — «Перезавантажити».")

    def reboot(self, serials):
        for serial in serials:
            code, out, err = self.adb.reboot(serial)
            self.log(f"  {'✓' if code == 0 else '✗'} {self.model(serial)} ({serial}): "
                     f"{'перезавантажуються' if code == 0 else (err or out).strip()}")

    def rollback(self, serials, opts):
        self.log(f"═══ Відкат окулярів: {len(serials)} ═══")
        videos = []
        if opts.get("videos"):
            videos = [f["dst"].rstrip("/") + "/" + os.path.basename(f["src"]) for f in self.config.get("files", [])]
        ssids = [n["ssid"] for n in self.config.get("wifi_networks", [])] if opts.get("wifi") else []
        for serial in serials:
            self.set_status(serial, "Відкат…")
            steps = self.adb.rollback(serial, PLAYER_PACKAGE,
                                      remove_player=opts.get("player", True),
                                      enable_meta=opts.get("meta", True),
                                      restore_settings=opts.get("settings", True),
                                      video_paths=videos, wifi_ssids=ssids)
            for ok, text in steps:
                self.log(f"  {'✓' if ok else '✗'} {self.model(serial)} ({serial}): {text}")
            self.set_status(serial, "Відкочено" if all(ok for ok, _ in steps) else "Відкат з помилками")
        self.log("═══ Відкат завершено ═══")
        self.refresh_devices()

    def enable_tcpip(self, serials):
        self.log("═══ Увімкнення Wireless ADB (порт 5555) ═══")
        for serial in serials:
            code, out, err = self.adb.enable_tcpip(serial, 5555)
            if code == 0:
                _, ip_out, _ = self.adb.run("shell", "ip", "route", "get", "8.8.8.8", serial=serial, timeout=10)
                m = re.search(r"src\s+([\d.]+)", ip_out)
                hint = f"  → adb connect {m.group(1)}:5555" if m else ""
                self.log(f"  ✓ {self.model(serial)} ({serial}): tcpip:5555 увімкнено{hint}")
            else:
                self.log(f"  ✗ {self.model(serial)} ({serial}): {err or out}")

    # ── Wi-Fi ──────────────────────────────────────────
    def apply_wifi(self, serials):
        networks = self.config.get("wifi_networks", [])
        self.log(f"═══ Застосування Wi-Fi: {len(networks)} мереж на {len(serials)} пристроїв ═══")
        for serial in serials:
            self.log(f"── Пристрій: {self.model(serial)} ({serial}) ──")
            self._connect_wifi(serial, networks)
        self.log("═══ Застосування Wi-Fi завершено ═══")

    def _connect_wifi(self, serial, networks):
        self.adb.enable_wifi(serial)
        for net in networks:
            ssid = net["ssid"]
            code, out, err = self.adb.connect_wifi(serial, ssid, net.get("password", ""), net.get("security", "wpa2"))
            combined = (out + err).lower()
            if code == 0 and any(x in combined for x in ["success", "connected", "saving", "initiated"]):
                self.log(f"  ✓ Wi-Fi: {ssid}")
            elif "already" in combined:
                self.log(f"  ⏭ Wi-Fi вже: {ssid}")
            else:
                self.log(f"  ✗ Wi-Fi помилка ({ssid}): {err or out or '?'}")

    # ── розгортання ────────────────────────────────────
    def start_deploy(self, serials):
        with self.lock:
            if self.deploying or self.busy:
                return {"ok": False, "error": "Вже йде інша дія"}
            content = self.config.get("deploy_content", "all")
            files = self.config.get("files", []) if content in ("all", "files") else []
            apks = self.config.get("apks", []) if content in ("all", "apks") else []
            if not files and not apks:
                what = {"files": "файли", "apks": "APK"}.get(content, "файли або APK")
                return {"ok": False, "error": f"Додайте {what} для розгортання."}
            self.deploying = True
        self.deploy_cancel.clear()
        Thread(target=self.do_deploy, args=(serials, files, apks, self.config.get("force_reinstall", False)),
               daemon=True).start()
        return {"ok": True}

    def do_deploy(self, devices, files, apks, force_reinstall=False):
        try:
            self._deploy(devices, files, apks, force_reinstall)
        except Exception as exc:
            self.log(f"✗ Розгортання зупинилось: {exc}")
        finally:
            self.deploying = False
            self.current = {"text": "", "pct": 0}

    def _deploy(self, devices, files, apks, force_reinstall):
        total_tasks = len(devices) * (len(files) + len(apks))
        done_tasks = 0
        self.overall = {"done": 0, "total": total_tasks, "label": "Розгортання…"}
        self.log(f"═══ Початок розгортання: {len(devices)} пристроїв, {len(files)} файлів, {len(apks)} APK"
                 f"{' (force reinstall)' if apks and force_reinstall else ''} ═══")
        apk_packages = {p: self.adb.get_package_name_from_apk(p) for p in apks if os.path.exists(p)}

        def advance():
            nonlocal done_tasks
            done_tasks += 1
            self.overall = {"done": done_tasks, "total": total_tasks, "label": "Розгортання…"}

        for serial in devices:
            if self.deploy_cancel.is_set():
                break
            self.log(f"── Пристрій: {self.model(serial)} ({serial}) ──")
            self.set_status(serial, "Розгортання…")

            if self.config.get("wifi_auto_deploy", False) and self.config.get("wifi_networks"):
                self.log(f"  📶 Застосування Wi-Fi ({len(self.config['wifi_networks'])} мереж)…")
                self._connect_wifi(serial, self.config["wifi_networks"])

            for apk_path in apks:
                if self.deploy_cancel.is_set():
                    break
                apk_name = os.path.basename(apk_path)
                if not os.path.exists(apk_path):
                    self.log(f"  ✗ APK не знайдено: {apk_path}")
                    advance()
                    continue
                pkg = apk_packages.get(apk_path)
                installed = bool(pkg) and self.adb.is_package_installed(serial, pkg)
                if installed and not force_reinstall:
                    self.log(f"  ⏭ APK вже встановлено: {pkg}")
                    if pkg == PLAYER_PACKAGE:
                        self._setup_player(serial, apk_path)
                    advance()
                    continue
                if installed and force_reinstall:
                    self.current = {"text": f"Видаляю {pkg}…", "pct": -1}
                    self.log(f"  🗑 Видаляю встановлений: {pkg}…")
                    self._uninstall(serial, pkg)
                self.current = {"text": f"Встановлюю {apk_name}…", "pct": -1}
                self.set_status(serial, f"Встановлення {apk_name}…")
                self.log(f"  ⏳ Встановлюю: {apk_name} ({pkg or '?'})…")
                code, out, err = self.adb.install_apk(serial, apk_path)
                result = out + err
                # Package name міг бути невідомий (немає aapt) — беремо його з помилки несумісного підпису.
                if force_reinstall and "INSTALL_FAILED_UPDATE_INCOMPATIBLE" in result:
                    m = re.search(r"Existing package (\S+)", result)
                    if m:
                        self.log(f"  🗑 Підпис не збігається, видаляю: {m.group(1)}…")
                        self._uninstall(serial, m.group(1))
                        code, out, err = self.adb.install_apk(serial, apk_path)
                        result = out + err
                if code == 0 and "Success" in result:
                    self.log(f"  ✓ Встановлено: {apk_name}")
                    if pkg == PLAYER_PACKAGE:
                        self._setup_player(serial, apk_path)
                else:
                    self.log(f"  ✗ Помилка встановлення {apk_name}: {err or out}")
                advance()

            for file_entry in files:
                if self.deploy_cancel.is_set():
                    break
                src, dst = file_entry["src"], file_entry["dst"]
                filename = os.path.basename(src)
                if not os.path.exists(src):
                    self.log(f"  ✗ Файл не знайдено: {src}")
                    advance()
                    continue
                local_size = os.path.getsize(src)
                remote_path = dst.rstrip("/") + "/" + filename
                if self.adb.remote_file_size(serial, remote_path) == local_size:
                    self.log(f"  ⏭ Файл вже є: {filename} ({local_size / 1024 / 1024:.1f} МБ)")
                    advance()
                    continue
                self.log(f"  ⏳ Копіюю: {filename} ({local_size / 1024 / 1024:.1f} МБ) → {dst}")
                self.set_status(serial, f"Копіювання {filename}")

                def progress_cb(pct, speed, status, fn=filename, ser=serial):
                    self.current = {"text": f"{fn} → {ser}  {speed}".strip(), "pct": pct}
                    if pct >= 0:
                        self.set_status(ser, f"Копіювання {pct}%")

                code, out, err_line = self.adb.push_with_progress(serial, src, remote_path, callback=progress_cb)
                if code == 0:
                    self.log(f"  ✓ Скопійовано: {filename}")
                    self.adb.trigger_media_scan(serial, remote_path)
                else:
                    self.log(f"  ✗ Помилка копіювання {filename}: {err_line or out}")
                advance()

            self.set_status(serial, "Скасовано" if self.deploy_cancel.is_set() else "✓ Готово")

        status = "Скасовано" if self.deploy_cancel.is_set() else "Завершено"
        self.overall = {"done": done_tasks, "total": total_tasks, "label": status}
        self.log(f"═══ {status}: {done_tasks}/{total_tasks} задач ═══")

    def _setup_player(self, serial, apk_path):
        self.current = {"text": "Налаштовую автозапуск і самооновлення…", "pct": -1}
        choice = self.config.get("autostart", AUTOSTART_KEEP)
        autostart = {AUTOSTART_ON: True, AUTOSTART_OFF: False}.get(choice)
        errors = self.adb.setup_player(serial, apk_path, PLAYER_PACKAGE, autostart=autostart)
        if errors:
            self.log(f"  ✗ Налаштування плеєра: {'; '.join(errors)}")
        else:
            self.log("  ✓ Плеєр налаштовано: тихе оновлення, мережа без інтернету, системні налаштування з сервера, "
                     f"автозапуск — {choice}")

    def _uninstall(self, serial, pkg):
        code, out, err = self.adb.uninstall_package(serial, pkg)
        self.log(f"  ✓ Видалено: {pkg}" if code == 0 and "Success" in out + err
                 else f"  ✗ Помилка видалення {pkg}: {err or out}")

    # ── списки ─────────────────────────────────────────
    def add_files(self, dst, folder=False):
        if folder:
            chosen = native_dialog("askdirectory", title="Оберіть папку з файлами")
            paths = [os.path.join(chosen, f) for f in os.listdir(chosen)
                     if os.path.isfile(os.path.join(chosen, f))] if chosen else []
        else:
            paths = list(native_dialog("askopenfilenames", title="Оберіть файли") or [])
        for p in paths:
            self.config["files"].append({"src": p, "dst": dst})
        save_config(self.config)
        return {"ok": True, "added": len(paths)}

    def add_apks(self):
        paths = native_dialog("askopenfilenames", title="Оберіть APK файли",
                              filetypes=[("APK файли", "*.apk"), ("Всі файли", "*.*")]) or []
        for p in paths:
            if p not in self.config["apks"]:
                self.config["apks"].append(p)
        save_config(self.config)
        return {"ok": True, "added": len(paths)}

    def remove_items(self, key, indices):
        items = self.config.get(key, [])
        for i in sorted({int(i) for i in indices}, reverse=True):
            if 0 <= i < len(items):
                items.pop(i)
        save_config(self.config)
        return {"ok": True}

    def add_wifi(self, ssid, security, password):
        ssid = (ssid or "").strip()
        if not ssid:
            return {"ok": False, "error": "Введіть SSID"}
        if security not in ("wpa2", "wpa3", "open"):
            return {"ok": False, "error": "Невідомий тип безпеки"}
        if security != "open" and not password:
            return {"ok": False, "error": "Введіть пароль або оберіть тип open"}
        self.config.setdefault("wifi_networks", []).append(
            {"ssid": ssid, "security": security, "password": password if security != "open" else ""})
        save_config(self.config)
        self.log(f"Wi-Fi мережу додано: {ssid}")
        return {"ok": True}

    def set_options(self, opts):
        for key in ("deploy_content", "force_reinstall", "autostart", "wifi_auto_deploy"):
            if key in opts:
                self.config[key] = opts[key]
        save_config(self.config)
        return {"ok": True}

    def set_adb_path(self, path):
        self.config["adb_path"] = path.strip() or "adb"
        self.adb = ADB(self.config["adb_path"])
        self.apk_packages.clear()
        save_config(self.config)
        self.log(f"ADB шлях збережено: {self.config['adb_path']}")
        return {"ok": True}

    def reload_config(self):
        self.config = load_config()
        self.adb = ADB(self.config.get("adb_path", "adb"))
        self.apk_packages.clear()
        self.log("Конфіг перезавантажено")
        return {"ok": True}

    # ── оновлення з GitHub ─────────────────────────────
    def check_release(self):
        try:
            self.release = fetch_latest_release()
            self.release_error = ""
            self.log(f"GitHub: останній реліз {self.release['version']}")
        except Exception as exc:
            self.release_error = str(exc)
            self.log(f"GitHub не відповів: {exc}")

    def _download_job(self, kind, asset_name, dest):
        asset = self.release["assets"][asset_name]
        job = {"kind": kind, "stage": "downloading", "done": 0, "total": asset["size"], "error": ""}
        self.update_job = job

        def progress(done, total):
            job.update(done=done, total=total or job["total"])
        try:
            download_file(asset["url"], dest, progress)
            job["stage"] = "done"
            return True
        except Exception as exc:
            job.update(stage="failed", error=str(exc))
            self.log(f"✗ Завантаження {asset_name}: {exc}")
            return False

    def download_player(self):
        version = self.release["version"]
        dest = SCRIPT_DIR / "updates" / f"VRClassroomPlayer-Quest-{version}.apk"
        if not self._download_job("player", PLAYER_ASSET, dest):
            return
        # Старі APK плеєра з цього ж менеджера замінюємо новим; свої APK користувача не чіпаємо.
        apks = [p for p in self.config.get("apks", []) if not os.path.basename(p).startswith("VRClassroomPlayer-Quest")]
        self.config["apks"] = apks + [str(dest)]
        save_config(self.config)
        self.log(f"✓ Плеєр {version} завантажено і додано в «Додатки»: розгорніть його на окуляри")

    def update_self(self):
        exe = Path(sys.executable).resolve()
        new_exe = exe.with_name(exe.stem + ".new.exe")
        if not self._download_job("self", DEPLOY_ASSET, new_exe):
            return
        script = Path(tempfile.gettempdir()) / "questdeploy-update.bat"
        script.write_text(swap_script(new_exe, exe), encoding="utf-8")
        subprocess.Popen(["cmd", "/c", str(script)], close_fds=True,
                         creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
        self.update_job["stage"] = "restarting"
        self.log("Deploy Manager оновлюється і перезапуститься…")
        Timer(1.5, os._exit, args=(0,)).start()


# ═══════════════════════════════════════════════════════════
#  HTTP: сторінка UI + JSON API (лише 127.0.0.1)
# ═══════════════════════════════════════════════════════════

def ui_dir():
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "deploy_ui"


class Handler(BaseHTTPRequestHandler):
    service = None
    last_seen = [time.time()]
    STATIC = {".html": "text/html; charset=utf-8", ".woff2": "font/woff2", ".svg": "image/svg+xml"}

    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        Handler.last_seen[0] = time.time()
        path, _, query = self.path.partition("?")
        if path == "/api/state":
            since = int(re.search(r"since=(\d+)", query).group(1)) if "since=" in query else 0
            return self._send(200, self.service.state(since))
        name = "index.html" if path == "/" else path.lstrip("/")
        file = (ui_dir() / name).resolve()
        if ui_dir().resolve() not in file.parents or not file.is_file() or file.suffix not in self.STATIC:
            return self._send(404, {"error": "not found"})
        return self._send(200, file.read_bytes(), self.STATIC[file.suffix])

    def do_POST(self):
        Handler.last_seen[0] = time.time()
        # Лише наша сторінка: інший сайт у браузері (чи DNS rebinding) не може смикати adb через цей порт.
        origin = self.headers.get("Origin", "")
        if (origin and origin != f"http://127.0.0.1:{PORT}") or self.headers.get("Host") != f"127.0.0.1:{PORT}":
            return self._send(403, {"ok": False, "error": "forbidden"})
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._send(400, {"ok": False, "error": "bad json"})
        try:
            result = self.route(self.path, body)
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
        return self._send(200 if result.get("ok", True) else 400, result)

    def route(self, path, body):
        s = self.service
        serials = s.targets(body.get("serials"))
        need_devices = path in ("/api/deploy", "/api/recover", "/api/reboot", "/api/rollback",
                                "/api/wifi/apply", "/api/tcpip")
        if need_devices and not serials:
            return {"ok": False, "error": "Немає підключених пристроїв."}
        routes = {
            "/api/devices/refresh": lambda: s.background("пошук пристроїв", s.refresh_devices),
            "/api/deploy": lambda: s.start_deploy(serials),
            "/api/cancel": lambda: (s.deploy_cancel.set(), s.log("Скасування…"), {"ok": True})[-1],
            "/api/recover": lambda: s.background("відновлення", s.recover, serials),
            "/api/reboot": lambda: s.background("перезавантаження", s.reboot, serials),
            "/api/rollback": lambda: s.background("відкат", s.rollback, serials, body.get("options") or {}),
            "/api/tcpip": lambda: s.background("wireless adb", s.enable_tcpip, serials),
            "/api/wifi/apply": lambda: (s.background("Wi-Fi", s.apply_wifi, serials)
                                        if s.config.get("wifi_networks") else
                                        {"ok": False, "error": "Немає збережених Wi-Fi мереж."}),
            "/api/wifi/add": lambda: s.add_wifi(body.get("ssid"), body.get("security", "wpa2"), body.get("password", "")),
            "/api/wifi/remove": lambda: s.remove_items("wifi_networks", body.get("indices", [])),
            "/api/files/add": lambda: s.add_files(body.get("dst") or "/sdcard/Movies/", folder=bool(body.get("folder"))),
            "/api/files/remove": lambda: s.remove_items("files", body.get("indices", [])),
            "/api/apks/add": lambda: s.add_apks(),
            "/api/apks/remove": lambda: s.remove_items("apks", body.get("indices", [])),
            "/api/options": lambda: s.set_options(body),
            "/api/adb/browse": lambda: {"ok": True, "path": native_dialog(
                "askopenfilename", title="Знайти adb.exe", filetypes=[("ADB", "adb.exe"), ("Всі", "*.*")]) or ""},
            "/api/adb/save": lambda: s.set_adb_path(body.get("path", "")),
            "/api/config/open": lambda: (os.startfile(str(CONFIG_FILE)) if os.name == "nt" else None, {"ok": True})[-1],
            "/api/config/reload": lambda: s.reload_config(),
            "/api/update/check": lambda: s.background("перевірка оновлень", s.check_release),
            "/api/update/player": lambda: (s.background("завантаження плеєра", s.download_player)
                                           if s.update_state()["has_player"] else
                                           {"ok": False, "error": "Спершу перевірте оновлення"}),
            "/api/update/self": lambda: (s.background("оновлення менеджера", s.update_self)
                                         if s.update_state()["self_available"] and s.update_state()["can_self_update"] else
                                         {"ok": False, "error": "Немає новішої версії"}),
        }
        if path not in routes:
            return {"ok": False, "error": "unknown action"}
        return routes[path]()


def open_window(url):
    """Окреме вікно без вкладок (Edge/Chrome --app); інакше — звичайний браузер."""
    candidates = [shutil.which("msedge"), shutil.which("chrome")]
    for env in ("ProgramFiles(x86)", "ProgramFiles", "LocalAppData"):
        base = os.environ.get(env)
        if base:
            candidates += [os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
                           os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")]
    for exe in candidates:
        if exe and os.path.isfile(exe):
            subprocess.Popen([exe, f"--app={url}", "--window-size=1320,900"], close_fds=True)
            return
    webbrowser.open(url)


def main():
    url = f"http://127.0.0.1:{PORT}/"
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        open_window(url)  # менеджер уже запущено: просто показуємо його вікно
        return
    service = DeployService()
    Handler.service = service
    Thread(target=service.refresh_devices, daemon=True).start()
    if service.config.get("check_updates", True):
        Thread(target=service.check_release, daemon=True).start()
    if "--no-window" not in sys.argv:  # --no-window: лише сервер (перевірка в браузері)
        open_window(url)
    # Вікно закрили (сторінка не питає стан 30 с) і нічого не йде — виходимо.
    def watchdog():
        while True:
            time.sleep(5)
            idle = time.time() - Handler.last_seen[0]
            if idle > 30 and not service.deploying and not service.busy:
                os._exit(0)
    Thread(target=watchdog, daemon=True).start()
    server.serve_forever()


if __name__ == "__main__":
    main()
