"""Network scanner: threaded TCP scan on port 5555 to discover Quest devices."""

import socket
import ipaddress
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from PyQt5.QtCore import QThread, pyqtSignal

import adb_manager


SCAN_PORT = 5555
SCAN_TIMEOUT = 0.5  # seconds per host
MAX_SCAN_WORKERS = 64


@dataclass
class FoundDevice:
    ip: str
    mac: str
    name: str


def get_local_subnet() -> str:
    """Detect local subnet (e.g. '192.168.1.0/24') by inspecting default route."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        # Assume /24
        parts = local_ip.split(".")
        return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
    except Exception:
        return "192.168.1.0/24"


def tcp_check(ip: str, port: int = SCAN_PORT, timeout: float = SCAN_TIMEOUT) -> bool:
    """Check if a TCP port is open on the given IP."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex((ip, port)) == 0
    except Exception:
        return False


def scan_subnet(subnet: str, progress_callback=None) -> list[FoundDevice]:
    """Scan subnet for devices with port 5555 open, then get MAC/name via ADB."""
    network = ipaddress.IPv4Network(subnet, strict=False)
    hosts = [str(h) for h in network.hosts()]
    total = len(hosts)
    open_ips: list[str] = []
    scanned = 0

    with ThreadPoolExecutor(max_workers=MAX_SCAN_WORKERS) as pool:
        futures = {pool.submit(tcp_check, ip): ip for ip in hosts}
        for future in as_completed(futures):
            scanned += 1
            ip = futures[future]
            if progress_callback:
                progress_callback(scanned, total)
            try:
                if future.result():
                    open_ips.append(ip)
            except Exception:
                pass

    devices: list[FoundDevice] = []
    for ip in sorted(open_ips):
        adb_manager.connect(ip)
        name = adb_manager.get_device_name(ip)
        # Use IP as identifier since MAC is not always accessible
        devices.append(FoundDevice(ip=ip, mac=ip, name=name))

    return devices


def resolve_ip_by_mac(target_mac: str, subnet: str | None = None) -> str | None:
    """Try to find current IP for a given MAC via ARP table or mini-scan."""
    target_mac = target_mac.lower().strip()

    # 1. Check ARP table first (fast)
    try:
        import subprocess
        proc = subprocess.run(["ip", "neigh"], capture_output=True, text=True, timeout=3)
        for line in proc.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 5:
                ip_addr = parts[0]
                mac_match = re.search(r"([0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2})", line.lower())
                if mac_match and mac_match.group(1) == target_mac:
                    if tcp_check(ip_addr):
                        return ip_addr
    except Exception:
        pass

    # 2. Mini-scan as fallback
    if subnet is None:
        subnet = get_local_subnet()
    network = ipaddress.IPv4Network(subnet, strict=False)
    hosts = [str(h) for h in network.hosts()]

    with ThreadPoolExecutor(max_workers=MAX_SCAN_WORKERS) as pool:
        futures = {pool.submit(tcp_check, ip): ip for ip in hosts}
        for future in as_completed(futures):
            ip = futures[future]
            try:
                if future.result():
                    adb_manager.connect(ip)
                    mac = adb_manager.get_mac(ip)
                    if mac == target_mac:
                        return ip
            except Exception:
                pass

    return None


class ScanWorker(QThread):
    """QThread wrapper for subnet scanning with progress signals."""
    progress = pyqtSignal(int, int)  # scanned, total
    finished_signal = pyqtSignal(list)  # list of FoundDevice

    def __init__(self, subnet: str | None = None, parent=None):
        super().__init__(parent)
        self.subnet = subnet or get_local_subnet()

    def run(self):
        devices = scan_subnet(self.subnet, progress_callback=self._on_progress)
        self.finished_signal.emit(devices)

    def _on_progress(self, scanned: int, total: int):
        self.progress.emit(scanned, total)
