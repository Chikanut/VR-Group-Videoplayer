import asyncio
import logging
import re
import socket
from typing import Callable

import aiohttp

from .adb_executor import ADB_PORT, adb_executor
from .config import get_config
from .device_manager import device_manager

logger = logging.getLogger("vrclassroom.discovery")


def detect_subnet() -> str:
    """Try to detect the local subnet for scanning."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        parts = ip.split(".")
        return f"{parts[0]}.{parts[1]}.{parts[2]}"
    except Exception:
        return "192.168.1"


async def scan_ip(ip: str) -> str | None:
    """Try to connect to ADB on a single IP. Returns IP if successful."""
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, ADB_PORT),
            timeout=2,
        )
        writer.close()
        await writer.wait_closed()
        return ip
    except (asyncio.TimeoutError, OSError, ConnectionRefusedError):
        return None


async def scan_subnet(subnet: str) -> list[str]:
    """Scan a /24 subnet for devices with ADB port open."""
    logger.info("Scanning subnet %s.0/24...", subnet)
    tasks = [scan_ip(f"{subnet}.{i}") for i in range(1, 255)]
    results = await asyncio.gather(*tasks)
    found = [ip for ip in results if ip is not None]
    logger.info("Scan complete. Found %d device(s) with ADB port open", len(found))
    return found


async def _check_player_http(ip: str, player_port: int, max_retries: int = 2) -> dict | None:
    """Check if player HTTP server responds, with retries for Quest 3 startup delay."""
    for attempt in range(max_retries + 1):
        try:
            async with aiohttp.ClientSession() as session:
                url = f"http://{ip}:{player_port}/status"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception:
            if attempt < max_retries:
                await asyncio.sleep(2)
    return None


async def _get_battery_info(ip: str) -> tuple[int, bool]:
    """Extract battery level and charging state from device."""
    battery = -1
    charging = False
    success, bat_output = await adb_executor.shell(ip, "dumpsys battery")
    if success:
        for line in bat_output.splitlines():
            line = line.strip()
            if line.startswith("level:"):
                try:
                    battery = int(line.split(":")[1].strip())
                except (ValueError, IndexError):
                    pass
            elif line.startswith("status:"):
                # 2 = charging, 5 = full
                try:
                    status_val = int(line.split(":")[1].strip())
                    charging = status_val in (2, 5)
                except (ValueError, IndexError):
                    pass
    return battery, charging


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

            discovered_ips = await scan_subnet(subnet)

            for ip in discovered_ips:
                connected = await adb_executor.connect(ip)
                if connected:
                    success, mac_output = await adb_executor.shell(
                        ip, "cat /sys/class/net/wlan0/address"
                    )
                    device_id = mac_output.strip().replace(":", "") if success and mac_output.strip() else ip

                    battery, charging = await _get_battery_info(ip)

                    packages = await adb_executor.list_packages(ip)
                    package_id = config.get("packageId", "com.vrclassroom.player")
                    player_installed = package_id in packages

                    await device_manager.add_or_update(
                        device_id,
                        ip,
                        adb_connected=True,
                        battery=battery,
                        battery_charging=charging,
                        installed_packages=packages,
                    )

                    # Try to connect to player HTTP with retries
                    if player_installed:
                        player_port = config.get("playerPort", 8080)
                        data = await _check_player_http(ip, player_port)
                        if data:
                            await device_manager.add_or_update(
                                device_id,
                                ip,
                                player_connected=True,
                                player_version=data.get("playerVersion", data.get("version", "")),
                                playback_state=data.get("state", "idle"),
                                current_video=data.get("file", ""),
                                current_mode=data.get("mode", "360"),
                                playback_time=data.get("time", 0.0),
                                playback_duration=data.get("duration", 0.0),
                                loop=data.get("loop", False),
                                locked=data.get("locked", False),
                                uptime_minutes=data.get("uptimeMinutes", 0),
                            )
                        else:
                            # Player installed but not responding - try launching it
                            logger.info("Player installed but not responding on %s, attempting launch", ip)
                            await adb_executor.shell(
                                ip,
                                f"monkey -p {package_id} -c android.intent.category.LAUNCHER 1"
                            )
                            # Wait for app to start and retry
                            await asyncio.sleep(5)
                            data = await _check_player_http(ip, player_port, max_retries=3)
                            if data:
                                await device_manager.add_or_update(
                                    device_id,
                                    ip,
                                    player_connected=True,
                                    player_version=data.get("playerVersion", data.get("version", "")),
                                    playback_state=data.get("state", "idle"),
                                    current_video=data.get("file", ""),
                                    current_mode=data.get("mode", "360"),
                                    playback_time=data.get("time", 0.0),
                                    playback_duration=data.get("duration", 0.0),
                                    loop=data.get("loop", False),
                                    locked=data.get("locked", False),
                                    uptime_minutes=data.get("uptimeMinutes", 0),
                                )
                            else:
                                logger.warning("Player on %s not responding after launch attempt", ip)
                else:
                    logger.debug("ADB port open on %s but connect failed", ip)

            # Also scan for USB devices
            await _scan_usb_devices()

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
            # Get MAC for device_id
            success, mac_output = await adb_executor.run_on_serial(
                serial, ["shell", "cat", "/sys/class/net/wlan0/address"]
            )
            device_id = mac_output.strip().replace(":", "") if success and mac_output.strip() else f"usb_{serial}"

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
    """Handle self-registration from a player device."""
    device_id = data["deviceId"]
    ip = data["ip"]

    await device_manager.add_or_update(
        device_id,
        ip,
        battery=data.get("battery", -1),
        player_connected=True,
        player_version=data.get("playerVersion", ""),
        installed_packages=data.get("installedPackages", []),
    )

    device = await device_manager.get(device_id)
    if device and not device.adb_connected:
        connected = await adb_executor.connect(ip)
        if connected:
            await device_manager.add_or_update(device_id, ip, adb_connected=True)
