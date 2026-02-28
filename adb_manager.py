"""Wrapper around CLI adb for Meta Quest device management."""

import subprocess
import re


ADB_PORT = 5555
ADB_TIMEOUT = 5  # seconds


def _run(args: list[str], timeout: int = ADB_TIMEOUT) -> tuple[int, str, str]:
    """Run a subprocess and return (returncode, stdout, stderr)."""
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except FileNotFoundError:
        return -1, "", "adb not found"


def _target(ip: str) -> str:
    """Format ip:port target string."""
    return f"{ip}:{ADB_PORT}"


def connect(ip: str) -> bool:
    """Connect to device via adb. Returns True on success."""
    rc, out, _ = _run(["adb", "connect", _target(ip)])
    return rc == 0 and "connected" in out.lower()


def disconnect(ip: str) -> bool:
    """Disconnect from device. Returns True on success."""
    rc, _, _ = _run(["adb", "disconnect", _target(ip)])
    return rc == 0


def exec_command(ip: str, cmd: str) -> str:
    """Execute shell command on device. Returns stdout."""
    _, out, err = _run(["adb", "-s", _target(ip), "shell", cmd], timeout=10)
    return out if out else err


def get_battery(ip: str) -> int:
    """Get battery level percentage. Returns -1 on failure."""
    out = exec_command(ip, "dumpsys battery | grep level")
    match = re.search(r"level:\s*(\d+)", out)
    return int(match.group(1)) if match else -1


def get_device_name(ip: str) -> str:
    """Get device model name."""
    out = exec_command(ip, "getprop ro.product.model")
    return out if out else "Unknown"


def get_mac(ip: str) -> str:
    """Get WiFi MAC address of the device."""
    out = exec_command(ip, "cat /sys/class/net/wlan0/address")
    out = out.strip().lower()
    if re.match(r"([0-9a-f]{2}:){5}[0-9a-f]{2}", out):
        return out
    # Fallback: ip link
    out = exec_command(ip, "ip link show wlan0")
    match = re.search(r"link/ether\s+([0-9a-f:]{17})", out.lower())
    return match.group(1) if match else ""


def is_online(ip: str) -> bool:
    """Check if device is reachable via adb."""
    rc, out, _ = _run(["adb", "-s", _target(ip), "get-state"], timeout=3)
    return rc == 0 and "device" in out.lower()
