import asyncio
import logging
import os
from typing import Any, Dict, List, Set

import aiohttp

from .config import PLAYER_HTTP_PORT, get_config
from .content_sync import library_sizes
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

    # Headset agent (1.9.0+) reports its files with sizes, player or not; older players are asked over HTTP.
    device_sizes: Dict[str, int] = {}
    if device.files is not None:
        device_sizes = {str(f.get("name", "")): int(f.get("size", -1)) for f in device.files}
        device_files = set(device_sizes)
    elif not device.player_connected:
        await device_manager.add_or_update(
            device_id,
            device.ip,
            seen=False,
            requirements_met=None,
            requirements_detail=[],
        )
        return []
    else:
        try:
            device_files = await _load_device_files(device.ip)
        except Exception as exc:
            logger.warning("Failed to load device files for %s: %s", device_id, exc)
            return list(device.requirements_detail or [])

    config = get_config()
    videos = config.get("requirementVideos", [])
    library = library_sizes()

    results = []
    for video in videos:
        filename = os.path.basename(str(video.get("filename", "")).strip())
        present = bool(filename) and filename in device_files
        # Same name, different size than in the library: an older or broken copy; sync replaces it.
        outdated = present and filename in library and filename in device_sizes and device_sizes[filename] != library[filename]
        results.append({
            "type": "video",
            "id": video.get("id", ""),
            "name": video.get("name", ""),
            "filename": filename,
            "present": present and not outdated,
            "outdated": outdated,
        })

    all_met = all(result["present"] for result in results) if results else True

    await device_manager.add_or_update(
        device_id,
        device.ip,
        requirements_met=all_met,
        requirements_detail=results,
    )

    return results


async def apply_agent_files(device_id: str, files: Any):
    """Store the file list an agent reported and re-check requirements when it changed."""
    if not isinstance(files, list):
        return
    normalized = [
        {"name": os.path.basename(str(f.get("name", ""))), "size": int(f.get("size", -1) or -1)}
        for f in files if isinstance(f, dict) and f.get("name")
    ]
    device = await device_manager.get(device_id)
    if device is None or device.files == normalized:
        return
    await device_manager.add_or_update(device_id, device.ip, seen=False, files=normalized)
    await check_requirements(device_id)


async def refresh_all_requirements():
    devices = [d for d in await device_manager.get_online_devices() if d.player_connected or d.files is not None]
    if not devices:
        return
    await asyncio.gather(*[check_requirements(device.device_id) for device in devices], return_exceptions=True)
