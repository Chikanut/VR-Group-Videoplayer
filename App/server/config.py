import json
import logging
import os
import sys
import uuid
from copy import deepcopy
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("vrclassroom.config")


def _desktop_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).parent.parent


DESKTOP_CONFIG_PATH = _desktop_base_dir() / "config.json"
DESKTOP_DEVICE_NAMES_PATH = _desktop_base_dir() / "device_names.json"

PLAYER_HTTP_PORT = 8080

DEFAULT_CONFIG = {
    "mobileAppUrl": "",
    "playerAppUrl": "",
    "requirementVideos": [],
    "batteryThreshold": 20,
    "scanInterval": 30,
    "networkSubnet": "",
    "serverPort": 8000,
    "deviceOfflineTimeout": 30,
}

RUNTIME_ONLY_KEYS = {"isAndroidRuntime"}
VALID_VIDEO_TYPES = {"360", "2d"}
VALID_PLACEMENT_MODES = {"default", "locked", "free"}

_config: dict = {}
_config_lock = Lock()
_device_names: dict = {}
_device_names_lock = Lock()


def _runtime_target() -> str:
    return os.environ.get("VRCLASSROOM_RUNTIME", "desktop").strip().lower()


def _is_android_runtime() -> bool:
    return _runtime_target() == "android"


def _android_private_dir() -> Path:
    private_root = os.environ.get("ANDROID_PRIVATE", "").strip()
    if private_root:
        return Path(private_root)
    return Path.home() / ".vrclassroom"


def _resolve_runtime_paths() -> Tuple[Path, Path]:
    if _is_android_runtime():
        private_dir = _android_private_dir()
        return private_dir / "config.json", private_dir / "device_names.json"
    return DESKTOP_CONFIG_PATH, DESKTOP_DEVICE_NAMES_PATH


CONFIG_PATH, DEVICE_NAMES_PATH = _resolve_runtime_paths()


def _normalize_int(value: Any, default: int, *, minimum: Optional[int] = None, maximum: Optional[int] = None) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        normalized = default

    if minimum is not None:
        normalized = max(minimum, normalized)
    if maximum is not None:
        normalized = min(maximum, normalized)
    return normalized


def _normalize_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_video_type(value: Any) -> str:
    normalized = _normalize_string(value).lower()
    if normalized in {"sphere", "360_mono"}:
        normalized = "360"
    if normalized == "flat":
        normalized = "2d"
    return normalized if normalized in VALID_VIDEO_TYPES else "360"


def _normalize_placement_mode(value: Any) -> str:
    normalized = _normalize_string(value).lower()
    return normalized if normalized in VALID_PLACEMENT_MODES else "default"


def _extract_filename(video: Dict[str, Any]) -> str:
    filename = _normalize_string(video.get("filename"))
    if filename:
        return os.path.basename(filename)

    legacy_path = _normalize_string(video.get("localPath"))
    if legacy_path:
        return os.path.basename(legacy_path)

    legacy_device_path = _normalize_string(video.get("devicePath"))
    if legacy_device_path:
        return os.path.basename(legacy_device_path)

    return ""


def _normalize_video(video: Dict[str, Any]) -> Dict[str, Any]:
    advanced_settings = video.get("advancedSettings")
    normalized_video = {
        "id": _normalize_string(video.get("id")) or str(uuid.uuid4()),
        "name": _normalize_string(video.get("name")),
        "filename": _extract_filename(video),
        "loop": bool(video.get("loop", False)),
        "videoType": _normalize_video_type(video.get("videoType")),
        "placementMode": _normalize_placement_mode(video.get("placementMode")),
    }
    if advanced_settings is not None:
        normalized_video["advancedSettings"] = advanced_settings
    return normalized_video


def _serialize_storage_config(config: Dict[str, Any]) -> Dict[str, Any]:
    return {key: deepcopy(value) for key, value in config.items() if key not in RUNTIME_ONLY_KEYS}


def _normalize_config(data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    raw = data or {}
    normalized = deepcopy(DEFAULT_CONFIG)

    mobile_app_url = _normalize_string(raw.get("mobileAppUrl"))
    if not mobile_app_url:
        mobile_app_url = _normalize_string(raw.get("apkDownloadUrl"))
    normalized["mobileAppUrl"] = mobile_app_url
    normalized["playerAppUrl"] = _normalize_string(raw.get("playerAppUrl"))

    normalized["batteryThreshold"] = _normalize_int(raw.get("batteryThreshold"), 20, minimum=0, maximum=100)
    normalized["scanInterval"] = _normalize_int(raw.get("scanInterval"), 30, minimum=5, maximum=300)
    normalized["networkSubnet"] = _normalize_string(raw.get("networkSubnet"))
    normalized["serverPort"] = _normalize_int(raw.get("serverPort"), 8000, minimum=1, maximum=65535)
    normalized["deviceOfflineTimeout"] = _normalize_int(raw.get("deviceOfflineTimeout"), 30, minimum=10, maximum=300)

    videos = raw.get("requirementVideos", [])
    if not isinstance(videos, list):
        videos = []
    normalized["requirementVideos"] = [_normalize_video(video) for video in videos if isinstance(video, dict)]
    normalized["isAndroidRuntime"] = _is_android_runtime()
    return normalized


def _save_config_locked():
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as file_obj:
            json.dump(_serialize_storage_config(_config), file_obj, indent=2, ensure_ascii=False)
    except OSError as exc:
        logger.error("Failed to save config: %s", exc)


def load_config() -> dict:
    global _config
    with _config_lock:
        logger.info("Config file path resolved to %s", CONFIG_PATH.resolve())

        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as file_obj:
                    data = json.load(file_obj)
                _config = _normalize_config(data)
                logger.info("Config loaded from %s", CONFIG_PATH)
            except (json.JSONDecodeError, OSError) as exc:
                logger.error("Invalid config file, using defaults: %s", exc)
                _config = _normalize_config({})
                _save_config_locked()
        else:
            _config = _normalize_config({})
            _save_config_locked()
            logger.info("Created default config at %s", CONFIG_PATH)

        logger.info(
            "Runtime mode resolved: target=%s isAndroidRuntime=%s",
            _runtime_target(),
            _config["isAndroidRuntime"],
        )
        return deepcopy(_config)


def get_config() -> dict:
    with _config_lock:
        if not _config:
            return load_config()
        _config["isAndroidRuntime"] = _is_android_runtime()
        return deepcopy(_config)


def update_config(new_config: dict) -> dict:
    global _config
    with _config_lock:
        _config = _normalize_config(new_config)
        _save_config_locked()
        logger.info("Config updated")
        return deepcopy(_config)


def import_config(data: Dict[str, Any]) -> dict:
    return update_config(data)


def export_config() -> Dict[str, Any]:
    with _config_lock:
        if not _config:
            load_config()
        return _serialize_storage_config(_config)


def _save_device_names_locked():
    try:
        DEVICE_NAMES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(DEVICE_NAMES_PATH, "w", encoding="utf-8") as file_obj:
            json.dump(_device_names, file_obj, indent=2, ensure_ascii=False)
    except OSError as exc:
        logger.error("Failed to save device names: %s", exc)


def _normalize_device_names(data: Any) -> Dict[str, str]:
    if not isinstance(data, dict):
        return {}

    normalized: Dict[str, str] = {}
    for device_id, name in data.items():
        normalized_id = _normalize_string(device_id)
        normalized_name = _normalize_string(name)
        if normalized_id and normalized_name:
            normalized[normalized_id] = normalized_name
    return normalized


def load_device_names() -> dict:
    global _device_names
    with _device_names_lock:
        if DEVICE_NAMES_PATH.exists():
            try:
                with open(DEVICE_NAMES_PATH, "r", encoding="utf-8") as file_obj:
                    _device_names = _normalize_device_names(json.load(file_obj))
            except (json.JSONDecodeError, OSError):
                _device_names = {}
        return dict(_device_names)


def export_device_names() -> Dict[str, str]:
    global _device_names
    with _device_names_lock:
        if _device_names:
            return dict(_device_names)

    loaded = load_device_names()
    with _device_names_lock:
        if not _device_names:
            _device_names = dict(loaded)
        return dict(_device_names)


def replace_device_names(data: Dict[str, Any]) -> Dict[str, str]:
    global _device_names
    with _device_names_lock:
        _device_names = _normalize_device_names(data)
        _save_device_names_locked()
        return dict(_device_names)


def get_device_name(device_id: str) -> Optional[str]:
    with _device_names_lock:
        return _device_names.get(device_id)


def set_device_name(device_id: str, name: str):
    global _device_names
    normalized_id = _normalize_string(device_id)
    normalized_name = _normalize_string(name)
    if not normalized_id:
        return

    with _device_names_lock:
        if normalized_name:
            _device_names[normalized_id] = normalized_name
        else:
            _device_names.pop(normalized_id, None)
        _save_device_names_locked()
