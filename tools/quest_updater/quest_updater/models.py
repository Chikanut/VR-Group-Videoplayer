from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict


@dataclass
class ApkInfo:
    path: str = ""
    package_id: str = ""
    version_name: str = ""
    version_code: str = ""


@dataclass
class RequiredFileSpec:
    filename: str
    source_path: str = ""
    size_bytes: int = 0
    status: str = "missing"
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DeviceInfo:
    serial: str
    adb_state: str = ""
    transport: str = ""
    model: str = ""
    ip: str = ""
    device_name: str = ""
    player_http_ok: bool = False
    player_version: str = ""
    package_installed: bool = False
    installed_version_name: str = ""
    installed_version_code: str = ""
    plan_summary: str = ""
    stage: str = ""
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UploadJob:
    job_id: str
    serial: str
    device_label: str
    filename: str
    transferred_bytes: int = 0
    total_bytes: int = 0
    percent: float = 0.0
    speed_bps: float = 0.0
    state: str = "queued"
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UpdaterSettings:
    package_id: str = "com.vrclass.player"
    app_config_path: str = ""
    apk_path: str = ""
    content_root: str = ""
    player_http_port: int = 8080
    max_concurrent_installs: int = 8
    max_concurrent_uploads: int = 4
    prefer_wifi: bool = True
    verify_http: bool = True
    launch_after_install: bool = True
    auto_scan_media: bool = True
    force_reinstall_apk: bool = False
    local_path_overrides: Dict[str, str] = field(default_factory=dict)

    def normalized(self) -> "UpdaterSettings":
        settings = UpdaterSettings(**self.to_dict())
        settings.player_http_port = _clamp_int(settings.player_http_port, 8080, 1, 65535)
        settings.max_concurrent_installs = _clamp_int(settings.max_concurrent_installs, 8, 1, 32)
        settings.max_concurrent_uploads = _clamp_int(settings.max_concurrent_uploads, 4, 1, 16)
        settings.package_id = (settings.package_id or "com.vrclass.player").strip()
        settings.app_config_path = (settings.app_config_path or "").strip()
        settings.apk_path = (settings.apk_path or "").strip()
        settings.content_root = (settings.content_root or "").strip()
        settings.local_path_overrides = {
            str(name).strip(): str(path).strip()
            for name, path in (settings.local_path_overrides or {}).items()
            if str(name).strip()
        }
        return settings

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        normalized = default
    return max(minimum, min(maximum, normalized))
