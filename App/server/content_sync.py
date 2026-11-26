"""Video content over Wi-Fi: headset agents download the class videos from this server.

Settings → "Video library folder" (`videoLibraryPath`) is a folder on this PC. Every video in
`requirementVideos` whose file is in that folder is offered to the headsets: "Sync content"
sends each target agent {"action": "sync_content", "files": [{name, size, url}]}. The agent
(ContentSync.java) skips files it already has with the same size, resumes interrupted
downloads (HTTP Range, served by FileResponse) and pauses while the player is playing.
Headsets report their files back in every status, which drives the requirements check.
Players older than 1.9.0 have no agent and still need the USB deploy tool.
"""
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from .config import get_config
from .device_manager import device_manager
from .device_ws_manager import device_ws_manager

logger = logging.getLogger("vrclassroom.content")

CONTENT_URL_PREFIX = "/api/content/files/"


def library_dir() -> Optional[Path]:
    path = str(get_config().get("videoLibraryPath", "")).strip().strip('"')
    return Path(path) if path and os.path.isdir(path) else None


def safe_name(name: str) -> Optional[str]:
    """A bare file name, or None: requests can never reach outside the library folder."""
    name = (name or "").strip()
    if not name or name.startswith(".") or os.path.basename(name) != name or "/" in name or "\\" in name:
        return None
    return name


def library_file(name: str) -> Optional[Path]:
    folder = library_dir()
    name = safe_name(name)
    if folder is None or name is None:
        return None
    path = folder / name
    return path if path.is_file() else None


def library_sizes() -> Dict[str, int]:
    """File name -> size for the configured videos found in the library folder."""
    sizes: Dict[str, int] = {}
    for video in get_config().get("requirementVideos", []):
        name = os.path.basename(str(video.get("filename", "")).strip())
        path = library_file(name)
        if path is not None:
            sizes[name] = path.stat().st_size
    return sizes


def library_listing() -> Dict[str, Any]:
    folder = library_dir()
    configured = [os.path.basename(str(v.get("filename", "")).strip()) for v in get_config().get("requirementVideos", [])]
    sizes = library_sizes()
    return {
        "folder": str(folder) if folder else "",
        "videos": [{"name": name, "size": sizes.get(name), "inLibrary": name in sizes} for name in configured if name],
    }


async def _agent_targets(device_ids: List[str]) -> List[str]:
    """Agent-connected devices among device_ids (empty = all)."""
    targets = []
    for device in await device_manager.get_all():
        if device_ids and device["deviceId"] not in device_ids:
            continue
        if device.get("agentConnected") and device_ws_manager.is_connected(device["deviceId"]):
            targets.append(device["deviceId"])
    return targets


async def sync_content(device_ids: List[str]) -> Dict[str, Any]:
    if library_dir() is None:
        return {"success": False, "error": "Video library folder not found: set it in Settings"}
    sizes = library_sizes()
    listing = library_listing()
    files = [{"name": name, "size": size, "url": CONTENT_URL_PREFIX + quote(name)} for name, size in sizes.items()]
    command = {"type": "command", "action": "sync_content", "files": files}

    sent = []
    for device_id in await _agent_targets(device_ids):
        if await device_ws_manager.send_command(device_id, dict(command)):
            sent.append(device_id)
    missing = [v["name"] for v in listing["videos"] if not v["inLibrary"]]
    logger.info("Content sync (%d file(s)) sent to %d agent(s); not in library: %s", len(files), len(sent), missing)
    return {"success": True, "sent": len(sent), "deviceIds": sent, "files": len(files), "missingInLibrary": missing}


async def cancel_content(device_ids: List[str]) -> Dict[str, Any]:
    sent = []
    for device_id in await _agent_targets(device_ids):
        if await device_ws_manager.send_command(device_id, {"type": "command", "action": "cancel_content"}):
            sent.append(device_id)
    return {"success": True, "sent": len(sent), "deviceIds": sent}
