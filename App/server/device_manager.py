import asyncio
import logging
import time
from typing import Any

import aiohttp

from .config import get_config, get_device_name, load_device_names, set_device_name
from .models import DeviceState
from .websocket_manager import ws_manager

logger = logging.getLogger("vrclassroom.devices")


class DeviceManager:
    def __init__(self):
        self._devices: dict[str, DeviceState] = {}
        self._lock = asyncio.Lock()
        self._polling_task: asyncio.Task | None = None
        self._offline_task: asyncio.Task | None = None

    async def start(self):
        load_device_names()
        self._polling_task = asyncio.create_task(self._poll_loop())
        self._offline_task = asyncio.create_task(self._offline_check_loop())

    async def stop(self):
        if self._polling_task:
            self._polling_task.cancel()
        if self._offline_task:
            self._offline_task.cancel()

    async def add_or_update(self, device_id: str, ip: str, **kwargs) -> DeviceState:
        async with self._lock:
            is_new = device_id not in self._devices
            if is_new:
                device = DeviceState(device_id, ip)
                saved_name = get_device_name(device_id)
                if saved_name:
                    device.name = saved_name
                self._devices[device_id] = device
                logger.info("New device discovered: %s (%s)", device_id, ip)
            else:
                device = self._devices[device_id]
                device.ip = ip  # Update IP in case of DHCP change

            old_dict = device.to_dict()
            device.last_seen = time.time()
            device.online = True

            for key, value in kwargs.items():
                if hasattr(device, key):
                    setattr(device, key, value)

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

    async def get_all(self) -> list[dict[str, Any]]:
        async with self._lock:
            return [d.to_dict() for d in self._devices.values()]

    async def get(self, device_id: str) -> DeviceState | None:
        async with self._lock:
            return self._devices.get(device_id)

    async def get_dict(self, device_id: str) -> dict | None:
        async with self._lock:
            device = self._devices.get(device_id)
            return device.to_dict() if device else None

    async def remove(self, device_id: str) -> bool:
        async with self._lock:
            if device_id in self._devices:
                del self._devices[device_id]
                await ws_manager.broadcast({
                    "type": "device_removed",
                    "deviceId": device_id,
                })
                return True
            return False

    async def update_name(self, device_id: str, name: str) -> bool:
        async with self._lock:
            device = self._devices.get(device_id)
            if not device:
                return False
            device.name = name

        set_device_name(device_id, name)
        await ws_manager.broadcast({
            "type": "device_update",
            "deviceId": device_id,
            "changes": {"name": name},
        })
        return True

    async def get_online_player_devices(self) -> list[DeviceState]:
        async with self._lock:
            return [d for d in self._devices.values() if d.online and d.player_connected]

    async def get_online_adb_devices(self) -> list[DeviceState]:
        async with self._lock:
            return [d for d in self._devices.values() if d.online and d.adb_connected]

    def get_snapshot(self) -> list[dict[str, Any]]:
        return [d.to_dict() for d in self._devices.values()]

    async def _poll_loop(self):
        while True:
            try:
                config = get_config()
                interval = config.get("statusPollInterval", 5)
                await asyncio.sleep(interval)

                async with self._lock:
                    devices = [
                        d for d in self._devices.values()
                        if d.online and (d.player_connected or d.adb_connected)
                    ]

                if devices:
                    tasks = [self._poll_device(d) for d in devices]
                    await asyncio.gather(*tasks, return_exceptions=True)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Poll loop error: %s", e)
                await asyncio.sleep(5)

    async def _poll_device(self, device: DeviceState):
        config = get_config()
        player_port = config.get("playerPort", 8080)
        url = f"http://{device.ip}:{player_port}/status"

        # Try up to 2 times with increasing timeout for Quest 3 stability
        for attempt in range(2):
            try:
                timeout = 5 if attempt == 0 else 8
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            await self.add_or_update(
                                device.device_id,
                                device.ip,
                                battery=data.get("battery", device.battery),
                                battery_charging=data.get("batteryCharging", data.get("charging", False)),
                                playback_state=data.get("state", "idle"),
                                current_video=data.get("file", ""),
                                current_mode=data.get("mode", "360"),
                                playback_time=data.get("time", 0.0),
                                playback_duration=data.get("duration", 0.0),
                                loop=data.get("loop", False),
                                locked=data.get("locked", False),
                                uptime_minutes=data.get("uptimeMinutes", 0),
                                last_player_response=time.time(),
                                player_connected=True,
                            )
                            return  # Success
                        else:
                            logger.warning("Player %s returned status %d", device.ip, resp.status)
            except Exception:
                if attempt == 0:
                    await asyncio.sleep(1)
                    continue

        # All attempts failed - mark as disconnected only after consecutive failures
        # Use a grace period: don't disconnect immediately
        if device.player_connected:
            now = time.time()
            grace_period = config.get("deviceOfflineTimeout", 30)
            if device.last_player_response > 0 and (now - device.last_player_response) > grace_period:
                await self.add_or_update(
                    device.device_id,
                    device.ip,
                    player_connected=False,
                )

    async def _offline_check_loop(self):
        while True:
            try:
                config = get_config()
                timeout = config.get("deviceOfflineTimeout", 30)
                await asyncio.sleep(10)

                now = time.time()
                async with self._lock:
                    devices_to_update = []
                    for d in self._devices.values():
                        if d.online and (now - d.last_seen) > timeout:
                            devices_to_update.append(d)

                for d in devices_to_update:
                    await self.add_or_update(
                        d.device_id,
                        d.ip,
                        online=False,
                        player_connected=False,
                    )
                    logger.info("Device %s marked offline (no response for %ds)", d.device_id, timeout)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Offline check error: %s", e)
                await asyncio.sleep(10)


device_manager = DeviceManager()
