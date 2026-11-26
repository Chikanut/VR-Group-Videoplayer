"""Updates from GitHub Releases: the control panel itself and the player APK.

`GET /api/updates` compares APP_VERSION with the latest release (cached 10 min).
Player: the release APK is downloaded next to config.json (`updates/`), set as
`playerApkPath` and sent to the headsets like "Update players" (player_update.py).
Panel: only the Windows .exe replaces itself (a small .bat swaps the file after this
process exits and starts it again); the Android app and a source checkout get the
release link instead.
"""
import asyncio
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

import aiohttp

from .config import CONFIG_PATH, get_config, update_config
from .player_update import update_players
from .version import APP_VERSION

logger = logging.getLogger("vrclassroom.github_update")

REPO = "Chikanut/VR-Group-Videoplayer"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
PLAYER_ASSET = "VRClassroomPlayer-Quest.apk"
PANEL_ASSET = "VRClassroomControlPanel-Windows.exe"
CACHE_SEC = 600

_cache: Dict[str, Any] = {"at": 0.0, "release": None, "error": ""}
_job: Optional[Dict[str, Any]] = None


def parse_version(text: str) -> tuple:
    return tuple(int(part) for part in re.findall(r"\d+", text or "")[:3])


def is_newer(latest: str, current: str) -> bool:
    return parse_version(latest) > parse_version(current)


def panel_can_self_update() -> bool:
    return bool(getattr(sys, "frozen", False)) and os.name == "nt"


def _release_from_api(data: Dict[str, Any]) -> Dict[str, Any]:
    assets = {a.get("name"): a for a in data.get("assets") or [] if a.get("browser_download_url")}
    version = (data.get("tag_name") or "").lstrip("v")
    return {
        "version": version,
        "name": data.get("name") or version,
        "notes": data.get("body") or "",
        "url": data.get("html_url") or f"https://github.com/{REPO}/releases/latest",
        "publishedAt": data.get("published_at") or "",
        "assets": {name: {"url": a["browser_download_url"], "size": a.get("size", 0)} for name, a in assets.items()},
        "hasPlayer": PLAYER_ASSET in assets,
        "hasPanel": PANEL_ASSET in assets,
    }


async def fetch_latest(force: bool = False) -> None:
    if not force and time.time() - _cache["at"] < CACHE_SEC:
        return
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "VRClassroomControl"}
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(LATEST_URL) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status}")
                _cache["release"] = _release_from_api(await resp.json())
                _cache["error"] = ""
    except Exception as exc:  # no internet in the classroom is normal
        _cache["error"] = str(exc) or type(exc).__name__
        logger.info("GitHub release check failed: %s", _cache["error"])
    _cache["at"] = time.time()


async def get_status(refresh: bool = False) -> Dict[str, Any]:
    if refresh or get_config().get("checkUpdates", True):
        await fetch_latest(force=refresh)
    release = _cache["release"]
    can_self = panel_can_self_update()
    return {
        "current": APP_VERSION,
        "latest": {k: v for k, v in release.items() if k != "assets"} if release else None,
        "error": _cache["error"] if refresh or not release else "",
        "panelUpdateAvailable": bool(release and is_newer(release["version"], APP_VERSION)),
        "panelCanSelfUpdate": can_self,
        "panelHint": "" if can_self else "Panel update source hint",
        "job": _job,
    }


def updates_dir() -> Path:
    return CONFIG_PATH.parent / "updates"


async def _download(url: str, dest: Path, job: Dict[str, Any]) -> None:
    part = dest.with_name(dest.name + ".part")
    dest.parent.mkdir(parents=True, exist_ok=True)
    timeout = aiohttp.ClientTimeout(total=None, sock_connect=15, sock_read=60)
    async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": "VRClassroomControl"}) as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status}")
            job["total"] = int(resp.headers.get("Content-Length") or job.get("total") or 0)
            with open(part, "wb") as file_obj:
                async for chunk in resp.content.iter_chunked(1 << 20):
                    file_obj.write(chunk)
                    job["downloaded"] += len(chunk)
    if job["total"] and job["downloaded"] != job["total"]:
        raise RuntimeError("download incomplete")
    os.replace(part, dest)


def _start(kind: str) -> Dict[str, Any]:
    global _job
    if _job and _job["stage"] in ("downloading", "installing"):
        return {"success": False, "error": "An update is already running"}
    release = _cache["release"]
    asset_name = PLAYER_ASSET if kind == "player" else PANEL_ASSET
    if not release:
        return {"success": False, "error": "No update on GitHub"}
    asset = release["assets"].get(asset_name)
    if not asset:
        return {"success": False, "error": "This release has no file for this"}
    _job = {"kind": kind, "version": release["version"], "stage": "downloading",
            "downloaded": 0, "total": asset["size"], "error": "", "message": "", "sent": None}
    return {"success": True, "asset": asset}


async def _run(job: Dict[str, Any], body) -> None:
    try:
        await body()
    except Exception as exc:
        logger.error("%s update failed: %s", job["kind"], exc)
        job.update(stage="failed", error=str(exc) or type(exc).__name__)


async def start_player_update() -> Dict[str, Any]:
    started = _start("player")
    if not started["success"]:
        return started
    job = _job
    dest = updates_dir() / f"VRClassroomPlayer-Quest-{job['version']}.apk"

    async def body():
        await _download(started["asset"]["url"], dest, job)
        cfg = get_config()
        cfg["playerApkPath"] = str(dest)
        update_config(cfg)
        job["stage"] = "installing"
        result = await update_players()
        if not result.get("success"):
            raise RuntimeError(result.get("error") or "update failed")
        job.update(stage="done", message="Update sent to headsets", sent=result["sent"])

    asyncio.create_task(_run(job, body))
    return {"success": True}


def _swap_script(new_exe: Path, exe: Path) -> str:
    # Waits until this .exe is unlocked (the PyInstaller bootloader exits after us), swaps it and starts it.
    return (
        "@echo off\r\n"
        "set n=0\r\n"
        ":retry\r\n"
        f'move /y "{new_exe}" "{exe}" >nul 2>&1 && goto run\r\n'
        "set /a n+=1\r\n"
        "if %n% geq 60 goto end\r\n"
        "timeout /t 1 /nobreak >nul\r\n"
        "goto retry\r\n"
        ":run\r\n"
        f'start "" "{exe}"\r\n'
        ":end\r\n"
        'del "%~f0"\r\n'
    )


async def start_panel_update() -> Dict[str, Any]:
    if not panel_can_self_update():
        return {"success": False, "error": "Panel update source hint"}
    started = _start("panel")
    if not started["success"]:
        return started
    job = _job
    exe = Path(sys.executable).resolve()
    new_exe = exe.with_name(exe.stem + ".new.exe")

    async def body():
        await _download(started["asset"]["url"], new_exe, job)
        script = Path(tempfile.gettempdir()) / "vrclassroom-update.bat"
        script.write_text(_swap_script(new_exe, exe), encoding="utf-8")
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        subprocess.Popen(["cmd", "/c", str(script)], creationflags=flags, close_fds=True)
        job.update(stage="done", message="Restarting the control panel...")
        logger.info("Control panel %s downloaded, restarting", job["version"])
        # shortcut: hard exit skips uvicorn shutdown; headsets reconnect to the new process within seconds.
        asyncio.get_running_loop().call_later(1.5, os._exit, 0)

    asyncio.create_task(_run(job, body))
    return {"success": True}
