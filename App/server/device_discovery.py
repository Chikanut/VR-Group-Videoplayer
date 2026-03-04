import asyncio
import logging
import socket
import time

import aiohttp

from .adb_executor import ADB_PORT, adb_executor
from .config import get_config
from .device_manager import device_manager

logger = logging.getLogger("vrclassroom.discovery")

# Track IPs where we already attempted a player launch this scan cycle,
# so we don't keep restarting the app every 30s.
_launch_attempted: set[str] = set()

PACKAGE_CACHE_TTL_SECONDS = 90
BATTERY_CACHE_TTL_SECONDS = 30
DISCOVERY_CONCURRENCY = 8

_package_cache: dict[str, dict] = {}
_battery_cache: dict[str, tuple[float, int, bool]] = {}


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
    url = f"http://{ip}:{player_port}/status"
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        last_error = f"HTTP {resp.status}"
                        logger.debug("Player HTTP check %s attempt %d: status %d", ip, attempt + 1, resp.status)
        except Exception as e:
            last_error = str(e)
            logger.debug("Player HTTP check %s attempt %d failed: %s", ip, attempt + 1, e)
            if attempt < max_retries:
                await asyncio.sleep(2)
    if last_error:
        logger.info("Player HTTP not responding on %s after %d attempts: %s", ip, max_retries + 1, last_error)
    return None


async def _get_cached_packages_and_version(ip: str, package_id: str) -> tuple[list[str], str]:
    now = time.time()
    cached = _package_cache.get(ip)
    if cached and now - cached["timestamp"] < PACKAGE_CACHE_TTL_SECONDS:
        return cached["packages"], cached["version"]

    packages = await adb_executor.list_packages(ip)
    version = ""
    if package_id in packages:
        success, version_output = await adb_executor.shell(
            ip,
            f"dumpsys package {package_id} | grep versionName",
        )
        if success:
            for line in version_output.splitlines():
                line = line.strip()
                if line.startswith("versionName="):
                    version = line.split("=", 1)[1].strip()
                    break

    _package_cache[ip] = {
        "timestamp": now,
        "packages": packages,
        "version": version,
    }
    return packages, version




async def _read_stable_id_from_adb(ip: str) -> tuple[str, str]:
    """Get the best available stable ID from Android via ADB."""
    success, android_id = await adb_executor.shell(ip, "settings get secure android_id")
    if success:
        value = android_id.strip()
        if value and value.lower() != "null":
            return value, "android_id"

    success, serial = await adb_executor.shell(ip, "getprop ro.serialno")
    if success:
        value = serial.strip()
        if value and value.lower() != "unknown":
            return value, "android_id"

    success, mac_output = await adb_executor.shell(ip, "cat /sys/class/net/wlan0/address")
    if success:
        mac = mac_output.strip().replace(":", "")
        if mac:
            return mac, "mac"

    return ip, "ip"


async def _resolve_identity(ip: str, player_data: dict | None = None) -> tuple[str, str]:
    """Resolve stable device identity with strict source priority."""
    if player_data:
        player_reported_id = str(player_data.get("deviceId", "")).strip()
        if player_reported_id:
            return player_reported_id, "player"

    return await _read_stable_id_from_adb(ip)




async def _get_autostart_state(ip: str, package_id: str) -> bool | None:
    component = f"{package_id}/.BootCompletedReceiver"
    return await adb_executor.get_component_enabled(ip, component)

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


async def _get_cached_battery_info(ip: str) -> tuple[int, bool]:
    cached = _battery_cache.get(ip)
    if cached and time.time() - cached[0] < BATTERY_CACHE_TTL_SECONDS:
        return cached[1], cached[2]
    return -1, False


async def battery_poll_loop():
    """Poll battery out of discovery to keep discovery fast."""
    await asyncio.sleep(5)

    while True:
        try:
            started_at = time.perf_counter()
            devices = await device_manager.get_all()
            candidates = [d for d in devices if d.get("adbConnected") and d.get("ip") and d.get("ip") != "USB"]

            for device in candidates:
                ip = device["ip"]
                battery, charging = await _get_battery_info(ip)
                _battery_cache[ip] = (time.time(), battery, charging)
                await device_manager.add_or_update(
                    device["deviceId"],
                    ip,
                    battery=battery,
                    battery_charging=charging,
                )

            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            if candidates:
                logger.info("Battery poll complete: devices=%d duration_ms=%d", len(candidates), elapsed_ms)

            await asyncio.sleep(15)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("Battery poll loop error: %s", exc)
            await asyncio.sleep(5)


async def process_discovered_ip(
    ip: str,
    config: dict,
    semaphore: asyncio.Semaphore,
    metrics: dict[str, int],
):
    started_at = time.perf_counter()
    async with semaphore:
        connected = await adb_executor.connect(ip)
        if not connected:
            logger.debug("ADB port open on %s but connect failed", ip)
            return

        stable_device_id, id_source = await _read_stable_id_from_adb(ip)
        battery, charging = await _get_cached_battery_info(ip)

        package_id = config.get("packageId", "com.vrclassroom.player")
        packages, cached_apk_version = await _get_cached_packages_and_version(ip, package_id)
        player_installed = package_id in packages
        autostart_enabled = await _get_autostart_state(ip, package_id)

        device_id = stable_device_id
        player_port = config.get("playerPort", 8080)

        if player_installed:
            data = await _check_player_http(ip, player_port)
            if data:
                device_id, id_source = await _resolve_identity(ip, data)

                await device_manager.add_or_update(
                    device_id,
                    ip,
                    stable_device_id=device_id,
                    id_source=id_source,
                    adb_connected=True,
                    battery=battery,
                    battery_charging=charging,
                    installed_packages=packages,
                    player_connected=True,
                    player_version=data.get("playerVersion", data.get("version", "") or cached_apk_version),
                    playback_state=data.get("state", "idle"),
                    current_video=data.get("file", ""),
                    current_mode=data.get("mode", "360"),
                    playback_time=data.get("time", 0.0),
                    playback_duration=data.get("duration", 0.0),
                    loop=data.get("loop", False),
                    locked=data.get("locked", False),
                    uptime_minutes=data.get("uptimeMinutes", 0),
                    autostart_enabled=autostart_enabled,
                )

                device_name = data.get("deviceName", "")
                if device_name:
                    await device_manager.apply_device_name_from_device(device_id, device_name)
            else:
                metrics["http_timeout_count"] += 1
                await device_manager.add_or_update(
                    device_id,
                    ip,
                    stable_device_id=stable_device_id,
                    id_source=id_source,
                    adb_connected=True,
                    battery=battery,
                    battery_charging=charging,
                    installed_packages=packages,
                )

                proc_ok, pid_output = await adb_executor.shell(ip, f"pidof {package_id}")
                if proc_ok and pid_output.strip():
                    logger.info(
                        "Player process running on %s (PID: %s) but HTTP port %d not responding yet. "
                        "Will not relaunch — player_recheck_loop will detect it when ready.",
                        ip, pid_output.strip(), player_port
                    )
                elif ip not in _launch_attempted:
                    logger.info("Player installed but not running on %s, attempting launch", ip)
                    _launch_attempted.add(ip)
                    await adb_executor.shell(
                        ip,
                        f"monkey -p {package_id} -c android.intent.category.LAUNCHER 1"
                    )
                    await asyncio.sleep(5)
                    data = await _check_player_http(ip, player_port, max_retries=3)
                    if data:
                        device_id, id_source = await _resolve_identity(ip, data)
                        await device_manager.add_or_update(
                            device_id,
                            ip,
                            stable_device_id=device_id,
                            id_source=id_source,
                            player_connected=True,
                            player_version=data.get("playerVersion", data.get("version", "") or cached_apk_version),
                            playback_state=data.get("state", "idle"),
                            current_video=data.get("file", ""),
                            current_mode=data.get("mode", "360"),
                            playback_time=data.get("time", 0.0),
                            playback_duration=data.get("duration", 0.0),
                            loop=data.get("loop", False),
                            locked=data.get("locked", False),
                            uptime_minutes=data.get("uptimeMinutes", 0),
                            autostart_enabled=autostart_enabled,
                        )
                        device_name = data.get("deviceName", "")
                        if device_name:
                            await device_manager.apply_device_name_from_device(device_id, device_name)
                    else:
                        metrics["http_timeout_count"] += 1
                        logger.warning("Player on %s launched but HTTP still not responding", ip)
                else:
                    logger.debug("Player not running on %s, already attempted launch this cycle", ip)
        else:
            await device_manager.add_or_update(
                device_id,
                ip,
                stable_device_id=stable_device_id,
                id_source=id_source,
                adb_connected=True,
                autostart_enabled=autostart_enabled,
                battery=battery,
                battery_charging=charging,
                installed_packages=packages,
            )

    metrics["processed_devices"] += 1
    per_device_ms = int((time.perf_counter() - started_at) * 1000)
    logger.info("Discovery metrics: ip=%s per_device_init_ms=%d", ip, per_device_ms)


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

            scan_started_at = time.perf_counter()
            discovered_ips = await scan_subnet(subnet)

            # Reset launch tracker each scan cycle
            _launch_attempted.clear()

            metrics = {
                "http_timeout_count": 0,
                "adb_timeout_count": 0,
                "processed_devices": 0,
            }
            semaphore = asyncio.Semaphore(DISCOVERY_CONCURRENCY)
            tasks = [process_discovered_ip(ip, config, semaphore, metrics) for ip in discovered_ips]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, asyncio.TimeoutError):
                    metrics["adb_timeout_count"] += 1
                elif isinstance(result, Exception):
                    logger.warning("Device processing failed: %s", result)

            # Also scan for USB devices
            await _scan_usb_devices()

            scan_duration_ms = int((time.perf_counter() - scan_started_at) * 1000)
            logger.info(
                "Discovery metrics: scan_duration_ms=%d discovered=%d processed=%d http_timeout=%d adb_timeout=%d",
                scan_duration_ms,
                len(discovered_ips),
                metrics["processed_devices"],
                metrics["http_timeout_count"],
                metrics["adb_timeout_count"],
            )

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
                id_source = "android_id"
            else:
                success, mac_output = await adb_executor.run_on_serial(
                    serial, ["shell", "cat", "/sys/class/net/wlan0/address"]
                )
                if success and mac_output.strip():
                    device_id = mac_output.strip().replace(":", "")
                    id_source = "mac"
                else:
                    device_id = serial
                    id_source = "android_id"

            ip = await adb_executor.get_usb_device_ip(serial)

            package_id = get_config().get("packageId", "com.vrclassroom.player")
            autostart_enabled = None
            if ip:
                autostart_enabled = await _get_autostart_state(ip, package_id)

            await device_manager.add_or_update(
                device_id,
                ip or "USB",
                stable_device_id=device_id,
                id_source=id_source,
                adb_connected=True,
                usb_connected=True,
                autostart_enabled=autostart_enabled,
            )
    except Exception as e:
        logger.debug("USB scan error: %s", e)


async def handle_self_registration(data: dict):
    """Handle self-registration from a player device."""
    try:
        ip = str(data.get("ip", "")).strip()
        incoming_device_id = str(data.get("deviceId", "")).strip()
        if not incoming_device_id or not ip:
            logger.warning(
                "Skipping self-registration due to invalid payload: deviceId=%r ip=%r payload=%s",
                data.get("deviceId"),
                data.get("ip"),
                data,
            )
            return

        device_id, id_source = await _resolve_identity(ip, data)

        await device_manager.add_or_update(
            device_id,
            ip=ip,
            stable_device_id=device_id,
            id_source=id_source,
            battery=data.get("battery", -1),
            player_connected=True,
            player_version=data.get("playerVersion", ""),
            installed_packages=data.get("installedPackages", []),
        )

        await device_manager.add_or_update(
            device_id,
            ip=ip,
            stable_device_id=device_id,
            id_source=id_source,
            last_player_response=time.time(),
            player_connected=True,
        )

        # If device reports a custom name, use it (unless server already has one)
        device_name = data.get("deviceName", "")
        if device_name:
            await device_manager.apply_device_name_from_device(device_id, device_name)

        device = await device_manager.get(device_id)
        if device and not device.adb_connected:
            connected = await adb_executor.connect(ip)
            if connected:
                package_id = get_config().get("packageId", "com.vrclassroom.player")
                autostart_enabled = await _get_autostart_state(ip, package_id)
                await device_manager.add_or_update(
                    device_id,
                    ip=ip,
                    stable_device_id=device_id,
                    id_source=id_source,
                    adb_connected=True,
                    autostart_enabled=autostart_enabled,
                )
    except Exception:
        logger.exception("Self-registration handling failed. payload=%s", data)
