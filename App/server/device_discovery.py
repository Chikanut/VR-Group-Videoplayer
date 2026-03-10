import asyncio
import logging
import socket

import aiohttp
from typing import Dict, List, Optional

from .adb_executor import ADB_PORT, adb_executor
from .config import ADB_AVAILABLE, detect_android_hotspot_subnet, get_config
from .device_manager import device_manager
from .device_ws_manager import device_ws_manager

logger = logging.getLogger("vrclassroom.discovery")

DISCOVERY_CONCURRENCY = 32


def detect_subnet() -> str:
    """Try to detect the local subnet for scanning."""
    if not ADB_AVAILABLE:
        return detect_android_hotspot_subnet()

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        parts = ip.split(".")
        return f"{parts[0]}.{parts[1]}.{parts[2]}"
    except Exception:
        return "192.168.1"


async def scan_ip(ip: str, port: int, timeout_s: float = 2.0) -> Optional[str]:
    """Try to connect to a TCP port on a single IP. Returns IP if successful."""
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port),
            timeout=timeout_s,
        )
        writer.close()
        await writer.wait_closed()
        return ip
    except (asyncio.TimeoutError, OSError, ConnectionRefusedError):
        return None


async def scan_subnet(subnet: str, port: int, timeout_s: float = 2.0) -> List[str]:
    """Scan a /24 subnet for devices with a given port open."""
    logger.info("Scanning subnet %s.0/24 on port %d...", subnet, port)
    semaphore = asyncio.Semaphore(DISCOVERY_CONCURRENCY)

    async def scan_with_limit(candidate_ip: str):
        async with semaphore:
            return await scan_ip(candidate_ip, port, timeout_s=timeout_s)

    tasks = [scan_with_limit(f"{subnet}.{i}") for i in range(1, 255)]
    results = await asyncio.gather(*tasks)
    found = [ip for ip in results if ip is not None]
    logger.info("Scan complete. Found %d device(s) with port %d open", len(found), port)
    return found


async def _read_stable_id_from_adb(ip: str) -> str:
    """Get the best available stable ID from Android via ADB."""
    success, android_id = await adb_executor.shell(ip, "settings get secure android_id")
    if success:
        value = android_id.strip()
        if value and value.lower() != "null":
            return value

    success, serial = await adb_executor.shell(ip, "getprop ro.serialno")
    if success:
        value = serial.strip()
        if value and value.lower() != "unknown":
            return value

    logger.warning("Could not read android_id or serial from %s, using IP as fallback", ip)
    return ip


async def _probe_player_http(ip: str, player_port: int) -> Optional[Dict]:
    """Try to reach the player's HTTP API on port 8080. Returns status dict or None."""
    try:
        async with aiohttp.ClientSession() as session:
            url = f"http://{ip}:{player_port}/status"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception:
        pass
    return None


async def _push_server_ip_to_player(ip: str, player_port: int, server_url: str):
    """Push the server's IP:port to the player so it can connect via WebSocket."""
    try:
        async with aiohttp.ClientSession() as session:
            url = f"http://{ip}:{player_port}/server-ip"
            async with session.put(
                url,
                json={"serverIp": server_url},
                timeout=aiohttp.ClientTimeout(total=3),
            ) as resp:
                if resp.status == 200:
                    logger.info("Pushed server IP %s to device %s", server_url, ip)
                else:
                    logger.debug("Failed to push server IP to %s: HTTP %d", ip, resp.status)
    except Exception as e:
        logger.debug("Failed to push server IP to %s: %s", ip, e)


def _get_server_url() -> str:
    """Get the server's own IP:port for devices to connect back."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        config = get_config()
        port = config.get("serverPort", 8000)
        return f"{ip}:{port}"
    except Exception:
        return ""


_STATUS_FIELD_MAP = {
    "state": "playback_state",
    "file": "current_video",
    "mode": "current_mode",
    "time": "playback_time",
    "duration": "playback_duration",
    "battery": "battery",
    "batteryCharging": "battery_charging",
    "loop": "loop",
    "uptimeMinutes": "uptime_minutes",
    "playerVersion": "player_version",
    "androidId": "android_id",
    "android_id": "android_id",
    "deviceModel": "device_model",
    "model": "device_model",
    "macAddress": "mac_address",
    "mac": "mac_address",
    "packages": "installed_packages",
}


async def process_discovered_ip(
    ip: str,
    semaphore: asyncio.Semaphore,
):
    """Discovery: probe HTTP player and optionally enrich with ADB."""
    async with semaphore:
        config = get_config()
        player_port = config.get("playerPort", 8080)

        status = await _probe_player_http(ip, player_port)
        if status is None:
            return

        device_id = str(status.get("deviceId", "")).strip() or ip
        extra_kwargs = {}
        for json_key, attr_name in _STATUS_FIELD_MAP.items():
            if json_key in status:
                extra_kwargs[attr_name] = status[json_key]

        if "androidId" in status:
            device_id = str(status.get("androidId") or device_id)
        if "android_id" in status:
            device_id = str(status.get("android_id") or device_id)
        if "packages" in status and isinstance(status.get("packages"), list):
            extra_kwargs["installed_packages"] = status.get("packages")

        adb_connected = False
        if ADB_AVAILABLE:
            adb_connected = await adb_executor.connect(ip)
            if adb_connected:
                device_id = await _read_stable_id_from_adb(ip)

        if not device_ws_manager.is_connected(device_id):
            server_url = _get_server_url()
            if server_url:
                asyncio.create_task(_push_server_ip_to_player(ip, player_port, server_url))

        await device_manager.add_or_update(
            device_id,
            ip,
            adb_connected=adb_connected,
            player_connected=True,
            **extra_kwargs,
        )
        await device_manager.mark_discovery_seen(device_id)


async def discovery_loop():
    """Background task that periodically scans the network for devices."""
    await asyncio.sleep(3)

    while True:
        try:
            config = get_config()
            interval = config.get("scanInterval", 30)

            subnet = config.get("networkSubnet", "")
            if not subnet:
                subnet = detect_subnet()

            # Increment missed cycles for all known devices before scanning
            await device_manager.increment_missed_discovery()

            player_port = config.get("playerPort", 8080)
            discovery_port = ADB_PORT if ADB_AVAILABLE else player_port
            timeout_s = 0.8 if not ADB_AVAILABLE else 1.5
            discovered_ips = await scan_subnet(subnet, discovery_port, timeout_s=timeout_s)

            semaphore = asyncio.Semaphore(DISCOVERY_CONCURRENCY)
            tasks = [process_discovered_ip(ip, semaphore) for ip in discovered_ips]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    logger.warning("Device processing failed: %s", result)

            # Also scan for USB devices
            if ADB_AVAILABLE:
                await _scan_usb_devices()

            logger.info("Discovery complete: discovered=%d", len(discovered_ips))

            await asyncio.sleep(interval)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Discovery loop error: %s", e)
            await asyncio.sleep(10)


async def _scan_usb_devices():
    """Detect USB-connected devices and add them to device manager."""
    try:
        usb_serials = await adb_executor.list_usb_devices()
        for serial in usb_serials:
            success, android_id_output = await adb_executor.run_on_serial(
                serial, ["shell", "settings", "get", "secure", "android_id"]
            )
            android_id = android_id_output.strip() if success else ""
            if android_id and android_id.lower() != "null":
                device_id = android_id
            else:
                device_id = serial

            ip = await adb_executor.get_usb_device_ip(serial)

            await device_manager.add_or_update(
                device_id,
                ip or "USB",
                adb_connected=True,
                usb_connected=True,
            )
    except Exception as e:
        logger.debug("USB scan error: %s", e)


async def handle_self_registration(data: dict):
    """Handle self-registration from a player device (legacy HTTP endpoint)."""
    try:
        ip = str(data.get("ip", "")).strip()
        incoming_device_id = str(data.get("deviceId", "")).strip()
        if not incoming_device_id or not ip:
            logger.warning("Skipping self-registration: invalid payload deviceId=%r ip=%r", data.get("deviceId"), data.get("ip"))
            return

        await device_manager.add_or_update(
            incoming_device_id,
            ip=ip,
            battery=data.get("battery", -1),
            player_connected=True,
            player_version=data.get("playerVersion", ""),
        )

        device_name = data.get("deviceName", "")
        if device_name:
            await device_manager.apply_device_name_from_device(incoming_device_id, device_name)

        # Try ADB connect if not already connected
        if ADB_AVAILABLE:
            device = await device_manager.get(incoming_device_id)
            if device and not device.adb_connected:
                connected = await adb_executor.connect(ip)
                if connected:
                    await device_manager.add_or_update(
                        incoming_device_id,
                        ip=ip,
                        adb_connected=True,
                    )
    except Exception:
        logger.exception("Self-registration handling failed. payload=%s", data)
