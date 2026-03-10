import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

import aiohttp

from .config import get_config, get_device_name, load_device_names, set_device_name
from .device_ws_manager import device_ws_manager
from .models import DeviceState
from .websocket_manager import ws_manager

logger = logging.getLogger("vrclassroom.devices")


class DeviceManager:
    def __init__(self):
        self._devices: Dict[str, DeviceState] = {}
        self._ip_to_device: Dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._offline_task: Optional[asyncio.Task] = None

    async def start(self):
        load_device_names()
        self._offline_task = asyncio.create_task(self._offline_check_loop())

    async def stop(self):
        if self._offline_task:
            self._offline_task.cancel()

    async def add_or_update(self, device_id: str, ip: str, **kwargs) -> DeviceState:
        """Simple upsert by device_id. IP is tracked but not used as identifier."""
        push_saved_name = False
        saved_name_value = ""
        async with self._lock:
            # If the same IP is already known under another ID, treat this as the same device.
            # This avoids duplicate tiles when the player first registers with one ID and later
            # ADB discovery reports another ID for the same physical device.
            existing_device_id_for_ip = self._ip_to_device.get(ip)
            if existing_device_id_for_ip and existing_device_id_for_ip != device_id:
                logger.info(
                    "Aliasing device %s to existing device %s by IP %s",
                    device_id,
                    existing_device_id_for_ip,
                    ip,
                )
                device_id = existing_device_id_for_ip

            is_new = device_id not in self._devices

            if is_new:
                device = DeviceState(device_id, ip)
                saved_name = get_device_name(device_id)
                if saved_name:
                    device.name = saved_name
                    push_saved_name = True
                    saved_name_value = saved_name
                self._devices[device_id] = device
                logger.info("New device discovered: %s (%s)", device_id, ip)
            else:
                device = self._devices[device_id]
                device.ip = ip

            old_dict = device.to_dict()

            device.last_seen = time.time()
            device.online = True

            for key, value in kwargs.items():
                if hasattr(device, key):
                    setattr(device, key, value)

            # Update IP index
            self._ip_to_device[ip] = device_id

            new_dict = device.to_dict()
            player_connected = device.player_connected

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
        if push_saved_name and player_connected and ip:
            await self._push_name_to_device(ip, saved_name_value)

        return device

    def get_device_id_by_ip(self, ip: str) -> Optional[str]:
        """Lookup device_id by IP for discovery correlation."""
        return self._ip_to_device.get(ip)

    async def get_known_ips(self) -> List[str]:
        async with self._lock:
            return [d.ip for d in self._devices.values() if d.ip and d.ip != "USB"]

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

    async def update_name(self, device_id: str, name: str) -> bool:
        async with self._lock:
            device = self._devices.get(device_id)
            if not device:
                return False
            device.name = name
            device_ip = device.ip
            player_connected = device.player_connected

        set_device_name(device_id, name)
        await ws_manager.broadcast({
            "type": "device_update",
            "deviceId": device_id,
            "changes": {"name": name},
        })

        if player_connected and device_ip:
            await self._push_name_to_device(device_ip, name)

        return True

    async def apply_device_name_from_device(self, device_id: str, device_name: str):
        """Apply a device-reported name if the server doesn't have a custom name yet."""
        saved = get_device_name(device_id)
        if saved:
            return
        should_broadcast = False
        async with self._lock:
            device = self._devices.get(device_id)
            if device and not device.name:
                device.name = device_name
                should_broadcast = True
        if should_broadcast:
            await ws_manager.broadcast({
                "type": "device_update",
                "deviceId": device_id,
                "changes": {"name": device_name},
            })

    async def _push_name_to_device(self, ip: str, name: str):
        """Push a name to the device via HTTP PUT /name."""
        config = get_config()
        player_port = config.get("playerPort", 8080)
        url = f"http://{ip}:{player_port}/name"
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

    async def get_online_player_devices(self) -> List[DeviceState]:
        async with self._lock:
            return [d for d in self._devices.values() if d.online and d.player_connected]

    async def get_online_adb_devices(self) -> List[DeviceState]:
        async with self._lock:
            return [d for d in self._devices.values() if d.online and d.adb_connected]

    def get_snapshot(self) -> List[Dict[str, Any]]:
        return [d.to_dict() for d in self._devices.values()]

    async def mark_discovery_seen(self, device_id: str):
        """Reset missed_discovery_cycles for a device found during scan."""
        async with self._lock:
            device = self._devices.get(device_id)
            if device:
                device.missed_discovery_cycles = 0

    async def increment_missed_discovery(self):
        """Increment missed_discovery_cycles for all online ADB devices not seen in this scan."""
        async with self._lock:
            for d in self._devices.values():
                if d.online and d.adb_connected:
                    d.missed_discovery_cycles += 1

    async def _offline_check_loop(self):
        """Unified offline detection: WS heartbeat timeout + discovery miss."""
        while True:
            try:
                await asyncio.sleep(10)
                config = get_config()
                timeout = config.get("deviceOfflineTimeout", 30)
                now = time.time()

                async with self._lock:
                    devices_to_update = []
                    for d in self._devices.values():
                        if not d.online:
                            continue

                        # WS-connected device: if WS dropped but still marked as player_connected
                        if d.player_connected and not device_ws_manager.is_connected(d.device_id):
                            # HTTP-probed player: rely on discovery cycle to refresh
                            # Only mark disconnected if not seen by discovery for 2+ cycles
                            if d.missed_discovery_cycles >= 2:
                                devices_to_update.append((d, {"player_connected": False}))
                                continue
                        elif d.player_connected and device_ws_manager.is_connected(d.device_id):
                            # WS-connected: heartbeat timeout (15s)
                            if (now - d.last_seen) > 15:
                                devices_to_update.append((d, {"player_connected": False}))
                                continue

                        # Device not seen by discovery for 2+ cycles -> offline
                        if d.missed_discovery_cycles >= 2 and not d.player_connected:
                            devices_to_update.append((d, {"online": False, "adb_connected": False}))
                            continue

                        # General timeout fallback
                        if (now - d.last_seen) > timeout:
                            devices_to_update.append((d, {"online": False, "player_connected": False, "adb_connected": False}))

                for d, updates in devices_to_update:
                    await self.add_or_update(d.device_id, d.ip, **updates)
                    if not updates.get("online", True):
                        logger.info("Device %s marked offline", d.device_id)
                    elif "player_connected" in updates:
                        logger.info("Device %s player disconnected (heartbeat timeout)", d.device_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Offline check error: %s", e)
                await asyncio.sleep(10)


device_manager = DeviceManager()
