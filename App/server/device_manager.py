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

# When a player WebSocket closes, wait this long before telling the dashboard: the player
# normally reconnects within a second or two (Wi-Fi roaming, app focus change, server
# restart) and flipping the WS badge for every blip only looks like instability.
WS_DISCONNECT_GRACE_SEC = 8

# Minimum interval between repeated attempts to push a name to the same device.
NAME_PUSH_RETRY_SEC = 15


class DeviceManager:
    """Tracks headset state and broadcasts diffs to web clients.

    Device naming model
    -------------------
    The headset is the source of truth for its name/number: the player persists it in
    PlayerPrefs and reports it in every register/status payload as ``deviceName``.
    The server only mirrors that value. ``device_names.json`` is kept as a fallback for
    players that do not report a name (older builds, or a freshly installed app) and as
    a queue: when the instructor renames an offline device the name is stored here and
    pushed to the headset as soon as it reports again.

    Effective display name, in priority order:
      1. a name the instructor just assigned that the device has not confirmed yet
      2. the name reported by the device
      3. the server-side fallback from device_names.json
      4. the device ID
    """

    def __init__(self):
        self._devices: Dict[str, DeviceState] = {}
        self._ip_to_device: Dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._liveness_task: Optional[asyncio.Task] = None
        self._liveness_pass_count = 0
        # device_id -> name assigned by the instructor, awaiting confirmation from the device
        self._pending_names: Dict[str, str] = {}
        self._last_name_push: Dict[str, float] = {}
        self._ws_grace_tasks: Dict[str, asyncio.Task] = {}

    async def start(self):
        load_device_names()
        self._liveness_task = asyncio.create_task(self._liveness_loop())

    async def stop(self):
        if self._liveness_task:
            self._liveness_task.cancel()
        for task in self._ws_grace_tasks.values():
            task.cancel()
        self._ws_grace_tasks.clear()

    # --- Upsert -------------------------------------------------------------

    async def add_or_update(self, device_id: str, ip: str, *, seen: bool = True, **kwargs) -> Optional[DeviceState]:
        """Upsert device state and broadcast the diff to web clients.

        seen=True  - the data comes from the device itself (WS heartbeat, HTTP status,
                     registration). Proves reachability: refreshes last_seen and online.
        seen=False - server-side bookkeeping (volume, requirements, liveness verdicts).
                     Never refreshes last_seen and never resurrects an offline device.
        """
        ip = (ip or "").strip()

        async with self._lock:
            device_id = self._resolve_device_id_locked(device_id, ip)
            is_new = device_id not in self._devices

            if is_new:
                if not seen:
                    # Bookkeeping for a device we have never heard from - nothing to update.
                    return None
                device = DeviceState(device_id, ip or "unknown")
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

            self._refresh_name_locked(device)
            new_dict = device.to_dict()

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
        if not device_id:
            logger.warning("Ignoring status from %s without a device ID: %s", ip, status)
            return None

        device = await self.add_or_update(
            device_id,
            ip,
            player_connected=True,
            **status_to_kwargs(status),
        )
        if device is None:
            return None

        if "deviceName" in status:
            await self.apply_device_name_from_device(device.device_id, status.get("deviceName"))
        else:
            # Older player without name reporting: still deliver anything the instructor
            # assigned while it was away.
            await self._retry_pending_name(device.device_id)
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
            self._pending_names.pop(device_id, None)
            self._last_name_push.pop(device_id, None)
            stale_ips = [ip for ip, did in self._ip_to_device.items() if did == device_id]
            for ip in stale_ips:
                del self._ip_to_device[ip]

        task = self._ws_grace_tasks.pop(device_id, None)
        if task:
            task.cancel()

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

    def _refresh_name_locked(self, device: DeviceState):
        """Recompute the effective display name and its source (see class docstring)."""
        pending = self._pending_names.get(device.device_id)
        if pending is not None:
            device.pending_name = pending
            if pending:
                device.name = pending
                device.name_source = "pending"
                return
            # Pending "" = instructor cleared the name; fall through without the fallback
            # file (set_device_name already removed it) but keep showing the ID.
            device.name = device.device_id
            device.name_source = "id"
            return

        device.pending_name = ""
        if device.reported_name:
            device.name = device.reported_name
            device.name_source = "device"
            return

        saved = get_device_name(device.device_id)
        if saved:
            device.name = saved
            device.name_source = "server"
            return

        device.name = device.device_id
        device.name_source = "id"

    async def _broadcast_if_changed(self, device_id: str, old_dict: Dict[str, Any], new_dict: Dict[str, Any]):
        changes = {k: v for k, v in new_dict.items() if old_dict.get(k) != v}
        if changes:
            await ws_manager.broadcast({
                "type": "device_update",
                "deviceId": device_id,
                "changes": changes,
            })

    async def update_name(self, device_id: str, name: str) -> Optional[Dict[str, Any]]:
        """Instructor assigns a name/number. Stored on the headset; mirrored here.

        Returns None if the device is unknown, otherwise a dict describing whether the
        name reached the device (``pushed``/``via``) or is queued (``pending``).
        """
        normalized = (name or "").strip()

        async with self._lock:
            device = self._devices.get(device_id)
            if not device:
                return None
            old_dict = device.to_dict()
            if normalized == device.reported_name:
                # Device already has exactly this name: nothing to push, drop any stale
                # pending value.
                self._pending_names.pop(device_id, None)
            else:
                self._pending_names[device_id] = normalized
            self._refresh_name_locked(device)
            new_dict = device.to_dict()
            device_ip = device.ip
            reachable = device.online and device.player_connected
            already_confirmed = normalized == device.reported_name

        # Fallback store for players that do not report names (and for restarts).
        set_device_name(device_id, normalized)
        await self._broadcast_if_changed(device_id, old_dict, new_dict)

        if already_confirmed:
            return {"ok": True, "name": new_dict["name"], "pushed": True, "via": "device", "pending": False}

        pushed, via = False, None
        if reachable:
            pushed, via = await self._push_name_to_device(device_id, device_ip, normalized)

        return {
            "ok": True,
            "name": new_dict["name"],
            "pushed": pushed,
            "via": via,
            "pending": not pushed,
        }

    async def apply_device_name_from_device(self, device_id: str, device_name: Optional[str]):
        """Apply the name the device reports (device wins over the server-side fallback).

        Also reconciles pending instructor assignments: a matching report confirms
        them, a mismatching one triggers a (throttled) re-push. A device that reports an
        empty name while the server still has a fallback for it receives that fallback,
        so a reinstalled app gets its number back.
        """
        reported = str(device_name or "").strip()
        push_name: Optional[str] = None

        async with self._lock:
            device = self._devices.get(device_id)
            if device is None:
                return
            old_dict = device.to_dict()
            device.reported_name = reported

            pending = self._pending_names.get(device_id)
            if pending is not None:
                if pending == reported:
                    logger.info("Device %s confirmed name '%s'", device_id, reported)
                    self._pending_names.pop(device_id, None)
                else:
                    push_name = pending
            elif not reported:
                saved = get_device_name(device_id)
                if saved:
                    push_name = saved

            self._refresh_name_locked(device)
            new_dict = device.to_dict()
            device_ip = device.ip

        await self._broadcast_if_changed(device_id, old_dict, new_dict)

        if push_name is not None and self._name_push_due(device_id):
            await self._push_name_to_device(device_id, device_ip, push_name)

    async def _retry_pending_name(self, device_id: str):
        async with self._lock:
            pending = self._pending_names.get(device_id)
            device = self._devices.get(device_id)
            device_ip = device.ip if device else ""
        if pending is None or not self._name_push_due(device_id):
            return
        await self._push_name_to_device(device_id, device_ip, pending)

    def _name_push_due(self, device_id: str) -> bool:
        last = self._last_name_push.get(device_id, 0.0)
        return (time.time() - last) >= NAME_PUSH_RETRY_SEC

    def reset_name_push_throttle(self, device_id: str):
        """A fresh connection is a new chance to deliver a queued name right away."""
        self._last_name_push.pop(device_id, None)

    async def _push_name_to_device(self, device_id: str, ip: str, name: str) -> Tuple[bool, Optional[str]]:
        """Deliver a name to the headset: WS command first, HTTP PUT /name as fallback.

        Only a *successful* delivery starts the retry throttle, so a push that failed
        because the device was unreachable is retried at the next sign of life.
        """
        if device_ws_manager.is_connected(device_id):
            sent = await device_ws_manager.send_command(
                device_id, {"type": "command", "action": "set_name", "name": name}
            )
            if sent:
                logger.info("Pushed name '%s' to device %s via WS", name, device_id)
                self._last_name_push[device_id] = time.time()
                return True, "ws"

        if not ip or ip == "unknown":
            return False, None

        url = f"http://{ip}:{PLAYER_HTTP_PORT}/name"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.put(
                    url,
                    json={"name": name},
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status == 200:
                        logger.info("Pushed name '%s' to device %s via HTTP", name, ip)
                        self._last_name_push[device_id] = time.time()
                        return True, "http"
                    logger.warning("Failed to push name to %s: HTTP %d", ip, resp.status)
        except Exception as e:
            logger.warning("Failed to push name to device %s: %s", ip, e)
        return False, None

    async def sync_device_names(self):
        """Re-evaluate fallback names after device_names.json was replaced via the API.

        Imported names never overwrite what a headset reports about itself; they only
        fill in for devices that report no name.
        """
        async with self._lock:
            updates = []
            for device in self._devices.values():
                old_dict = device.to_dict()
                self._refresh_name_locked(device)
                updates.append((device.device_id, old_dict, device.to_dict()))

        for device_id, old_dict, new_dict in updates:
            await self._broadcast_if_changed(device_id, old_dict, new_dict)

    # --- Player WebSocket lifecycle -----------------------------------------

    def cancel_ws_disconnect_grace(self, device_id: str):
        task = self._ws_grace_tasks.pop(device_id, None)
        if task:
            task.cancel()

    def schedule_ws_disconnect_check(self, device_id: str):
        """Mark ws_connected=False only if the player has not reconnected within the grace period."""
        self.cancel_ws_disconnect_grace(device_id)
        self._ws_grace_tasks[device_id] = asyncio.create_task(self._ws_disconnect_check(device_id))

    async def _ws_disconnect_check(self, device_id: str):
        try:
            await asyncio.sleep(WS_DISCONNECT_GRACE_SEC)
        except asyncio.CancelledError:
            return
        self._ws_grace_tasks.pop(device_id, None)
        if device_ws_manager.is_connected(device_id):
            return
        # Do not demote player_connected here: the HTTP API is usually still up and the
        # liveness loop verifies that, marking the device offline only if it really stops
        # answering.
        await self.add_or_update(device_id, "", seen=False, ws_connected=False)

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
