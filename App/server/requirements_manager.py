import asyncio
import logging
import os
from typing import Any, Dict, List, Set

import aiohttp

from .config import PLAYER_HTTP_PORT, get_config
from .device_manager import device_manager

logger = logging.getLogger("vrclassroom.requirements")


async def _load_device_files(device_ip: str) -> Set[str]:
    async with aiohttp.ClientSession() as session:
        url = f"http://{device_ip}:{PLAYER_HTTP_PORT}/files"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status}")
            data = await resp.json()

    filenames: Set[str] = set()
    for file_info in data.get("files", []):
        filename = str(file_info.get("name", "")).strip()
        path = str(file_info.get("path", "")).strip()
        if filename:
            filenames.add(filename)
        if path:
            filenames.add(os.path.basename(path))
    return filenames


async def check_requirements(device_id: str) -> List[Dict[str, Any]]:
    """Check which configured video files are present on a device."""
    device = await device_manager.get(device_id)
    if not device:
        return []

    if not device.player_connected:
        await device_manager.add_or_update(
            device_id,
            device.ip,
            requirements_met=None,
            requirements_detail=[],
        )
        return []

    try:
        device_files = await _load_device_files(device.ip)
    except Exception as exc:
        logger.warning("Failed to load device files for %s: %s", device_id, exc)
        return list(device.requirements_detail or [])

    config = get_config()
    videos = config.get("requirementVideos", [])

    results = []
    for video in videos:
        filename = os.path.basename(str(video.get("filename", "")).strip())
        results.append({
            "type": "video",
            "id": video.get("id", ""),
            "name": video.get("name", ""),
            "filename": filename,
            "present": bool(filename) and filename in device_files,
        })

    all_met = all(result["present"] for result in results) if results else True

    await device_manager.add_or_update(
        device_id,
        device.ip,
        requirements_met=all_met,
        requirements_detail=results,
    )

    return results


async def refresh_all_requirements():
    devices = await device_manager.get_online_player_devices()
    if not devices:
        return
    await asyncio.gather(*[check_requirements(device.device_id) for device in devices], return_exceptions=True)
