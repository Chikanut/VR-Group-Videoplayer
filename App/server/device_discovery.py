import asyncio
import logging
import socket

from .adb_executor import ADB_PORT, adb_executor
from .config import get_config
from .device_manager import device_manager

logger = logging.getLogger("vrclassroom.discovery")

DISCOVERY_CONCURRENCY = 8


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


async def process_discovered_ip(
    ip: str,
    semaphore: asyncio.Semaphore,
):
    """Minimal discovery: connect ADB + read ID + register. That's all."""
    async with semaphore:
        connected = await adb_executor.connect(ip)
        if not connected:
            logger.debug("ADB port open on %s but connect failed", ip)
            return

        device_id = await _read_stable_id_from_adb(ip)

        await device_manager.add_or_update(
            device_id,
            ip,
            adb_connected=True,
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

            discovered_ips = await scan_subnet(subnet)

            semaphore = asyncio.Semaphore(DISCOVERY_CONCURRENCY)
            tasks = [process_discovered_ip(ip, semaphore) for ip in discovered_ips]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    logger.warning("Device processing failed: %s", result)

            # Also scan for USB devices
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
