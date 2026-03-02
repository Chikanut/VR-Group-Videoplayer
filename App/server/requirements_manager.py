import asyncio
import logging
import os
import time
from typing import Any

import aiohttp

from .adb_executor import adb_executor
from .config import get_config, get_device_video_path, DEVICE_VIDEO_DIR
from .device_manager import device_manager
from .websocket_manager import ws_manager

logger = logging.getLogger("vrclassroom.requirements")

_update_locks: dict[str, asyncio.Lock] = {}


def _get_update_lock(device_id: str) -> asyncio.Lock:
    if device_id not in _update_locks:
        _update_locks[device_id] = asyncio.Lock()
    return _update_locks[device_id]


def _compare_versions(local_ver: str, device_ver: str) -> bool:
    """Return True if local_ver is newer than device_ver."""
    def parse(v: str):
        parts = []
        for p in v.replace("-", ".").split("."):
            try:
                parts.append(int(p))
            except ValueError:
                parts.append(0)
        return parts
    try:
        return parse(local_ver) > parse(device_ver)
    except Exception:
        return local_ver != device_ver


async def check_requirements(device_id: str) -> list[dict[str, Any]]:
    """Check which requirements are met for a device."""
    device = await device_manager.get(device_id)
    if not device:
        return []

    config = get_config()
    videos = config.get("requirementVideos", [])
    package_id = config.get("packageId", "com.vrclassroom.player")
    apk_path = config.get("apkPath", "")
    player_port = config.get("playerPort", 8080)
    results = []

    # Check APK installation and version
    apk_installed = False
    apk_needs_update = False
    device_version = ""
    local_version = ""

    if device.adb_connected:
        packages = await adb_executor.list_packages(device.ip)
        apk_installed = package_id in packages
        if apk_installed and apk_path and os.path.isfile(apk_path):
            device_version = await adb_executor.get_package_version(device.ip, package_id) or ""
            local_version = await adb_executor.get_local_apk_version(apk_path) or ""
            if device_version and local_version:
                apk_needs_update = _compare_versions(local_version, device_version)
    elif device.player_connected:
        apk_installed = True

    results.append({
        "type": "apk",
        "name": package_id,
        "required": bool(apk_path),
        "present": apk_installed and not apk_needs_update,
        "deviceVersion": device_version,
        "localVersion": local_version,
        "needsUpdate": apk_needs_update,
    })

    # Check video files
    device_files: set[str] = set()

    # Try to get file list from player API first
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
        local_path = video.get("localPath", "")
        video_name = video.get("name", "")
        device_path = get_device_video_path(local_path) if local_path else ""
        present = False

        if device_path:
            if device_path in device_files:
                present = True
            elif os.path.basename(device_path) in device_files:
                present = True
            elif device.adb_connected and not present:
                present = await adb_executor.file_exists(device.ip, device_path)

        results.append({
            "type": "video",
            "id": video.get("id", ""),
            "name": video_name,
            "devicePath": device_path,
            "localPath": local_path,
            "present": present,
        })

    # Update device requirements status
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
    """Run the update process for a device: install APK + push missing videos."""
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
            device_id, device.ip,
            update_in_progress=True,
            update_progress={"stage": "starting", "progress": 0, "message": "Starting update..."},
        )

        config = get_config()
        videos = config.get("requirementVideos", [])
        package_id = config.get("packageId", "com.vrclassroom.player")
        apk_path = config.get("apkPath", "")
        results = {"installed_apk": False, "pushed_videos": [], "errors": []}

        try:
            # Step 1: Install/update APK if needed
            if apk_path and os.path.isfile(apk_path):
                packages = await adb_executor.list_packages(device.ip)
                need_install = package_id not in packages
                need_upgrade = False

                if not need_install:
                    # Check if version upgrade is needed
                    device_ver = await adb_executor.get_package_version(device.ip, package_id) or ""
                    local_ver = await adb_executor.get_local_apk_version(apk_path) or ""
                    if device_ver and local_ver and _compare_versions(local_ver, device_ver):
                        need_upgrade = True
                        logger.info("APK upgrade: device=%s, local=%s", device_ver, local_ver)

                if need_install or need_upgrade:
                    action = "Installing" if need_install else "Upgrading"
                    await _broadcast_progress(device_id, "install_apk", 0, f"{action} {package_id}...")
                    success, output = await adb_executor.install_apk(device.ip, apk_path)
                    if success:
                        results["installed_apk"] = True
                        await _broadcast_progress(device_id, "install_apk", 100, f"APK {action.lower().rstrip('ing')}ed successfully")
                    else:
                        results["errors"].append(f"APK {action.lower()} failed: {output}")
                        await _broadcast_progress(device_id, "install_apk_failed", 0, f"APK {action.lower()} failed: {output}")
                else:
                    await _broadcast_progress(device_id, "install_apk", 100, "APK up to date")
            elif apk_path:
                logger.warning("APK path configured but file not found: %s", apk_path)
                await _broadcast_progress(device_id, "install_apk_skipped", 0, f"APK file not found: {apk_path}")

            # Step 2: Push missing videos
            total_videos = len(videos)
            for idx, video in enumerate(videos):
                device = await device_manager.get(device_id)
                if not device or not device.online:
                    results["errors"].append("Device went offline during update")
                    break

                local_path = video.get("localPath", "")
                video_name = video.get("name", os.path.basename(local_path))

                if not local_path:
                    continue

                device_path = get_device_video_path(local_path)

                # Check if already present
                exists = await adb_executor.file_exists(device.ip, device_path)
                if exists:
                    await _broadcast_progress(
                        device_id, "push_video", 100,
                        f"[{idx + 1}/{total_videos}] {video_name} already present",
                        file=video_name, video_index=idx, total=total_videos,
                    )
                    continue

                if not os.path.isfile(local_path):
                    error_msg = f"Local file not found: {local_path}"
                    results["errors"].append(error_msg)
                    await _broadcast_progress(
                        device_id, "push_video_failed", 0, error_msg,
                        file=video_name, video_index=idx, total=total_videos,
                    )
                    continue

                # Ensure directory exists on device
                await adb_executor.ensure_directory(device.ip, device_path)

                file_size = os.path.getsize(local_path)
                file_size_mb = file_size / (1024 * 1024)

                async def progress_cb(pct, text, _name=video_name, _idx=idx):
                    await _broadcast_progress(
                        device_id, "push_video", pct,
                        f"[{_idx + 1}/{total_videos}] Pushing {_name}... {pct}%",
                        file=_name, video_index=_idx, total=total_videos,
                    )

                await _broadcast_progress(
                    device_id, "push_video", 0,
                    f"[{idx + 1}/{total_videos}] Pushing {video_name} ({file_size_mb:.0f}MB)...",
                    file=video_name, video_index=idx, total=total_videos,
                )

                success, output = await adb_executor.push_file_with_progress(
                    device.ip, local_path, device_path, progress_cb,
                )

                if success:
                    results["pushed_videos"].append(video_name)
                    # Register file with Android media scanner
                    logger.info("Scanning media file: %s", device_path)
                    await adb_executor.scan_media_file(device.ip, device_path)
                    await _broadcast_progress(
                        device_id, "push_video", 100,
                        f"[{idx + 1}/{total_videos}] {video_name} pushed successfully",
                        file=video_name, video_index=idx, total=total_videos,
                    )
                else:
                    results["errors"].append(f"Push {video_name} failed: {output}")
                    await _broadcast_progress(
                        device_id, "push_video_failed", 0,
                        f"[{idx + 1}/{total_videos}] {video_name} push failed: {output}",
                        file=video_name, video_index=idx, total=total_videos,
                    )

            # Step 3: Re-check requirements
            await _broadcast_progress(device_id, "verifying", 0, "Verifying requirements...")
            await check_requirements(device_id)

            status = "completed" if not results["errors"] else "completed_with_errors"
            await _broadcast_progress(
                device_id, status, 100,
                f"Update {status}. Pushed {len(results['pushed_videos'])} video(s), {len(results['errors'])} error(s).",
            )

        except Exception as e:
            logger.error("Update failed for %s: %s", device_id, e)
            results["errors"].append(str(e))
            await _broadcast_progress(device_id, "failed", 0, f"Update failed: {e}")

        finally:
            await device_manager.add_or_update(
                device_id, device.ip,
                update_in_progress=False,
                update_progress=None,
            )

        results["status"] = "completed" if not results["errors"] else "completed_with_errors"
        return results


async def run_usb_update(
    serial: str,
    *,
    enable_wireless_adb: bool = True,
    update_app: bool = True,
    update_content: bool = True,
) -> dict[str, Any]:
    """Run initialization for a USB-connected device with selectable stages."""
    config = get_config()
    videos = config.get("requirementVideos", [])
    package_id = config.get("packageId", "com.vrclassroom.player")
    apk_path = config.get("apkPath", "")
    results = {"serial": serial, "installed_apk": False, "pushed_videos": [], "errors": [], "ip": None}

    # Broadcast progress via WebSocket (use serial as device_id for USB)
    usb_device_id = f"usb_{serial}"

    async def broadcast_usb(stage, progress, message, **extra):
        data = {
            "type": "update_progress",
            "deviceId": usb_device_id,
            "stage": stage,
            "progress": progress,
            "message": message,
            "isUsb": True,
            **extra,
        }
        await ws_manager.broadcast(data)

    stages = []
    if update_app:
        stages.append("Update App")
    if update_content:
        stages.append("Update Content")
    if enable_wireless_adb:
        stages.append("Wireless ADB")
    await broadcast_usb("starting", 0, f"Initializing USB device {serial} ({', '.join(stages)})...")

    try:
        # Step 1: Install APK (if selected)
        if update_app:
            if apk_path and os.path.isfile(apk_path):
                await broadcast_usb("install_apk", 0, f"Installing {package_id}...")
                success, output = await adb_executor.install_apk_usb(serial, apk_path)
                if success:
                    results["installed_apk"] = True
                    await broadcast_usb("install_apk", 100, "APK installed successfully")
                else:
                    results["errors"].append(f"APK install failed: {output}")
                    await broadcast_usb("install_apk_failed", 0, f"APK install failed: {output}")
            elif apk_path:
                results["errors"].append(f"APK file not found: {apk_path}")
                await broadcast_usb("install_apk_failed", 0, f"APK file not found: {apk_path}")

        # Step 2: Push videos (if selected)
        if update_content:
            total_videos = len(videos)
            for idx, video in enumerate(videos):
                local_path = video.get("localPath", "")
                video_name = video.get("name", os.path.basename(local_path))
                if not local_path:
                    continue

                device_path = get_device_video_path(local_path)

                if not os.path.isfile(local_path):
                    results["errors"].append(f"Local file not found: {local_path}")
                    await broadcast_usb("push_video_failed", 0, f"File not found: {local_path}",
                                        file=video_name, video_index=idx, total=total_videos)
                    continue

                # Ensure directory
                await adb_executor.run_on_serial(serial, ["shell", "mkdir", "-p", DEVICE_VIDEO_DIR])

                file_size = os.path.getsize(local_path)
                file_size_mb = file_size / (1024 * 1024)

                async def progress_cb(pct, text, _name=video_name, _idx=idx):
                    await broadcast_usb("push_video", pct,
                                        f"[{_idx + 1}/{total_videos}] Pushing {_name}... {pct}%",
                                        file=_name, video_index=_idx, total=total_videos)

                await broadcast_usb("push_video", 0,
                                    f"[{idx + 1}/{total_videos}] Pushing {video_name} ({file_size_mb:.0f}MB)...",
                                    file=video_name, video_index=idx, total=total_videos)

                success, output = await adb_executor.push_file_usb_with_progress(
                    serial, local_path, device_path, progress_cb,
                )

                if success:
                    results["pushed_videos"].append(video_name)
                    await adb_executor.scan_media_file_usb(serial, device_path)
                    await broadcast_usb("push_video", 100,
                                        f"[{idx + 1}/{total_videos}] {video_name} pushed successfully",
                                        file=video_name, video_index=idx, total=total_videos)
                else:
                    results["errors"].append(f"Push {video_name} failed: {output}")
                    await broadcast_usb("push_video_failed", 0,
                                        f"[{idx + 1}/{total_videos}] Push failed: {output}",
                                        file=video_name, video_index=idx, total=total_videos)

        # Step 3: Enable wireless ADB (if selected)
        if enable_wireless_adb:
            await broadcast_usb("enabling_wifi", 50, "Enabling wireless ADB...")
            await adb_executor.enable_tcpip(serial)
            await asyncio.sleep(2)

            ip = await adb_executor.get_usb_device_ip(serial)
            results["ip"] = ip
            if ip:
                connected = await adb_executor.connect(ip)
                if connected:
                    await broadcast_usb("enabling_wifi", 100, f"Wireless ADB enabled ({ip})")
                else:
                    await broadcast_usb("enabling_wifi", 100, f"Got IP {ip} but wireless connect pending")

        status = "completed" if not results["errors"] else "completed_with_errors"
        summary_parts = []
        if update_app and results["installed_apk"]:
            summary_parts.append("APK installed")
        if update_content:
            summary_parts.append(f"{len(results['pushed_videos'])} video(s) pushed")
        if enable_wireless_adb and results.get("ip"):
            summary_parts.append(f"WiFi ADB on {results['ip']}")
        summary = ", ".join(summary_parts) if summary_parts else "No actions performed"
        await broadcast_usb(status, 100, f"USB setup {status}. {summary}.")

    except Exception as e:
        logger.error("USB update failed for %s: %s", serial, e)
        results["errors"].append(str(e))
        await broadcast_usb("failed", 0, f"USB update failed: {e}")

    results["status"] = "completed" if not results["errors"] else "completed_with_errors"
    return results


async def _broadcast_progress(device_id: str, stage: str, progress: int, message: str, **extra):
    progress_data = {
        "deviceId": device_id,
        "stage": stage,
        "progress": progress,
        "message": message,
        **extra,
    }
    await device_manager.add_or_update(
        device_id,
        (await device_manager.get(device_id)).ip,
        update_progress=progress_data,
    )
    await ws_manager.broadcast({
        "type": "update_progress",
        **progress_data,
    })
