import asyncio
import logging
import socket
from typing import Dict, List, Optional
from urllib.parse import quote

import aiohttp

from .config import PLAYER_HTTP_PORT, get_config
from .device_manager import device_manager
from .device_ws_manager import device_ws_manager
from .player_probe import AGENT_HTTP_PORT, extract_device_id, probe_player_status

logger = logging.getLogger("vrclassroom.discovery")

DISCOVERY_CONCURRENCY = 24
SCAN_TIMEOUT_SEC = 0.8


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
    """Try to reach the player HTTP API. Returns status dict or None."""
    return await probe_player_status(ip)


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


async def _point_agents_to_server(subnet: str):
    """Headset agents (1.9.0+) answer on 8081 even with the player closed. Tell those that are
    not connected where the server is, so they need not find it with their own scan."""
    server_url = _get_server_url()
    if not server_url:
        return
    connected_ips = {
        d["ip"] for d in await device_manager.get_all()
        if d.get("agentConnected") and device_ws_manager.is_connected(d["deviceId"])
    }
    for ip in await scan_subnet(subnet, AGENT_HTTP_PORT):
        if ip in connected_ips:
            continue
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"http://{ip}:{AGENT_HTTP_PORT}/server?address={quote(server_url)}",
                    timeout=aiohttp.ClientTimeout(total=3),
                ) as resp:
                    # Watchdogs older than 1.9.0 answer 404: they have no agent.
                    logger.debug("Server address pushed to agent %s: HTTP %d", ip, resp.status)
        except Exception as exc:
            logger.debug("Server address push to %s failed: %s", ip, exc)


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

        device_id = extract_device_id(status, "")
        if not device_id:
            # A player that answered with an empty/partial status (e.g. an internal error
            # while building it). Refresh the device we already know at this IP, but never
            # invent a new device keyed by the IP - that is how headsets used to "lose"
            # their ID and name on the dashboard.
            device_id = device_manager.get_device_id_by_ip(ip) or ""
            if not device_id:
                logger.warning("Player at %s answered /status without a device ID; skipping", ip)
                return

        if not device_ws_manager.is_connected(device_id):
            server_url = _get_server_url()
            if server_url:
                asyncio.create_task(_push_server_ip_to_player(ip, server_url))

        device = await device_manager.apply_player_status(device_id, ip, status)
        if device is None:
            return
        device_id = device.device_id

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

            known_ips = await device_manager.get_known_ips()
            discovered_ips = await scan_subnet(subnet, PLAYER_HTTP_PORT, preferred_ips=known_ips)

            # The fast subnet sweep uses a short connect timeout and can miss a busy or
            # power-saving headset. Known devices always get a full-timeout status probe
            # so a single slow answer never looks like a disappearance.
            seen = set(discovered_ips)
            for ip in known_ips:
                if ip not in seen:
                    discovered_ips.append(ip)
                    seen.add(ip)

            semaphore = asyncio.Semaphore(DISCOVERY_CONCURRENCY)
            tasks = [process_discovered_ip(ip, semaphore) for ip in discovered_ips]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    logger.warning("Device processing failed: %s", result)

            await _point_agents_to_server(subnet)

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

        kwargs = {"player_connected": True}
        if "battery" in data:
            kwargs["battery"] = data.get("battery", -1)
        if data.get("playerVersion"):
            kwargs["player_version"] = data.get("playerVersion", "")

        device = await device_manager.add_or_update(incoming_device_id, ip=ip, **kwargs)
        if device is None:
            return
        device_id = device.device_id

        if "deviceName" in data:
            await device_manager.apply_device_name_from_device(device_id, data.get("deviceName"))

        from .requirements_manager import check_requirements

        await check_requirements(device_id)
    except Exception:
        logger.exception("Self-registration handling failed. payload=%s", data)
