import re
import subprocess
from typing import Optional

ADB_PORT = 5555


class AdbManager:
    def __init__(self, adb_path: str = "adb") -> None:
        self.adb_path = adb_path

    def _run(self, args: list[str], timeout: int = 10) -> subprocess.CompletedProcess:
        return subprocess.run(
            [self.adb_path, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def connect(self, ip: str) -> bool:
        result = self._run(["connect", f"{ip}:{ADB_PORT}"])
        output = (result.stdout + result.stderr).lower()
        return "connected" in output or "already connected" in output

    def disconnect(self, ip: str) -> bool:
        result = self._run(["disconnect", f"{ip}:{ADB_PORT}"])
        return result.returncode == 0

    def exec_command(self, ip: str, cmd: str, timeout: int = 15) -> str:
        result = self._run(["-s", f"{ip}:{ADB_PORT}", "shell", cmd], timeout=timeout)
        if result.returncode != 0:
            stderr = result.stderr.strip() or "Unknown adb shell error"
            return f"ERROR: {stderr}"
        return result.stdout.strip()

    def get_battery(self, ip: str) -> int:
        output = self.exec_command(ip, "dumpsys battery | grep level")
        match = re.search(r"(\d+)", output)
        return int(match.group(1)) if match else -1

    def get_device_name(self, ip: str) -> str:
        output = self.exec_command(ip, "getprop ro.product.model")
        return output.strip() or "Unknown Device"

    def get_mac(self, ip: str) -> str:
        output = self.exec_command(ip, "cat /sys/class/net/wlan0/address")
        mac_match = re.search(r"([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", output)
        if mac_match:
            return mac_match.group(0).lower()

        fallback = self.exec_command(ip, "ip link show wlan0")
        mac_match = re.search(r"link/ether\s+(([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2})", fallback)
        return mac_match.group(1).lower() if mac_match else ""

    def is_online(self, ip: str) -> bool:
        result = self._run(["-s", f"{ip}:{ADB_PORT}", "get-state"], timeout=6)
        return result.returncode == 0 and "device" in result.stdout.lower()

    def resolve_ip_by_mac_arp(self, target_mac: str) -> Optional[str]:
        arp = subprocess.run(["arp", "-an"], capture_output=True, text=True, check=False)
        mac = target_mac.lower()
        for line in arp.stdout.splitlines():
            if mac in line.lower():
                match = re.search(r"\((\d+\.\d+\.\d+\.\d+)\)", line)
                if match:
                    return match.group(1)
        return None
