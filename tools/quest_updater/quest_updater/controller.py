from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from queue import Queue
from typing import Dict, Iterable, List

from .adb_service import ADBError, ADBService
from .config_store import load_settings, save_settings
from .models import ApkInfo, DeviceInfo, RequiredFileSpec, UploadJob, UpdaterSettings


REMOTE_VIDEO_DIR = "/sdcard/Movies"


class QuestUpdaterController:
    def __init__(self):
        self.events: "Queue[dict]" = Queue()
        self.settings = load_settings()
        self.adb = ADBService()
        self.devices: Dict[str, DeviceInfo] = {}
        self.required_files: List[RequiredFileSpec] = []
        self.upload_jobs: Dict[str, UploadJob] = {}
        self._busy = False
        self._busy_lock = threading.Lock()
        self._load_required_files()

    def set_settings(self, settings: UpdaterSettings) -> None:
        self.settings = settings.normalized()
        save_settings(self.settings)
        self._load_required_files()

    def _emit(self, event_type: str, **payload) -> None:
        payload["type"] = event_type
        self.events.put(payload)

    def log(self, message: str) -> None:
        self._emit("log", message=message, ts=time.strftime("%H:%M:%S"))

    def _run_async(self, target, *, busy_label: str) -> None:
        with self._busy_lock:
            if self._busy:
                self.log("Another operation is already running.")
                return
            self._busy = True
        self._emit("busy", value=True, label=busy_label)

        def runner():
            try:
                target()
            except Exception as exc:  # pragma: no cover
                self.log(f"Unexpected error: {exc}")
            finally:
                with self._busy_lock:
                    self._busy = False
                self._emit("busy", value=False, label="")

        threading.Thread(target=runner, daemon=True).start()

    def _load_required_files(self) -> None:
        filenames: List[str] = []
        app_config_path = Path(self.settings.app_config_path)
        if app_config_path.exists():
            try:
                payload = json.loads(app_config_path.read_text(encoding="utf-8"))
                for item in payload.get("requirementVideos", []):
                    filename = str(item.get("filename", "")).strip()
                    if filename and filename not in filenames:
                        filenames.append(filename)
            except (json.JSONDecodeError, OSError) as exc:
                self.log(f"Failed to read App config: {exc}")

        self.required_files = [
            RequiredFileSpec(
                filename=name,
                source_path=self.settings.local_path_overrides.get(name, ""),
            )
            for name in filenames
        ]
        self.required_files = self.adb.resolve_required_files(self.settings.content_root, self.required_files)
        self._emit("required_files_updated", files=[item.to_dict() for item in self.required_files])

    def refresh_required_files(self) -> None:
        self._load_required_files()

    def set_required_file_override(self, filename: str, source_path: str) -> None:
        if source_path:
            self.settings.local_path_overrides[filename] = source_path
        else:
            self.settings.local_path_overrides.pop(filename, None)
        save_settings(self.settings)
        self._load_required_files()

    def discover_async(self) -> None:
        self._run_async(self._discover, busy_label="Discovering devices...")

    def pair_wifi_async(self, serials: Iterable[str]) -> None:
        selected = list(serials)
        self._run_async(lambda: self._pair_wifi(selected), busy_label="Pairing Wi-Fi...")

    def plan_async(self, serials: Iterable[str]) -> None:
        selected = list(serials)
        self._run_async(lambda: self._plan(selected), busy_label="Building update plan...")

    def apply_async(self, serials: Iterable[str]) -> None:
        selected = list(serials)
        self._run_async(lambda: self._apply(selected), busy_label="Applying updates...")

    def _discover(self) -> None:
        self.log("Scanning adb devices...")
        discovered = self.adb.list_devices()
        inspected: Dict[str, DeviceInfo] = {}
        for device in discovered:
            try:
                inspected[device.serial] = self.adb.inspect_device(
                    device,
                    self.settings.package_id,
                    self.settings.player_http_port,
                )
            except Exception as exc:
                inspected[device.serial] = DeviceInfo(
                    serial=device.serial,
                    adb_state=device.adb_state,
                    transport=device.transport,
                    model=device.model,
                    note=str(exc),
                )
        self.devices = inspected
        self._emit("devices_updated", devices=[device.to_dict() for device in self.devices.values()])
        self.log(f"Found {len(self.devices)} device(s).")

    def _pair_wifi(self, serials: List[str]) -> None:
        if not serials:
            self.log("Select at least one USB device to enable Wi-Fi ADB.")
            return
        for serial in serials:
            device = self.devices.get(serial)
            if device and device.transport != "usb":
                self.log(f"Skipping {serial}: already not a USB transport.")
                continue
            try:
                ip = self.adb.pair_wifi(serial)
                self.log(f"{serial} connected over Wi-Fi at {ip}:5555")
            except ADBError as exc:
                self.log(f"{serial} Wi-Fi pairing failed: {exc}")
        self._discover()

    def _plan(self, serials: List[str]) -> None:
        if not serials:
            self.log("Select at least one device.")
            return
        if not self.devices:
            self._discover()

        apk_info = self.adb.get_local_apk_info(self.settings.apk_path, self.settings.package_id)
        if self.settings.apk_path and not Path(self.settings.apk_path).exists():
            self.log(f"APK path does not exist: {self.settings.apk_path}")
        if apk_info.version_name or apk_info.version_code:
            self.log(
                f"Local APK: {apk_info.package_id} versionName={apk_info.version_name or '?'} "
                f"versionCode={apk_info.version_code or '?'}"
            )
        else:
            self.log("Local APK metadata could not be read. Install checks will use the package state only.")

        self.required_files = self.adb.resolve_required_files(self.settings.content_root, self.required_files)
        self._emit("required_files_updated", files=[item.to_dict() for item in self.required_files])

        for serial in serials:
            device = self.devices.get(serial)
            if not device:
                continue
            planned = self._plan_device(device, apk_info, self.required_files)
            self.devices[serial] = planned
            self._emit("device_updated", device=planned.to_dict())

        self.log("Plan is ready.")

    def _plan_device(self, device: DeviceInfo, apk_info: ApkInfo, required_files: List[RequiredFileSpec]) -> DeviceInfo:
        planned = DeviceInfo(**device.to_dict())
        install_needed = self._needs_install(planned, apk_info)
        file_note = "inventory unavailable"
        if planned.player_http_ok and planned.ip:
            try:
                remote_files = self.adb.get_remote_files_http(planned.ip, self.settings.player_http_port)
                missing = [
                    spec.filename
                    for spec in required_files
                    if spec.status == "ready" and remote_files.get(spec.filename) != spec.size_bytes
                ]
                file_note = f"{len(missing)} file(s) need upload" if missing else "content is up to date"
            except Exception:
                file_note = "HTTP inventory failed"
        planned.plan_summary = ("install/update APK; " if install_needed else "APK OK; ") + file_note
        planned.stage = "planned"
        return planned

    def _needs_install(self, device: DeviceInfo, apk_info: ApkInfo) -> bool:
        if self.settings.force_reinstall_apk:
            return bool(self.settings.apk_path)
        if not device.package_installed:
            return bool(self.settings.apk_path)
        if apk_info.version_code and device.installed_version_code:
            if apk_info.version_code != device.installed_version_code:
                return True
        if apk_info.version_name and device.installed_version_name:
            return apk_info.version_name != device.installed_version_name
        return False

    def _apply(self, serials: List[str]) -> None:
        if not serials:
            self.log("Select at least one device.")
            return
        self._discover()

        self.required_files = self.adb.resolve_required_files(self.settings.content_root, self.required_files)
        self._emit("required_files_updated", files=[item.to_dict() for item in self.required_files])

        missing_local = [item.filename for item in self.required_files if item.status != "ready"]
        if missing_local:
            self.log("Some required files are unresolved and will be skipped: " + ", ".join(missing_local))

        apk_info = self.adb.get_local_apk_info(self.settings.apk_path, self.settings.package_id)
        if self.settings.apk_path and not Path(self.settings.apk_path).exists():
            self.log(f"APK path does not exist: {self.settings.apk_path}")
        install_targets = [self.devices[serial] for serial in serials if serial in self.devices]
        if not install_targets:
            self.log("No matching devices were found.")
            return

        self.log("Stage 1/3: installing APK where needed...")
        with ThreadPoolExecutor(max_workers=self.settings.max_concurrent_installs) as executor:
            futures = {
                executor.submit(self._install_stage_for_device, device, apk_info): device.serial
                for device in install_targets
            }
            for future in as_completed(futures):
                serial = futures[future]
                try:
                    updated = future.result()
                    self.devices[serial] = updated
                    self._emit("device_updated", device=updated.to_dict())
                except Exception as exc:
                    self.log(f"{serial} install stage failed: {exc}")

        self.log("Stage 2/3: building content sync plan...")
        upload_jobs = []
        device_changed_files: Dict[str, List[str]] = {}
        for serial in serials:
            device = self.devices.get(serial)
            if not device or device.adb_state != "device":
                continue
            device.stage = "planning content"
            self._emit("device_updated", device=device.to_dict())

            inventory = {}
            if device.ip and self.settings.verify_http:
                try:
                    inventory = self.adb.get_remote_files_http(device.ip, self.settings.player_http_port)
                    device.player_http_ok = True
                except Exception:
                    device.player_http_ok = False
            if not inventory:
                inventory = self.adb.get_remote_files_adb(serial, REMOTE_VIDEO_DIR)

            to_upload = [
                spec
                for spec in self.required_files
                if spec.status == "ready" and inventory.get(spec.filename) != spec.size_bytes
            ]
            device.plan_summary = f"{len(to_upload)} file(s) to upload"
            device.stage = "sync queued"
            self._emit("device_updated", device=device.to_dict())
            for spec in to_upload:
                upload_jobs.append((device, spec))
            device_changed_files[serial] = []

        self.log(f"Stage 3/3: uploading {len(upload_jobs)} file job(s)...")
        self.upload_jobs = {}
        self._emit("upload_reset")

        with ThreadPoolExecutor(max_workers=self.settings.max_concurrent_uploads) as executor:
            futures = {}
            for device, spec in upload_jobs:
                future = executor.submit(self._upload_job, device, spec)
                futures[future] = (device.serial, spec.filename)
            for future in as_completed(futures):
                serial, filename = futures[future]
                try:
                    remote_path = future.result()
                    device_changed_files.setdefault(serial, []).append(remote_path)
                    self.log(f"{serial} uploaded {filename}")
                except Exception as exc:
                    self.log(f"{serial} failed to upload {filename}: {exc}")

        self.log("Finalizing media library refresh...")
        for serial, changed in device_changed_files.items():
            if not changed or not self.settings.auto_scan_media:
                continue
            device = self.devices.get(serial)
            if not device:
                continue
            try:
                self.adb.trigger_media_scan(
                    serial,
                    self.settings.package_id,
                    changed,
                    device.ip,
                    self.settings.player_http_port,
                )
                time.sleep(2)
            except Exception as exc:
                self.log(f"{serial} media scan warning: {exc}")

        self._discover()
        self.log("Update flow finished.")

    def _install_stage_for_device(self, device: DeviceInfo, apk_info: ApkInfo) -> DeviceInfo:
        current = DeviceInfo(**device.to_dict())
        if current.adb_state != "device":
            current.stage = f"ADB {current.adb_state}"
            return current

        install_needed = self._needs_install(current, apk_info)
        if install_needed and self.settings.apk_path:
            current.stage = "installing APK"
            self._emit("device_updated", device=current.to_dict())
            self.adb.install_apk(current.serial, self.settings.apk_path)
            self.log(f"{current.serial} APK installed or updated.")
        else:
            current.stage = "APK up to date"
            self._emit("device_updated", device=current.to_dict())

        if self.settings.launch_after_install:
            current.stage = "launching player"
            self._emit("device_updated", device=current.to_dict())
            self.adb.launch_app(current.serial, self.settings.package_id)
            if not current.ip:
                current.ip = self.adb.get_device_ip(current.serial)
            if current.ip:
                current.player_http_ok = self.adb.wait_for_player_http(
                    current.serial,
                    current.ip,
                    self.settings.player_http_port,
                    self.settings.package_id,
                    timeout=30,
                )

        refreshed = self.adb.inspect_device(current, self.settings.package_id, self.settings.player_http_port)
        refreshed.stage = "ready"
        return refreshed

    def _upload_job(self, device: DeviceInfo, file_spec: RequiredFileSpec) -> str:
        job_id = f"{device.serial}|{file_spec.filename}"
        self.upload_jobs[job_id] = UploadJob(
            job_id=job_id,
            serial=device.serial,
            device_label=device.device_name or device.serial,
            filename=file_spec.filename,
            total_bytes=file_spec.size_bytes,
            state="queued",
        )
        self._emit("upload_updated", job=self.upload_jobs[job_id].to_dict())

        def on_progress(done: int, total: int, speed: float, state: str, note: str) -> None:
            job = self.upload_jobs[job_id]
            job.transferred_bytes = done
            job.total_bytes = total
            job.percent = (done / total * 100.0) if total else 0.0
            job.speed_bps = speed
            job.state = state
            job.note = note
            self._emit("upload_updated", job=job.to_dict())

        remote_path = self.adb.upload_file_with_progress(
            device.serial,
            file_spec.source_path,
            REMOTE_VIDEO_DIR,
            progress_cb=on_progress,
        )
        verified = self.adb.verify_remote_file_size(device.serial, remote_path, file_spec.size_bytes)
        job = self.upload_jobs[job_id]
        job.transferred_bytes = file_spec.size_bytes
        job.total_bytes = file_spec.size_bytes
        job.percent = 100.0
        job.speed_bps = 0.0
        job.state = "done" if verified else "warning"
        job.note = "verified" if verified else "size mismatch after upload"
        self._emit("upload_updated", job=job.to_dict())
        return remote_path
