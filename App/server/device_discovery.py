import asyncio
import logging
import socket
from typing import Dict, List, Optional

import aiohttp

from .config import PLAYER_HTTP_PORT, get_config
from .device_manager import device_manager
from .device_ws_manager import device_ws_manager

logger = logging.getLogger("vrclassroom.discovery")

DISCOVERY_CONCURRENCY = 24
SCAN_TIMEOUT_SEC = 0.8

_STATUS_FIELD_MAP = {
    "state": "playback_state",
    "file": "current_video",
    "mode": "current_mode",
    "time": "playback_time",
    "duration": "playback_duration",
    "battery": "battery",
    "batteryCharging": "battery_charging",
    "locked": "locked",
    "loop": "loop",
    "uptimeMinutes": "uptime_minutes",
    "playerVersion": "player_version",
    "androidId": "android_id",
    "android_id": "android_id",
    "deviceModel": "device_model",
    "model": "device_model",
    "macAddress": "mac_address",
    "mac": "mac_address",
    "personalVolume": "personal_volume",
    "effectiveVolume": "effective_volume",
}


def detect_subnet() -> str:
    """Try to detect the local subnet for scanning."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        parts = ip.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.{parts[2]}"
    except Exception:
        logger.debug("Failed to auto-detect subnet", exc_info=True)
    return "192.168.1"


async def scan_ip(ip: str, port: int, timeout: float = SCAN_TIMEOUT_SEC) -> Optional[str]:
    """Try to connect to a TCP port on a single IP. Returns IP if successful."""
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port),
            timeout=timeout,
        )
        writer.close()
        await writer.wait_closed()
        return ip
    except (asyncio.TimeoutError, OSError, ConnectionRefusedError):
        return None


async def scan_subnet(subnet: str, port: int, preferred_ips: Optional[List[str]] = None) -> List[str]:
    """Scan a /24 subnet for devices with a given port open."""
    preferred_ips = preferred_ips or []
    preferred_in_subnet = [ip for ip in preferred_ips if ip.startswith(f"{subnet}.")]

    scan_order: List[str] = []
    seen = set()

    for ip in preferred_in_subnet:
        if ip not in seen:
            scan_order.append(ip)
            seen.add(ip)

    for i in range(1, 255):
        ip = f"{subnet}.{i}"
        if ip not in seen:
            scan_order.append(ip)

    logger.info("Scanning subnet %s.0/24 on port %d...", subnet, port)

    semaphore = asyncio.Semaphore(DISCOVERY_CONCURRENCY)

    async def scan_with_limit(ip: str):
        async with semaphore:
            return await scan_ip(ip, port)

    results = await asyncio.gather(*[scan_with_limit(ip) for ip in scan_order])
    found = [ip for ip in results if ip is not None]
    logger.info("Scan complete. Found %d device(s) with port %d open", len(found), port)
    return found


async def _probe_player_http(ip: str) -> Optional[Dict]:
    """Try to reach the player's HTTP API. Returns status dict or None."""
    try:
        async with aiohttp.ClientSession() as session:
            url = f"http://{ip}:{PLAYER_HTTP_PORT}/status"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=2)) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception:
        return None
    return None


async def _push_server_ip_to_player(ip: str, server_url: str):
    """Push the server's IP:port to the player so it can connect via WebSocket."""
    try:
        async with aiohttp.ClientSession() as session:
            url = f"http://{ip}:{PLAYER_HTTP_PORT}/server-ip"
            async with session.put(
                url,
                json={"serverIp": server_url},
                timeout=aiohttp.ClientTimeout(total=3),
            ) as resp:
                if resp.status != 200:
                    logger.debug("Failed to push server IP to %s: HTTP %d", ip, resp.status)
    except Exception as exc:
        logger.debug("Failed to push server IP to %s: %s", ip, exc)


def _get_server_url() -> str:
    """Get the server's own IP:port for devices to connect back."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        config = get_config()
        port = config.get("serverPort", 8000)
        return f"{ip}:{port}"
    except Exception:
        return ""


async def process_discovered_ip(ip: str, semaphore: asyncio.Semaphore):
    """Discovery: probe HTTP player and refresh device state."""
    async with semaphore:
        status = await _probe_player_http(ip)
        if status is None:
            return

        device_id = (
            str(status.get("deviceId", "")).strip()
            or str(status.get("androidId", "")).strip()
            or str(status.get("android_id", "")).strip()
            or ip
        )

        extra_kwargs = {}
        for json_key, attr_name in _STATUS_FIELD_MAP.items():
            if json_key in status:
                extra_kwargs[attr_name] = status[json_key]

        if not device_ws_manager.is_connected(device_id):
            server_url = _get_server_url()
            if server_url:
                asyncio.create_task(_push_server_ip_to_player(ip, server_url))

        await device_manager.add_or_update(
            device_id,
            ip,
            player_connected=True,
            **extra_kwargs,
        )
        await device_manager.mark_discovery_seen(device_id)

        device_name = str(status.get("deviceName", "")).strip()
        if device_name:
            await device_manager.apply_device_name_from_device(device_id, device_name)

        from .requirements_manager import check_requirements

        await check_requirements(device_id)


async def discovery_loop():
    """Background task that periodically scans the network for devices."""
    await asyncio.sleep(3)

    while True:
        try:
            config = get_config()
            interval = config.get("scanInterval", 30)
            subnet = config.get("networkSubnet", "") or detect_subnet()

            await device_manager.increment_missed_discovery()

            known_ips = await device_manager.get_known_ips()
            discovered_ips = await scan_subnet(subnet, PLAYER_HTTP_PORT, preferred_ips=known_ips)

            semaphore = asyncio.Semaphore(DISCOVERY_CONCURRENCY)
            tasks = [process_discovered_ip(ip, semaphore) for ip in discovered_ips]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    logger.warning("Device processing failed: %s", result)

            logger.info("Discovery complete: discovered=%d", len(discovered_ips))
            await asyncio.sleep(interval)

        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("Discovery loop error: %s", exc)
            await asyncio.sleep(10)


async def handle_self_registration(data: dict):
    """Handle self-registration from a player device (legacy HTTP endpoint)."""
    try:
        ip = str(data.get("ip", "")).strip()
        incoming_device_id = str(data.get("deviceId", "")).strip()
        if not incoming_device_id or not ip:
            logger.warning(
                "Skipping self-registration: invalid payload deviceId=%r ip=%r",
                data.get("deviceId"),
                data.get("ip"),
            )
            return

        await device_manager.add_or_update(
            incoming_device_id,
            ip=ip,
            battery=data.get("battery", -1),
            player_connected=True,
            player_version=data.get("playerVersion", ""),
        )

        device_name = str(data.get("deviceName", "")).strip()
        if device_name:
            await device_manager.apply_device_name_from_device(incoming_device_id, device_name)

        from .requirements_manager import check_requirements

        await check_requirements(incoming_device_id)
    except Exception:
        logger.exception("Self-registration handling failed. payload=%s", data)
