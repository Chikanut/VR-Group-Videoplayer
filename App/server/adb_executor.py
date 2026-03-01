import asyncio
import logging
import re
import shlex
import shutil
from collections import defaultdict

logger = logging.getLogger("vrclassroom.adb")

ADB_PORT = 5555
COMMAND_TIMEOUT = 50


class ADBExecutor:
    def __init__(self):
        self._device_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._adb_path: str | None = None

    async def check_adb(self) -> bool:
        self._adb_path = shutil.which("adb")
        if self._adb_path:
            logger.info("ADB found at: %s", self._adb_path)
            return True
        logger.error("ADB not found in PATH")
        return False

    def _adb_cmd(self) -> str:
        return self._adb_path or "adb"

    async def _run(self, ip: str, args: list[str], timeout: int = COMMAND_TIMEOUT) -> tuple[bool, str]:
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

    async def install_apk(self, ip: str, apk_path: str) -> tuple[bool, str]:
        return await self._run(ip, ["install", "-r", apk_path], timeout=120)

    async def push_file(self, ip: str, local_path: str, device_path: str) -> tuple[bool, str]:
        return await self._run(ip, ["push", local_path, device_path], timeout=600)

    async def push_file_with_progress(self, ip: str, local_path: str, device_path: str,
                                       progress_callback=None) -> tuple[bool, str]:
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
                # ADB push progress uses \r (carriage return), not \n
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
                    # Split on \r or \n to catch progress updates
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

                # Process remaining buffer
                if buffer.strip():
                    text = buffer.decode(errors="replace").strip()
                    output_lines.append(text)
                    match = re.search(r"\[\s*(\d+)%\]", text)
                    if match and progress_callback:
                        await progress_callback(int(match.group(1)), text)

                await proc.wait()
                stdout_data = await proc.stdout.read()
                full_output = "\n".join(output_lines) + "\n" + stdout_data.decode(errors="replace")
                return proc.returncode == 0, full_output.strip()
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except Exception:
                    pass
                return False, "Push timed out"
            except Exception as e:
                return False, str(e)

    async def list_packages(self, ip: str) -> list[str]:
        success, output = await self._run(ip, ["shell", "pm", "list", "packages"])
        if not success:
            return []
        packages = []
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("package:"):
                packages.append(line[8:])
        return packages

    async def file_exists(self, ip: str, device_path: str) -> bool:
        success, output = await self._run(ip, ["shell", "ls", device_path])
        return success and "No such file" not in output

    async def get_file_size(self, ip: str, device_path: str) -> int:
        success, output = await self._run(ip, ["shell", "stat", "-c", "%s", device_path])
        if success:
            try:
                return int(output.strip())
            except ValueError:
                pass
        return -1

    async def shell(self, ip: str, command: str) -> tuple[bool, str]:
        return await self._run(ip, ["shell"] + shlex.split(command))

    async def ensure_directory(self, ip: str, device_path: str) -> bool:
        import os
        dir_path = os.path.dirname(device_path)
        if dir_path:
            success, _ = await self._run(ip, ["shell", "mkdir", "-p", dir_path])
            return success
        return True

    async def scan_media_file(self, ip: str, device_path: str) -> str:
        """Ask Android media scanner to index a file."""
        # Escape single quotes in path
        escaped = device_path.replace("'", "'\\''")
        file_uri = f"file://{device_path}"
        escaped_uri = file_uri.replace("'", "'\\''")

        outputs = []
        # Method 1: broadcast intent
        success, out = await self._run(
            ip,
            ["shell", "am", "broadcast", "-a",
             "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
             "-d", escaped_uri],
        )
        if out:
            outputs.append(out)

        # Method 2: media.scan service (newer Android)
        success2, out2 = await self._run(
            ip,
            ["shell", "cmd", "media.scan", escaped],
        )
        if out2 and "can't find service" not in out2.lower():
            outputs.append(out2)

        # Method 3: content provider insert
        success3, out3 = await self._run(
            ip,
            ["shell", "content", "insert", "--uri",
             "content://media/external/file",
             "--bind", f"_data:s:{device_path}"],
        )
        if out3:
            outputs.append(out3)

        return " | ".join(chunk for chunk in outputs if chunk)

    async def get_package_version(self, ip: str, package_id: str) -> str | None:
        """Get installed package version on device."""
        success, output = await self._run(
            ip, ["shell", "dumpsys", "package", package_id]
        )
        if not success:
            return None
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("versionName="):
                return line.split("=", 1)[1].strip()
        return None

    async def get_local_apk_version(self, apk_path: str) -> str | None:
        """Get version from a local APK file using aapt or aapt2."""
        import shutil as _shutil
        for tool in ("aapt2", "aapt"):
            tool_path = _shutil.which(tool)
            if not tool_path:
                continue
            try:
                if tool == "aapt2":
                    proc = await asyncio.create_subprocess_exec(
                        tool_path, "dump", "badging", apk_path,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                else:
                    proc = await asyncio.create_subprocess_exec(
                        tool_path, "dump", "badging", apk_path,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
                for line in stdout.decode(errors="replace").splitlines():
                    if line.startswith("package:"):
                        match = re.search(r"versionName='([^']+)'", line)
                        if match:
                            return match.group(1)
            except Exception:
                continue
        return None

    async def list_usb_devices(self) -> list[str]:
        """List ADB devices connected via USB."""
        try:
            proc = await asyncio.create_subprocess_exec(
                self._adb_cmd(), "devices", "-l",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            output = stdout.decode(errors="replace")
            usb_devices = []
            for line in output.splitlines():
                line = line.strip()
                if not line or line.startswith("List"):
                    continue
                # USB devices show serial numbers (not ip:port format)
                parts = line.split()
                if len(parts) >= 2 and parts[1] == "device":
                    serial = parts[0]
                    if ":" not in serial:  # USB device (no ip:port)
                        usb_devices.append(serial)
            return usb_devices
        except Exception:
            return []

    async def get_usb_device_ip(self, serial: str) -> str | None:
        """Get the IP address of a USB-connected device."""
        try:
            proc = await asyncio.create_subprocess_exec(
                self._adb_cmd(), "-s", serial, "shell",
                "ip", "route", "show", "dev", "wlan0",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            output = stdout.decode(errors="replace")
            # Look for "src X.X.X.X" in ip route output
            match = re.search(r"src\s+(\d+\.\d+\.\d+\.\d+)", output)
            if match:
                return match.group(1)
        except Exception:
            pass
        return None

    async def enable_tcpip(self, serial: str) -> bool:
        """Enable ADB over TCP/IP on a USB-connected device."""
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

    async def run_on_serial(self, serial: str, args: list[str], timeout: int = COMMAND_TIMEOUT) -> tuple[bool, str]:
        """Run ADB command targeting a USB serial (not ip:port)."""
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

    async def install_apk_usb(self, serial: str, apk_path: str) -> tuple[bool, str]:
        return await self.run_on_serial(serial, ["install", "-r", apk_path], timeout=120)

    async def push_file_usb_with_progress(self, serial: str, local_path: str, device_path: str,
                                           progress_callback=None) -> tuple[bool, str]:
        """Push file to USB-connected device with progress tracking."""
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
        """Ask Android media scanner to index a file on USB device."""
        file_uri = f"file://{device_path}"
        outputs = []
        success, out = await self.run_on_serial(
            serial,
            ["shell", "am", "broadcast", "-a",
             "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
             "-d", file_uri],
        )
        if out:
            outputs.append(out)
        success2, out2 = await self.run_on_serial(
            serial, ["shell", "cmd", "media.scan", device_path],
        )
        if out2 and "can't find service" not in out2.lower():
            outputs.append(out2)
        success3, out3 = await self.run_on_serial(
            serial,
            ["shell", "content", "insert", "--uri",
             "content://media/external/file",
             "--bind", f"_data:s:{device_path}"],
        )
        if out3:
            outputs.append(out3)
        return " | ".join(chunk for chunk in outputs if chunk)


adb_executor = ADBExecutor()
