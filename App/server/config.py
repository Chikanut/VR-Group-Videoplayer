import json
import logging
import os
import socket
import shutil
import uuid
from copy import deepcopy
from pathlib import Path
from threading import Lock
from typing import Optional, Tuple

logger = logging.getLogger("vrclassroom.config")

CONFIG_PATH = Path(__file__).parent.parent / "config.json"
DEVICE_NAMES_PATH = Path(__file__).parent.parent / "device_names.json"

DEFAULT_CONFIG = {
    "apkPath": "",
    "packageId": "com.vrclass.player",
    "adbActionPrefix": "com.vrclass.player",
    "requirementVideos": [],
    "batteryThreshold": 20,
    "scanInterval": 30,
    "networkSubnet": "",
    "networkSubnetAuto": True,
    "serverPort": 8000,
    "playerPort": 8080,
    "deviceOfflineTimeout": 30,
    "updateConcurrency": 5,
    "ignoreRequirements": False,
    "adbAvailable": True,
}

DEVICE_VIDEO_DIR = "/sdcard/Movies"

_config: dict = {}
_config_lock = Lock()
_device_names: dict = {}
_device_names_lock = Lock()


def _is_android_runtime() -> bool:
    return bool(os.environ.get("ANDROID_ARGUMENT") or os.environ.get("ANDROID_PRIVATE"))


def detect_adb_available() -> bool:
    if _is_android_runtime():
        return False
    if os.environ.get("VRCLASSROOM_DISABLE_ADB", "").lower() in {"1", "true", "yes", "on"}:
        return False
    return shutil.which("adb") is not None


ADB_AVAILABLE = detect_adb_available()


def _extract_subnet(ip_addr: str) -> str:
    parts = ip_addr.split(".")
    if len(parts) != 4:
        return ""
    if any(not part.isdigit() for part in parts):
        return ""
    return f"{parts[0]}.{parts[1]}.{parts[2]}"


def _detect_android_hotspot_subnet_with_source() -> Tuple[str, str]:
    """Best-effort detection of active hotspot/LAN subnet on Android runtime."""
    override = os.environ.get("VRCLASSROOM_ANDROID_SUBNET", "").strip()
    if override:
        return override, "env_override"

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route_sock:
            route_sock.connect(("8.8.8.8", 80))
            local_ip = route_sock.getsockname()[0]
        subnet = _extract_subnet(local_ip)
        if subnet:
            return subnet, "route"
    except OSError:
        pass

    try:
        hostname = socket.gethostname()
        for addr in socket.gethostbyname_ex(hostname)[2]:
            if not addr or addr.startswith("127."):
                continue
            subnet = _extract_subnet(addr)
            if subnet:
                return subnet, "hostname"
    except OSError:
        pass

    candidates = [
        "192.168.43",   # Android legacy hotspot
        "192.168.232",  # Android 11+ hotspot (common)
        "172.20.10",    # iOS hotspot (shared networks)
    ]

    return candidates[0], "fallback_candidates"


def detect_android_hotspot_subnet() -> str:
    subnet, _ = _detect_android_hotspot_subnet_with_source()
    return subnet


def load_config() -> dict:
    global _config
    with _config_lock:
        should_save_config = False
        detected_subnet = ""
        detected_subnet_source = "n/a"

        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, "r") as f:
                    data = json.load(f)
                # Merge with defaults, ignore unknown fields from old configs gracefully
                _config = {**deepcopy(DEFAULT_CONFIG)}
                for key in DEFAULT_CONFIG:
                    if key in data:
                        _config[key] = data[key]
                # Preserve extra keys that might be needed
                for key in data:
                    if key not in _config:
                        _config[key] = data[key]

                if "networkSubnet" in data and "networkSubnetAuto" not in data:
                    _config["networkSubnetAuto"] = True
                    should_save_config = True
                    logger.info(
                        "Config migration: existing networkSubnet detected without networkSubnetAuto; "
                        "defaulting to auto mode for Android compatibility"
                    )
                logger.info("Config loaded from %s", CONFIG_PATH)
            except (json.JSONDecodeError, OSError) as e:
                logger.error("Invalid config file, using defaults: %s", e)
                _config = deepcopy(DEFAULT_CONFIG)
        else:
            _config = deepcopy(DEFAULT_CONFIG)
            _save_config_locked()
            logger.info("Created default config at %s", CONFIG_PATH)

        if _is_android_runtime():
            detected_subnet, detected_subnet_source = _detect_android_hotspot_subnet_with_source()
            if _config.get("networkSubnetAuto", True):
                if _config.get("networkSubnet") != detected_subnet:
                    _config["networkSubnet"] = detected_subnet
                    should_save_config = True
            elif not _config.get("networkSubnet"):
                _config["networkSubnet"] = detected_subnet
                should_save_config = True
                logger.warning(
                    "networkSubnetAuto=false but networkSubnet is empty; "
                    "falling back to detected subnet"
                )

        _config["adbAvailable"] = ADB_AVAILABLE

        logger.info(
            "Network config at runtime: networkSubnet=%s, networkSubnetAuto=%s, detectedSubnet=%s, source=%s",
            _config.get("networkSubnet", ""),
            _config.get("networkSubnetAuto", True),
            detected_subnet,
            detected_subnet_source if _is_android_runtime() else "n/a",
        )

        if should_save_config:
            _save_config_locked()

        return deepcopy(_config)


def _save_config_locked():
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(_config, f, indent=2)
    except OSError as e:
        logger.error("Failed to save config: %s", e)


def get_config() -> dict:
    with _config_lock:
        if _config:
            _config["adbAvailable"] = ADB_AVAILABLE
        return deepcopy(_config)


def update_config(new_config: dict) -> dict:
    global _config
    with _config_lock:
        _config.update(new_config)
        _config["adbAvailable"] = ADB_AVAILABLE
        # Ensure requirement videos have IDs and strip legacy devicePath
        for video in _config.get("requirementVideos", []):
            if not video.get("id"):
                video["id"] = str(uuid.uuid4())
            video.pop("devicePath", None)
        _save_config_locked()
        logger.info("Config updated")
        return deepcopy(_config)


def get_device_video_path(local_path: str) -> str:
    """Compute the device path for a video: /sdcard/Movies/<filename>."""
    basename = os.path.basename(local_path)
    return f"{DEVICE_VIDEO_DIR}/{basename}"


def load_device_names() -> dict:
    global _device_names
    with _device_names_lock:
        if DEVICE_NAMES_PATH.exists():
            try:
                with open(DEVICE_NAMES_PATH, "r") as f:
                    _device_names = json.load(f)
            except (json.JSONDecodeError, OSError):
                _device_names = {}
        return dict(_device_names)


def get_device_name(device_id: str) -> Optional[str]:
    with _device_names_lock:
        return _device_names.get(device_id)


def set_device_name(device_id: str, name: str):
    global _device_names
    with _device_names_lock:
        _device_names[device_id] = name
        try:
            with open(DEVICE_NAMES_PATH, "w") as f:
                json.dump(_device_names, f, indent=2)
        except OSError as e:
            logger.error("Failed to save device names: %s", e)
