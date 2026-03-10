import asyncio
import logging
import re
import shlex
import shutil
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from .config import ADB_AVAILABLE

logger = logging.getLogger("vrclassroom.adb")

ADB_PORT = 5555
COMMAND_TIMEOUT = 50


class ADBExecutor:
    def __init__(self):
        self._device_locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._adb_path: Optional[str] = None

    async def check_adb(self) -> bool:
        self._adb_path = shutil.which("adb")
        if self._adb_path:
            logger.info("ADB found at: %s", self._adb_path)
            return True
        logger.error("ADB not found in PATH")
        return False

    def _adb_cmd(self) -> str:
        return self._adb_path or "adb"

    async def _run(self, ip: str, args: List[str], timeout: int = COMMAND_TIMEOUT) -> Tuple[bool, str]:
        target = f"{ip}:{ADB_PORT}"
        cmd = [self._adb_cmd(), "-s", target] + args
        async with self._device_locks[ip]:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                output = (stdout.decode(errors="replace") + stderr.decode(errors="replace")).strip()
                success = proc.returncode == 0
                if not success:
                    logger.warning("ADB command failed [%s]: %s -> %s", ip, " ".join(args), output[:200])
                return success, output
            except asyncio.TimeoutError:
                logger.error("ADB command timed out [%s]: %s", ip, " ".join(args))
                try:
                    proc.kill()
                except Exception:
                    pass
                return False, "Command timed out"
            except Exception as e:
                logger.error("ADB command error [%s]: %s -> %s", ip, " ".join(args), e)
                return False, str(e)

    async def connect(self, ip: str) -> bool:
        target = f"{ip}:{ADB_PORT}"
        try:
            proc = await asyncio.create_subprocess_exec(
                self._adb_cmd(), "connect", target,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)
            output = (stdout.decode(errors="replace") + stderr.decode(errors="replace")).strip()
            connected = "connected" in output.lower() and "cannot" not in output.lower()
            if connected:
                logger.debug("ADB connected to %s", ip)
            return connected
        except (asyncio.TimeoutError, Exception) as e:
            logger.debug("ADB connect failed for %s: %s", ip, e)
            return False

    async def disconnect(self, ip: str) -> bool:
        target = f"{ip}:{ADB_PORT}"
        try:
            proc = await asyncio.create_subprocess_exec(
                self._adb_cmd(), "disconnect", target,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=5)
            return True
        except Exception:
            return False

    async def is_connected(self, ip: str) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                self._adb_cmd(), "devices",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            output = stdout.decode(errors="replace")
            target = f"{ip}:{ADB_PORT}"
            for line in output.splitlines():
                if target in line and "device" in line and "offline" not in line:
                    return True
            return False
        except Exception:
            return False

    async def install_apk(self, ip: str, apk_path: str) -> Tuple[bool, str]:
        return await self._run(ip, ["install", "-r", apk_path], timeout=120)

    async def push_file(self, ip: str, local_path: str, device_path: str) -> Tuple[bool, str]:
        return await self._run(ip, ["push", local_path, device_path], timeout=600)

    async def push_file_with_progress(self, ip: str, local_path: str, device_path: str,
                                       progress_callback=None) -> Tuple[bool, str]:
        target = f"{ip}:{ADB_PORT}"
        cmd = [self._adb_cmd(), "-s", target, "push", local_path, device_path]
        async with self._device_locks[ip]:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                output_lines = []
                buffer = b""
                last_pct = -1
                while True:
                    try:
                        chunk = await asyncio.wait_for(proc.stderr.read(512), timeout=600)
                    except asyncio.TimeoutError:
                        try:
                            proc.kill()
                        except Exception:
                            pass
                        return False, "Push timed out"
                    if not chunk:
                        break
                    buffer += chunk
                    while b'\r' in buffer or b'\n' in buffer:
                        idx_r = buffer.find(b'\r')
                        idx_n = buffer.find(b'\n')
                        if idx_r == -1:
                            idx = idx_n
                        elif idx_n == -1:
                            idx = idx_r
                        else:
                            idx = min(idx_r, idx_n)
                        line_bytes = buffer[:idx]
                        buffer = buffer[idx + 1:]
                        text = line_bytes.decode(errors="replace").strip()
                        if not text:
                            continue
                        output_lines.append(text)
                        match = re.search(r"\[\s*(\d+)%\]", text)
                        if match and progress_callback:
                            pct = int(match.group(1))
                            if pct != last_pct:
                                last_pct = pct
                                await progress_callback(pct, text)

                if buffer.strip():
                    text = buffer.decode(errors="replace").strip()
                    output_lines.append(text)

                await proc.wait()
                stdout_data = await proc.stdout.read()
                full_output = "\n".join(output_lines) + "\n" + stdout_data.decode(errors="replace")
                return proc.returncode == 0, full_output.strip()
            except Exception as e:
                return False, str(e)

    async def shell(self, ip: str, command: str) -> Tuple[bool, str]:
        return await self._run(ip, ["shell", command], timeout=COMMAND_TIMEOUT)

    async def list_packages(self, ip: str) -> List[str]:
        success, output = await self.shell(ip, "pm list packages")
        if not success:
            return []
        packages = []
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("package:"):
                packages.append(line.replace("package:", ""))
        return packages

    async def file_exists(self, ip: str, device_path: str) -> bool:
        quoted = shlex.quote(device_path)
        success, output = await self.shell(ip, f"test -f {quoted} && echo ok || echo missing")
        return success and "ok" in output

    async def get_package_version(self, ip: str, package_id: str) -> Optional[str]:
        success, output = await self.shell(ip, f"dumpsys package {package_id} | grep versionName")
        if not success:
            return None
        match = re.search(r"versionName=([\w\.-]+)", output)
        return match.group(1) if match else None

    async def get_local_apk_version(self, apk_path: str) -> Optional[str]:
        try:
            proc = await asyncio.create_subprocess_exec(
                self._adb_cmd(), "shell", "aapt", "dump", "badging", apk_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            output = stdout.decode(errors="replace")
            match = re.search(r"versionName='([^']+)'", output)
            if match:
                return match.group(1)
        except Exception:
            pass
        return None

    async def list_usb_devices(self) -> List[str]:
        try:
            proc = await asyncio.create_subprocess_exec(
                self._adb_cmd(), "devices",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            output = stdout.decode(errors="replace")
            serials = []
            for line in output.splitlines()[1:]:
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) >= 2 and parts[1] == "device" and ":" not in parts[0]:
                    serials.append(parts[0])
            return serials
        except Exception:
            return []

    async def get_usb_device_ip(self, serial: str) -> Optional[str]:
        success, output = await self.run_on_serial(
            serial,
            ["shell", "ip", "-f", "inet", "addr", "show", "wlan0"],
        )
        if not success:
            success, output = await self.run_on_serial(
                serial,
                ["shell", "ip", "-f", "inet", "addr", "show"],
            )
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("inet "):
                ip = line.split()[1].split("/")[0]
                if ip and not ip.startswith("127."):
                    return ip
        return None

    async def enable_tcpip(self, serial: str) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                self._adb_cmd(), "-s", serial, "tcpip", str(ADB_PORT),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
            output = (stdout.decode(errors="replace") + stderr.decode(errors="replace")).lower()
            return "restarting" in output or proc.returncode == 0
        except Exception:
            return False

    async def run_on_serial(self, serial: str, args: List[str], timeout: int = COMMAND_TIMEOUT) -> Tuple[bool, str]:
        cmd = [self._adb_cmd(), "-s", serial] + args
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            output = (stdout.decode(errors="replace") + stderr.decode(errors="replace")).strip()
            return proc.returncode == 0, output
        except asyncio.TimeoutError:
            return False, "Command timed out"
        except Exception as e:
            return False, str(e)

    async def install_apk_usb(self, serial: str, apk_path: str) -> Tuple[bool, str]:
        return await self.run_on_serial(serial, ["install", "-r", apk_path], timeout=120)

    async def push_file_usb_with_progress(self, serial: str, local_path: str, device_path: str,
                                           progress_callback=None) -> Tuple[bool, str]:
        cmd = [self._adb_cmd(), "-s", serial, "push", local_path, device_path]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            output_lines = []
            buffer = b""
            last_pct = -1
            while True:
                try:
                    chunk = await asyncio.wait_for(proc.stderr.read(512), timeout=600)
                except asyncio.TimeoutError:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    return False, "Push timed out"
                if not chunk:
                    break
                buffer += chunk
                while b'\r' in buffer or b'\n' in buffer:
                    idx_r = buffer.find(b'\r')
                    idx_n = buffer.find(b'\n')
                    if idx_r == -1:
                        idx = idx_n
                    elif idx_n == -1:
                        idx = idx_r
                    else:
                        idx = min(idx_r, idx_n)
                    line_bytes = buffer[:idx]
                    buffer = buffer[idx + 1:]
                    text = line_bytes.decode(errors="replace").strip()
                    if not text:
                        continue
                    output_lines.append(text)
                    match = re.search(r"\[\s*(\d+)%\]", text)
                    if match and progress_callback:
                        pct = int(match.group(1))
                        if pct != last_pct:
                            last_pct = pct
                            await progress_callback(pct, text)

            if buffer.strip():
                text = buffer.decode(errors="replace").strip()
                output_lines.append(text)

            await proc.wait()
            stdout_data = await proc.stdout.read()
            full_output = "\n".join(output_lines) + "\n" + stdout_data.decode(errors="replace")
            return proc.returncode == 0, full_output.strip()
        except Exception as e:
            return False, str(e)

    async def scan_media_file_usb(self, serial: str, device_path: str) -> str:
        quoted = shlex.quote(device_path)
        file_uri = f"file://{device_path}"
        quoted_uri = shlex.quote(file_uri)
        outputs = []
        success, out = await self.run_on_serial(
            serial,
            ["shell", f"am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d {quoted_uri}"],
        )
        if out:
            outputs.append(out)
        success2, out2 = await self.run_on_serial(
            serial, ["shell", f"cmd media.scan {quoted}"],
        )
        if out2 and "can't find service" not in out2.lower():
            outputs.append(out2)
        quoted_data = shlex.quote(f"_data:s:{device_path}")
        success3, out3 = await self.run_on_serial(
            serial,
            ["shell", f"content insert --uri content://media/external/file --bind {quoted_data}"],
        )
        if out3:
            outputs.append(out3)
        return " | ".join(chunk for chunk in outputs if chunk)


class NoOpADBExecutor:
    async def check_adb(self) -> bool:
        return False

    async def connect(self, ip: str) -> bool:
        return False

    async def disconnect(self, ip: str) -> bool:
        return False

    async def is_connected(self, ip: str) -> bool:
        return False

    async def install_apk(self, ip: str, apk_path: str) -> Tuple[bool, str]:
        return False, "ADB disabled"

    async def push_file(self, ip: str, local_path: str, device_path: str) -> Tuple[bool, str]:
        return False, "ADB disabled"

    async def push_file_with_progress(self, ip: str, local_path: str, device_path: str, progress_callback=None) -> Tuple[bool, str]:
        return False, "ADB disabled"

    async def shell(self, ip: str, command: str) -> Tuple[bool, str]:
        return False, "ADB disabled"

    async def list_packages(self, ip: str) -> List[str]:
        return []

    async def file_exists(self, ip: str, device_path: str) -> bool:
        return False

    async def get_package_version(self, ip: str, package_id: str) -> Optional[str]:
        return None

    async def get_local_apk_version(self, apk_path: str) -> Optional[str]:
        return None

    async def list_usb_devices(self) -> List[str]:
        return []

    async def get_usb_device_ip(self, serial: str) -> Optional[str]:
        return None

    async def enable_tcpip(self, serial: str) -> bool:
        return False

    async def run_on_serial(self, serial: str, args: List[str], timeout: int = COMMAND_TIMEOUT) -> Tuple[bool, str]:
        return False, "ADB disabled"

    async def install_apk_usb(self, serial: str, apk_path: str) -> Tuple[bool, str]:
        return False, "ADB disabled"

    async def push_file_usb_with_progress(self, serial: str, local_path: str, device_path: str, progress_callback=None) -> Tuple[bool, str]:
        return False, "ADB disabled"

    async def scan_media_file_usb(self, serial: str, device_path: str) -> str:
        return ""


def get_adb_executor(adb_available: bool):
    if adb_available:
        return ADBExecutor()
    logger.info("ADB is disabled. Using no-op executor.")
    return NoOpADBExecutor()


adb_executor = get_adb_executor(ADB_AVAILABLE)
