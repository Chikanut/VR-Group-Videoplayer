import ipaddress
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from adb_manager import AdbManager


def _is_port_open(ip: str, port: int = 5555, timeout: float = 0.3) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((ip, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def scan_subnet(
    subnet: str,
    adb_manager: AdbManager,
    max_workers: int = 64,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[dict]:
    network = ipaddress.ip_network(subnet, strict=False)
    hosts = [str(ip) for ip in network.hosts()]
    total = len(hosts)
    scanned = 0
    results: list[dict] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_is_port_open, host): host for host in hosts}
        for future in as_completed(futures):
            ip = futures[future]
            scanned += 1
            if progress_callback:
                progress_callback(scanned, total)
            if not future.result():
                continue

            if not adb_manager.connect(ip):
                continue
            mac = adb_manager.get_mac(ip)
            name = adb_manager.get_device_name(ip)
            results.append({"ip": ip, "mac": mac, "name": name})

    unique: dict[str, dict] = {}
    for item in results:
        unique[item["mac"]] = item
    return list(unique.values())
