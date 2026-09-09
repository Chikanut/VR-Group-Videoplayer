import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from .config import PLAYER_HTTP_PORT, get_config, get_device_name, load_device_names, set_device_name
from .device_ws_manager import device_ws_manager
from .models import DeviceState
from .player_probe import extract_device_id, probe_player_status, status_to_kwargs
from .websocket_manager import ws_manager

logger = logging.getLogger("vrclassroom.devices")

# Liveness loop tuning.
LIVENESS_CHECK_INTERVAL = 5     # seconds between liveness passes
PROBE_STALE_AFTER = 10          # seconds without any report from the device before we probe /status
OFFLINE_PROBE_EVERY = 3         # offline devices are re-probed every Nth pass (~15s)
PROBE_CONCURRENCY = 24

# A device reporting an unknown ID from an IP that another device used *this recently*
# is treated as the same physical device (two devices cannot share an IP at the same time).
IP_ALIAS_WINDOW_SEC = 60


class DeviceManager:
    def __init__(self):
        self._devices: Dict[str, DeviceState] = {}
        self._ip_to_device: Dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._liveness_task: Optional[asyncio.Task] = None
        self._liveness_pass_count = 0

    async def start(self):
        load_device_names()
        self._liveness_task = asyncio.create_task(self._liveness_loop())

    async def stop(self):
        if self._liveness_task:
            self._liveness_task.cancel()

    # --- Upsert -------------------------------------------------------------

    async def add_or_update(self, device_id: str, ip: str, *, seen: bool = True, **kwargs) -> Optional[DeviceState]:
        """Upsert device state and broadcast the diff to web clients.

        seen=True  - the data comes from the device itself (WS heartbeat, HTTP status,
                     registration). Proves reachability: refreshes last_seen and online.
        seen=False - server-side bookkeeping (volume, requirements, liveness verdicts).
                     Never refreshes last_seen and never resurrects an offline device.
        """
        push_saved_name = False
        saved_name_value = ""
        ip = (ip or "").strip()

        async with self._lock:
            device_id = self._resolve_device_id_locked(device_id, ip)
            is_new = device_id not in self._devices

            if is_new:
                if not seen:
                    # Bookkeeping for a device we have never heard from - nothing to update.
                    return None
                device = DeviceState(device_id, ip or "unknown")
                saved_name = get_device_name(device_id)
                if saved_name:
                    device.name = saved_name
                    push_saved_name = True
                    saved_name_value = saved_name
                self._devices[device_id] = device
                logger.info("New device discovered: %s (%s)", device_id, ip)
            else:
                device = self._devices[device_id]

            old_dict = device.to_dict()

            if seen:
                device.last_seen = time.time()
                device.online = True
                if ip and ip != "unknown":
                    self._set_device_ip_locked(device, ip)
            elif ip and ip != "unknown" and (not device.ip or device.ip == "unknown"):
                self._set_device_ip_locked(device, ip)

            for key, value in kwargs.items():
                if hasattr(device, key):
                    setattr(device, key, value)

            new_dict = device.to_dict()
            player_connected = device.player_connected
            device_ip = device.ip

        # Broadcast changes
        if is_new:
            await ws_manager.broadcast({
                "type": "device_update",
                "deviceId": device_id,
                "device": new_dict,
                "isNew": True,
            })
        else:
            changes = {k: v for k, v in new_dict.items() if old_dict.get(k) != v}
            if changes:
                await ws_manager.broadcast({
                    "type": "device_update",
                    "deviceId": device_id,
                    "changes": changes,
                })

        # Push server-saved name to newly discovered device
        if push_saved_name and player_connected and device_ip and device_ip != "unknown":
            await self._push_name_to_device(device_ip, saved_name_value)

        return device

    def _resolve_device_id_locked(self, device_id: str, ip: str) -> str:
        """Map an incoming device ID onto an already-known device where that is safe.

        Aliasing by IP used to be unconditional, which merged two *different* headsets
        whenever a DHCP lease was reused. Now we only alias when:
          * the caller had no real ID and fell back to the IP, or
          * the device at that IP reported very recently (so it must be the same box).
        """
        if device_id in self._devices:
            return device_id

        existing_id = self._ip_to_device.get(ip) if ip else None
        if not existing_id or existing_id == device_id:
            return device_id

        existing = self._devices.get(existing_id)
        if existing is None:
            return device_id

        if device_id == ip or (time.time() - existing.last_seen) <= IP_ALIAS_WINDOW_SEC:
            logger.info("Aliasing device %s to existing device %s by IP %s", device_id, existing_id, ip)
            return existing_id

        return device_id

    def _set_device_ip_locked(self, device: DeviceState, ip: str):
        """Update a device's IP and keep the IP index free of stale entries."""
        if device.ip != ip:
            for stale_ip in [k for k, v in self._ip_to_device.items() if v == device.device_id and k != ip]:
                del self._ip_to_device[stale_ip]
            device.ip = ip
        self._ip_to_device[ip] = device.device_id

    async def apply_player_status(self, device_id_hint: str, ip: str, status: Dict[str, Any]) -> Optional[DeviceState]:
        """Apply a /status payload (from HTTP probe or WS heartbeat) as proof of life."""
        device_id = extract_device_id(status, device_id_hint)
        device = await self.add_or_update(
            device_id,
            ip,
            player_connected=True,
            **status_to_kwargs(status),
        )
        device_name = str(status.get("deviceName", "") or "").strip()
        if device is not None and device_name:
            await self.apply_device_name_from_device(device.device_id, device_name)
        return device

    # --- Queries ------------------------------------------------------------

    def get_device_id_by_ip(self, ip: str) -> Optional[str]:
        """Lookup device_id by IP for discovery correlation."""
        return self._ip_to_device.get(ip)

    async def get_known_ips(self) -> List[str]:
        async with self._lock:
            return [d.ip for d in self._devices.values() if d.ip and d.ip != "unknown"]

    async def get_all(self) -> List[Dict[str, Any]]:
        async with self._lock:
            return [d.to_dict() for d in self._devices.values()]

    async def get(self, device_id: str) -> Optional[DeviceState]:
        async with self._lock:
            return self._devices.get(device_id)

    async def get_dict(self, device_id: str) -> Optional[Dict]:
        async with self._lock:
            device = self._devices.get(device_id)
            return device.to_dict() if device else None

    async def remove(self, device_id: str) -> bool:
        async with self._lock:
            if device_id not in self._devices:
                return False
            self._devices.pop(device_id)
            stale_ips = [ip for ip, did in self._ip_to_device.items() if did == device_id]
            for ip in stale_ips:
                del self._ip_to_device[ip]

        await ws_manager.broadcast({
            "type": "device_removed",
            "deviceId": device_id,
        })
        return True

    async def get_online_player_devices(self) -> List[DeviceState]:
        async with self._lock:
            return [d for d in self._devices.values() if d.online and d.player_connected]

    def get_snapshot(self) -> List[Dict[str, Any]]:
        return [d.to_dict() for d in self._devices.values()]

    # --- Names --------------------------------------------------------------

    async def update_name(self, device_id: str, name: str) -> bool:
        async with self._lock:
            device = self._devices.get(device_id)
            if not device:
                return False
            device.name = name or device.reported_name or device.device_id
            device_ip = device.ip
            player_connected = device.player_connected

        set_device_name(device_id, name)
        await ws_manager.broadcast({
            "type": "device_update",
            "deviceId": device_id,
            "changes": {"name": name or device.reported_name or device.device_id},
        })

        if player_connected and device_ip:
            await self._push_name_to_device(device_ip, name or device.reported_name or "")

        return True

    async def apply_device_name_from_device(self, device_id: str, device_name: str):
        """Apply a device-reported name if the server doesn't have a custom name yet."""
        saved = get_device_name(device_id)
        if saved:
            return
        should_broadcast = False
        effective_name = device_name
        async with self._lock:
            device = self._devices.get(device_id)
            if device:
                device.reported_name = device_name
            if device and device.name != device_name:
                device.name = device_name
                should_broadcast = True
        if should_broadcast:
            await ws_manager.broadcast({
                "type": "device_update",
                "deviceId": device_id,
                "changes": {"name": effective_name},
            })

    async def _push_name_to_device(self, ip: str, name: str):
        """Push a name to the device via HTTP PUT /name."""
        url = f"http://{ip}:{PLAYER_HTTP_PORT}/name"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.put(
                    url,
                    json={"name": name},
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status == 200:
                        logger.info("Pushed name '%s' to device %s", name, ip)
                    else:
                        logger.warning("Failed to push name to %s: HTTP %d", ip, resp.status)
        except Exception as e:
            logger.warning("Failed to push name to device %s: %s", ip, e)

    async def sync_device_names(self):
        async with self._lock:
            updates = []
            for device in self._devices.values():
                saved_name = get_device_name(device.device_id)
                next_name = saved_name or device.reported_name or device.device_id
                if device.name != next_name:
                    device.name = next_name
                    updates.append((device.device_id, next_name))

        for device_id, name in updates:
            await ws_manager.broadcast({
                "type": "device_update",
                "deviceId": device_id,
                "changes": {"name": name},
            })

    # --- Liveness -----------------------------------------------------------

    async def _liveness_loop(self):
        while True:
            try:
                await asyncio.sleep(LIVENESS_CHECK_INTERVAL)
                await self.run_liveness_pass()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Liveness check error: %s", e)
                await asyncio.sleep(LIVENESS_CHECK_INTERVAL)

    async def run_liveness_pass(self, now: Optional[float] = None):
        """Verify devices that went quiet and demote only those that are really gone.

        A device counts as alive if ANY of these holds:
          * its player WebSocket is still open (uvicorn ping/pong closes dead sockets),
          * it answered a direct HTTP GET /status just now,
          * it reported anything (heartbeat, registration, scan) within PROBE_STALE_AFTER.

        Only when the WS is closed AND direct probes keep failing for longer than the
        configured deviceOfflineTimeout is the device marked offline. Offline devices are
        re-probed periodically so they come back as soon as they are reachable again,
        without waiting for the next full subnet scan.
        """
        self._liveness_pass_count += 1
        now = time.time() if now is None else now
        config = get_config()
        offline_after = max(float(config.get("deviceOfflineTimeout", 30)), 10.0)
        probe_offline = self._liveness_pass_count % OFFLINE_PROBE_EVERY == 0

        async with self._lock:
            targets: List[Tuple[str, str]] = []
            for d in self._devices.values():
                if not d.ip or d.ip == "unknown":
                    continue
                if d.online:
                    if (now - d.last_seen) >= PROBE_STALE_AFTER:
                        targets.append((d.device_id, d.ip))
                elif probe_offline:
                    targets.append((d.device_id, d.ip))

        if not targets:
            return

        semaphore = asyncio.Semaphore(PROBE_CONCURRENCY)

        async def probe(device_id: str, ip: str):
            async with semaphore:
                return device_id, ip, await probe_player_status(ip)

        results = await asyncio.gather(*(probe(did, ip) for did, ip in targets), return_exceptions=True)

        verdict_time = time.time()
        for result in results:
            if isinstance(result, BaseException):
                logger.debug("Liveness probe raised: %s", result)
                continue
            device_id, ip, status = result

            if status is not None:
                await self.apply_player_status(device_id, ip, status)
                continue

            if device_ws_manager.is_connected(device_id):
                # Transport is alive even though the app-level heartbeat is quiet
                # (e.g. Unity Update() paused). Keep the device online.
                continue

            device = await self.get(device_id)
            if device is None or not device.online:
                continue

            silent_for = verdict_time - device.last_seen
            if silent_for >= offline_after:
                logger.info(
                    "Device %s marked offline (silent for %.0fs, WS closed, HTTP probe failed)",
                    device_id,
                    silent_for,
                )
                await self.add_or_update(
                    device_id,
                    ip,
                    seen=False,
                    online=False,
                    player_connected=False,
                    ws_connected=False,
                )


device_manager = DeviceManager()
