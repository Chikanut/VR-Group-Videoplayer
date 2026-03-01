import asyncio
import logging
import re
import shlex
import shutil
from collections import defaultdict

logger = logging.getLogger("vrclassroom.adb")

ADB_PORT = 5555
COMMAND_TIMEOUT = 30


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
                while True:
                    line = await asyncio.wait_for(proc.stderr.readline(), timeout=300)
                    if not line:
                        break
                    text = line.decode(errors="replace").strip()
                    output_lines.append(text)
                    # Parse adb push progress: "[ XX%] /path/to/file"
                    match = re.search(r"\[\s*(\d+)%\]", text)
                    if match and progress_callback:
                        pct = int(match.group(1))
                        await progress_callback(pct, text)

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


adb_executor = ADBExecutor()
