from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.request
from dataclasses import replace
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from .models import ApkInfo, DeviceInfo, RequiredFileSpec


class ADBError(RuntimeError):
    pass


class ADBService:
    def __init__(self, adb_path: Optional[str] = None, aapt_path: Optional[str] = None):
        self.adb_path = adb_path or self._find_adb()
        self.aapt_path = aapt_path or self._find_aapt()

    def _find_adb(self) -> str:
        adb = shutil.which("adb")
        if adb:
            return adb
        raise ADBError("adb was not found in PATH")

    def _find_aapt(self) -> str:
        explicit = shutil.which("aapt")
        if explicit:
            return explicit

        sdk_roots = []
        for env_name in ("ANDROID_SDK_ROOT", "ANDROID_HOME"):
            value = os.environ.get(env_name, "").strip()
            if value:
                sdk_roots.append(Path(value))

        adb_path = Path(self.adb_path)
        if "platform-tools" in adb_path.parts:
            try:
                sdk_roots.append(adb_path.parents[1])
            except IndexError:
                pass

        for root in sdk_roots:
            build_tools = root / "build-tools"
            if not build_tools.exists():
                continue
            candidates = sorted(build_tools.glob("*/aapt.exe"), reverse=True)
            if candidates:
                return str(candidates[0])

        return ""

    def run(
        self,
        args: List[str],
        *,
        serial: Optional[str] = None,
        timeout: int = 30,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        command = [self.adb_path]
        if serial:
            command.extend(["-s", serial])
        command.extend(args)
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        if check and result.returncode != 0:
            raise ADBError((result.stderr or result.stdout or "adb command failed").strip())
        return result

    def shell(self, serial: str, command: str, *, timeout: int = 30, check: bool = True) -> str:
        result = self.run(["shell", "sh", "-c", command], serial=serial, timeout=timeout, check=check)
        return result.stdout.strip()

    def list_devices(self) -> List[DeviceInfo]:
        result = self.run(["devices", "-l"], timeout=20)
        devices: List[DeviceInfo] = []
        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("List of devices attached"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            serial = parts[0]
            adb_state = parts[1]
            model = ""
            for token in parts[2:]:
                if token.startswith("model:"):
                    model = token.split(":", 1)[1].replace("_", " ")
                    break
            transport = "wifi" if re.match(r"^\d+\.\d+\.\d+\.\d+:\d+$", serial) else "usb"
            devices.append(DeviceInfo(serial=serial, adb_state=adb_state, transport=transport, model=model))
        return devices

    def get_local_apk_info(self, apk_path: str, fallback_package_id: str) -> ApkInfo:
        apk = ApkInfo(path=apk_path, package_id=fallback_package_id)
        if not apk_path or not Path(apk_path).exists() or not self.aapt_path:
            return apk

        result = subprocess.run(
            [self.aapt_path, "dump", "badging", apk_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
        if result.returncode != 0:
            return apk

        match = re.search(
            r"package: name='(?P<package>[^']+)' versionCode='(?P<code>[^']*)' versionName='(?P<name>[^']*)'",
            result.stdout,
        )
        if match:
            apk.package_id = match.group("package") or fallback_package_id
            apk.version_code = match.group("code")
            apk.version_name = match.group("name")
        return apk

    def inspect_device(self, device: DeviceInfo, package_id: str, http_port: int) -> DeviceInfo:
        info = replace(device)
        if info.adb_state != "device":
            info.note = f"ADB state: {info.adb_state}"
            return info

        if not info.model:
            try:
                info.model = self.shell(info.serial, "getprop ro.product.model", timeout=10)
            except ADBError:
                pass

        info.ip = self.get_device_ip(info.serial)
        package = self.get_device_package_info(info.serial, package_id)
        if package:
            info.package_installed = True
            info.installed_version_name = package.get("version_name", "")
            info.installed_version_code = package.get("version_code", "")

        if info.ip:
            try:
                status = self.http_json("GET", info.ip, http_port, "/status", timeout=3)
                info.player_http_ok = True
                info.player_version = str(status.get("playerVersion", "")).strip()
                info.device_name = str(status.get("deviceName", "")).strip()
                if not info.model:
                    info.model = str(status.get("deviceModel", "")).strip()
            except Exception:
                info.player_http_ok = False

        return info

    def get_device_ip(self, serial: str) -> str:
        if re.match(r"^\d+\.\d+\.\d+\.\d+:\d+$", serial):
            return serial.split(":", 1)[0]

        route = self.shell(serial, "ip route", timeout=10, check=False)
        match = re.search(r"\bsrc\s+(\d+\.\d+\.\d+\.\d+)", route)
        if match:
            return match.group(1)

        addr = self.shell(serial, "ip addr show wlan0", timeout=10, check=False)
        match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", addr)
        if match:
            return match.group(1)
        return ""

    def get_device_package_info(self, serial: str, package_id: str) -> Optional[Dict[str, str]]:
        path_output = self.shell(serial, f"pm path {shell_escape(package_id)}", timeout=10, check=False)
        if "package:" not in path_output:
            return None

        dumpsys = self.shell(serial, f"dumpsys package {shell_escape(package_id)}", timeout=20, check=False)
        version_name = ""
        version_code = ""
        version_name_match = re.search(r"versionName=([^\s]+)", dumpsys)
        if version_name_match:
            version_name = version_name_match.group(1).strip()
        version_code_match = re.search(r"versionCode=(\d+)", dumpsys)
        if version_code_match:
            version_code = version_code_match.group(1).strip()
        return {"version_name": version_name, "version_code": version_code}

    def launch_app(self, serial: str, package_id: str) -> None:
        self.run(
            ["shell", "monkey", "-p", package_id, "-c", "android.intent.category.LAUNCHER", "1"],
            serial=serial,
            timeout=30,
            check=False,
        )

    def install_apk(self, serial: str, apk_path: str) -> str:
        result = self.run(["install", "-r", "-g", apk_path], serial=serial, timeout=600, check=False)
        output = (result.stdout + "\n" + result.stderr).strip()
        if result.returncode != 0 or "Failure" in output:
            raise ADBError(output or "APK install failed")
        return output

    def pair_wifi(self, serial: str) -> str:
        self.run(["tcpip", "5555"], serial=serial, timeout=30)
        time.sleep(2)
        ip = self.get_device_ip(serial)
        if not ip:
            raise ADBError("Could not determine device Wi-Fi IP")
        result = self.run(["connect", f"{ip}:5555"], timeout=30, check=False)
        output = (result.stdout + "\n" + result.stderr).strip()
        if "connected to" not in output and "already connected to" not in output:
            raise ADBError(output or "ADB Wi-Fi connect failed")
        return ip

    def http_json(
        self,
        method: str,
        ip: str,
        port: int,
        path: str,
        payload: Optional[Dict[str, object]] = None,
        timeout: int = 5,
    ) -> Dict[str, object]:
        url = f"http://{ip}:{port}{path}"
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
        return json.loads(body) if body else {}

    def wait_for_player_http(self, serial: str, ip: str, port: int, package_id: str, timeout: int = 40) -> bool:
        if not ip:
            return False
        self.launch_app(serial, package_id)
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                self.http_json("GET", ip, port, "/status", timeout=3)
                return True
            except Exception:
                time.sleep(2)
        return False

    def get_remote_files_http(self, ip: str, port: int) -> Dict[str, int]:
        data = self.http_json("GET", ip, port, "/files", timeout=8)
        results: Dict[str, int] = {}
        for item in data.get("files", []):
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            try:
                size = int(item.get("size", 0))
            except (TypeError, ValueError):
                size = 0
            results[name] = size
        return results

    def get_remote_files_adb(self, serial: str, remote_dir: str) -> Dict[str, int]:
        command = (
            f"dir={shell_escape(remote_dir)}; "
            f"if [ -d \"$dir\" ]; then "
            f"for f in \"$dir\"/*; do "
            f"[ -f \"$f\" ] || continue; "
            f"size=$(wc -c < \"$f\" 2>/dev/null | tr -d '[:space:]'); "
            f"base=$(basename \"$f\"); "
            f"printf '%s|%s\\n' \"$base\" \"$size\"; "
            f"done; fi"
        )
        output = self.shell(serial, command, timeout=30, check=False)
        results: Dict[str, int] = {}
        for line in output.splitlines():
            if "|" not in line:
                continue
            name, size_text = line.split("|", 1)
            name = name.strip()
            if not name:
                continue
            try:
                size = int(size_text.strip())
            except ValueError:
                size = 0
            results[name] = size
        return results

    def get_remote_file_size(self, serial: str, remote_path: str) -> int:
        command = (
            "path="
            + shell_escape(remote_path)
            + "; "
            + "if [ -f \"$path\" ]; then "
            + "if command -v toybox >/dev/null 2>&1; then toybox stat -c %s \"$path\" 2>/dev/null; "
            + "elif command -v stat >/dev/null 2>&1; then stat -c %s \"$path\" 2>/dev/null; "
            + "else wc -c < \"$path\" 2>/dev/null | tr -d '[:space:]'; fi; "
            + "fi"
        )
        output = self.shell(serial, command, timeout=15, check=False)
        try:
            return int(output.strip())
        except (TypeError, ValueError):
            return 0

    def ensure_remote_dir(self, serial: str, remote_dir: str) -> None:
        self.shell(serial, f"mkdir -p {shell_escape(remote_dir)}", timeout=20)

    def remove_remote_file(self, serial: str, remote_path: str) -> None:
        self.shell(serial, f"rm -f {shell_escape(remote_path)}", timeout=20, check=False)

    def replace_remote_file(self, serial: str, temp_path: str, final_path: str) -> None:
        command = f"rm -f {shell_escape(final_path)} && mv {shell_escape(temp_path)} {shell_escape(final_path)}"
        self.shell(serial, command, timeout=60)

    def trigger_media_scan(
        self,
        serial: str,
        package_id: str,
        remote_files: Iterable[str],
        ip: str,
        port: int,
    ) -> None:
        files = list(remote_files)
        if not files:
            return

        if ip:
            try:
                self.launch_app(serial, package_id)
                self.http_json("POST", ip, port, "/media/scan", payload={"files": files}, timeout=10)
                return
            except Exception:
                pass

        for remote_path in files:
            self.run(
                [
                    "shell",
                    "am",
                    "broadcast",
                    "-a",
                    "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
                    "-d",
                    f"file://{remote_path}",
                ],
                serial=serial,
                timeout=30,
                check=False,
            )

    def upload_file_with_progress(
        self,
        serial: str,
        local_path: str,
        remote_dir: str,
        *,
        progress_cb: Optional[Callable[[int, int, float, str, str], None]] = None,
    ) -> str:
        source = Path(local_path)
        if not source.exists():
            raise ADBError(f"Missing local file: {source}")

        total_bytes = source.stat().st_size
        filename = source.name
        temp_remote_path = f"{remote_dir}/.{filename}.uploading"
        final_remote_path = f"{remote_dir}/{filename}"

        self.ensure_remote_dir(serial, remote_dir)
        self.remove_remote_file(serial, temp_remote_path)

        command = [self.adb_path, "-s", serial, "push", "-z", "any", str(source), temp_remote_path]
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=False,
        )

        output_chunks: List[bytes] = []
        reader_done = threading.Event()

        def drain_output() -> None:
            if process.stdout is None:
                reader_done.set()
                return
            while True:
                chunk = process.stdout.read(1024)
                if not chunk:
                    break
                output_chunks.append(chunk)
            reader_done.set()

        threading.Thread(target=drain_output, daemon=True).start()

        last_bytes = 0
        last_ts = time.time()
        while process.poll() is None:
            current_bytes = self.get_remote_file_size(serial, temp_remote_path)
            now = time.time()
            delta_t = max(now - last_ts, 0.001)
            speed = max(current_bytes - last_bytes, 0) / delta_t
            last_bytes = current_bytes
            last_ts = now
            if progress_cb:
                progress_cb(current_bytes, total_bytes, speed, "uploading", "")
            time.sleep(1.0)

        reader_done.wait(timeout=5)
        if process.returncode != 0:
            output = b"".join(output_chunks).decode("utf-8", errors="replace").strip()
            raise ADBError(output or f"adb push failed with exit code {process.returncode}")

        self.replace_remote_file(serial, temp_remote_path, final_remote_path)
        if progress_cb:
            progress_cb(total_bytes, total_bytes, 0.0, "verifying", "rename complete")
        return final_remote_path

    def verify_remote_file_size(self, serial: str, remote_path: str, expected_size: int) -> bool:
        return self.get_remote_file_size(serial, remote_path) == int(expected_size)

    def resolve_required_files(self, content_root: str, files: List[RequiredFileSpec]) -> List[RequiredFileSpec]:
        root = Path(content_root) if content_root else None
        resolved: List[RequiredFileSpec] = []
        for file_spec in files:
            candidate = Path(file_spec.source_path) if file_spec.source_path else None
            path = candidate if candidate and candidate.exists() else None
            if path is None and root and root.exists():
                direct = root / file_spec.filename
                if direct.exists():
                    path = direct
                else:
                    matches = list(root.rglob(file_spec.filename))
                    if matches:
                        path = matches[0]

            updated = replace(file_spec)
            if path and path.exists():
                updated.source_path = str(path)
                updated.size_bytes = path.stat().st_size
                updated.status = "ready"
                updated.note = ""
            else:
                updated.source_path = ""
                updated.size_bytes = 0
                updated.status = "missing"
                updated.note = "Local file not found"
            resolved.append(updated)
        return resolved


def shell_escape(value: str) -> str:
    return "'" + str(value).replace("'", "'\"'\"'") + "'"
