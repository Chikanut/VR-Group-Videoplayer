import asyncio
import logging
import os
from typing import Any

import aiohttp

from .adb_executor import adb_executor
from .config import get_config
from .device_manager import device_manager
from .websocket_manager import ws_manager

logger = logging.getLogger("vrclassroom.requirements")

_update_locks: dict[str, asyncio.Lock] = {}


def _get_update_lock(device_id: str) -> asyncio.Lock:
    if device_id not in _update_locks:
        _update_locks[device_id] = asyncio.Lock()
    return _update_locks[device_id]


def _to_file_uri(path: str) -> str:
    if path.startswith("file://"):
        return path
    return "file://" + path


def _shell_escape_single_quotes(value: str) -> str:
    return value.replace("'", "'\\''")


def _normalized_device_path(video: dict[str, Any]) -> str:
    local_path = (video.get("localPath") or "").strip()
    if local_path:
        return f"/sdcard/Movies/{os.path.basename(local_path)}"
    return (video.get("devicePath") or "").strip()


async def _scan_media_file(ip: str, normalized_path: str) -> str:
    """Ask Android media scanner to index a file and return diagnostic output."""
    file_uri = _to_file_uri(normalized_path)
    outputs = []

    _, broadcast_out = await adb_executor.shell(
        ip,
        "am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE "
        f"-d '{_shell_escape_single_quotes(file_uri)}'",
    )
    if broadcast_out:
        outputs.append(broadcast_out)

    _, cmd_scan_out = await adb_executor.shell(
        ip,
        f"cmd media.scan '{_shell_escape_single_quotes(normalized_path)}'",
    )
    if cmd_scan_out and "can't find service: media.scan" not in cmd_scan_out.lower():
        outputs.append(cmd_scan_out)

    return " | ".join(chunk for chunk in outputs if chunk)


async def check_requirements(device_id: str) -> list[dict[str, Any]]:
    device = await device_manager.get(device_id)
    if not device:
        return []

    config = get_config()
    videos = config.get("requirementVideos", [])
    package_id = config.get("packageId", "com.vrclassroom.player")
    apk_path = config.get("apkPath", "")
    player_port = config.get("playerPort", 8080)
    results = []

    apk_installed = False
    if device.adb_connected:
        packages = await adb_executor.list_packages(device.ip)
        apk_installed = package_id in packages
    elif device.player_connected:
        apk_installed = True

    results.append({
        "type": "apk",
        "name": package_id,
        "required": bool(apk_path),
        "present": apk_installed,
    })

    device_files: set[str] = set()
    if device.player_connected:
        try:
            async with aiohttp.ClientSession() as session:
                url = f"http://{device.ip}:{player_port}/files"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for f in data.get("files", []):
                            device_files.add(f.get("path", ""))
                            device_files.add(f.get("name", ""))
        except Exception:
            pass

    for video in videos:
        device_path = _normalized_device_path(video)
        video_name = video.get("name", "")
        present = False

        if device_path:
            if device_path in device_files:
                present = True
            elif os.path.basename(device_path) in device_files:
                present = True
            elif device.adb_connected:
                present = await adb_executor.file_exists(device.ip, device_path)

        results.append({
            "type": "video",
            "id": video.get("id", ""),
            "name": video_name,
            "devicePath": device_path,
            "localPath": video.get("localPath", ""),
            "present": present,
        })

    all_met = all(
        r["present"] for r in results
        if r.get("required", True) and (r["type"] != "apk" or bool(apk_path))
    )
    if not videos and not apk_path:
        all_met = True

    await device_manager.add_or_update(
        device_id,
        device.ip,
        requirements_met=all_met,
        requirements_detail=results,
    )

    return results


async def run_update(device_id: str) -> dict[str, Any]:
    lock = _get_update_lock(device_id)

    if lock.locked():
        device = await device_manager.get(device_id)
        return {
            "status": "already_running",
            "progress": device.update_progress if device else None,
        }

    async with lock:
        device = await device_manager.get(device_id)
        if not device:
            return {"status": "error", "message": "Device not found"}

        if not device.adb_connected:
            return {"status": "error", "message": "ADB not connected"}

        await device_manager.add_or_update(
            device_id,
            device.ip,
            update_in_progress=True,
            update_progress={"stage": "starting", "progress": 0, "message": "Starting update..."},
        )

        config = get_config()
        videos = config.get("requirementVideos", [])
        package_id = config.get("packageId", "com.vrclassroom.player")
        apk_path = config.get("apkPath", "")
        results = {"installed_apk": False, "pushed_videos": [], "errors": []}

        try:
            if apk_path and os.path.isfile(apk_path):
                packages = await adb_executor.list_packages(device.ip)
                if package_id not in packages:
                    await _broadcast_progress(device_id, "install_apk", 0, f"Installing {package_id}...")
                    success, output = await adb_executor.install_apk(device.ip, apk_path)
                    if success:
                        results["installed_apk"] = True
                        await _broadcast_progress(device_id, "install_apk", 100, "APK installed successfully")
                    else:
                        results["errors"].append(f"APK install failed: {output}")
                        await _broadcast_progress(device_id, "install_apk_failed", 0, f"APK install failed: {output}")
                else:
                    await _broadcast_progress(device_id, "install_apk", 100, "APK already installed")
            elif apk_path:
                logger.warning("APK path configured but file not found: %s", apk_path)
                await _broadcast_progress(device_id, "install_apk_skipped", 0, f"APK file not found: {apk_path}")

            total_videos = len(videos)
            for idx, video in enumerate(videos):
                device = await device_manager.get(device_id)
                if not device or not device.online:
                    results["errors"].append("Device went offline during update")
                    break

                local_path = video.get("localPath", "")
                device_path = _normalized_device_path(video)
                video_name = video.get("name", os.path.basename(local_path))

                if not device_path or not local_path:
                    continue

                exists = await adb_executor.file_exists(device.ip, device_path)
                if exists:
                    await _broadcast_progress(
                        device_id,
                        "push_video",
                        100,
                        f"[{idx + 1}/{total_videos}] {video_name} already present",
                        file=video_name,
                        video_index=idx,
                        total=total_videos,
                    )
                    continue

                if not os.path.isfile(local_path):
                    error_msg = f"Local file not found: {local_path}"
                    results["errors"].append(error_msg)
                    await _broadcast_progress(
                        device_id,
                        "push_video_failed",
                        0,
                        error_msg,
                        file=video_name,
                        video_index=idx,
                        total=total_videos,
                    )
                    continue

                await adb_executor.ensure_directory(device.ip, device_path)

                file_size_mb = os.path.getsize(local_path) / (1024 * 1024)

                async def progress_cb(pct: int, _text: str, _name=video_name, _idx=idx):
                    await _broadcast_progress(
                        device_id,
                        "push_video",
                        pct,
                        f"[{_idx + 1}/{total_videos}] Pushing {_name}... {pct}%",
                        file=_name,
                        video_index=_idx,
                        total=total_videos,
                    )

                await _broadcast_progress(
                    device_id,
                    "push_video",
                    0,
                    f"[{idx + 1}/{total_videos}] Pushing {video_name} ({file_size_mb:.0f}MB)...",
                    file=video_name,
                    video_index=idx,
                    total=total_videos,
                )

                success, output = await adb_executor.push_file_with_progress(
                    device.ip,
                    local_path,
                    device_path,
                    progress_cb,
                )

                if success:
                    results["pushed_videos"].append(video_name)
                    scan_output = await _scan_media_file(device.ip, device_path)
                    if scan_output:
                        logger.info("Media scan output [%s] %s: %s", device_id, video_name, scan_output)
                    await _broadcast_progress(
                        device_id,
                        "push_video",
                        100,
                        f"[{idx + 1}/{total_videos}] {video_name} pushed successfully",
                        file=video_name,
                        video_index=idx,
                        total=total_videos,
                    )
                else:
                    results["errors"].append(f"Push {video_name} failed: {output}")
                    await _broadcast_progress(
                        device_id,
                        "push_video_failed",
                        0,
                        f"[{idx + 1}/{total_videos}] {video_name} push failed: {output}",
                        file=video_name,
                        video_index=idx,
                        total=total_videos,
                    )

            await _broadcast_progress(device_id, "verifying", 0, "Verifying requirements...")
            await check_requirements(device_id)

            status = "completed" if not results["errors"] else "completed_with_errors"
            await _broadcast_progress(
                device_id,
                status,
                100,
                f"Update {status}. Pushed {len(results['pushed_videos'])} video(s), {len(results['errors'])} error(s).",
            )

        except Exception as e:
            logger.error("Update failed for %s: %s", device_id, e)
            results["errors"].append(str(e))
            await _broadcast_progress(device_id, "failed", 0, f"Update failed: {e}")

        finally:
            await device_manager.add_or_update(
                device_id,
                device.ip,
                update_in_progress=False,
                update_progress=None,
            )

        results["status"] = "completed" if not results["errors"] else "completed_with_errors"
        return results


async def _broadcast_progress(device_id: str, stage: str, progress: int, message: str, **extra):
    device = await device_manager.get(device_id)
    if not device:
        return

    progress_data = {
        "deviceId": device_id,
        "stage": stage,
        "progress": progress,
        "message": message,
        **extra,
    }
    await device_manager.add_or_update(
        device_id,
        device.ip,
        update_progress=progress_data,
    )
    await ws_manager.broadcast({
        "type": "update_progress",
        **progress_data,
    })
