from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, Field




class VideoTransformSettings(BaseModel):
    localPosition: dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0, "z": 0.0})
    localRotation: dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0, "z": 0.0})
    localScale: dict[str, float] = Field(default_factory=lambda: {"x": 1.0, "y": 1.0, "z": 1.0})


class VideoMaterialSettings(BaseModel):
    tint: dict[str, float] = Field(default_factory=lambda: {"r": 1.0, "g": 1.0, "b": 1.0, "a": 1.0})
    brightness: float = 1.0
    textureTiling: dict[str, float] = Field(default_factory=lambda: {"x": 1.0, "y": 1.0})
    textureOffset: dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0})


class VideoAdvancedSettings(BaseModel):
    overrideTransformSettings: bool = False
    overrideMaterialSettings: bool = False
    transformSettings: VideoTransformSettings = Field(default_factory=VideoTransformSettings)
    materialSettings: VideoMaterialSettings = Field(default_factory=VideoMaterialSettings)


class RequirementVideo(BaseModel):
    id: str = ""
    name: str = ""
    localPath: str = ""
    loop: bool = False
    videoType: str = "360"
    advancedSettings: VideoAdvancedSettings | None = None


class ConfigModel(BaseModel):
    apkPath: str = ""
    packageId: str = "com.vrclassroom.player"
    requirementVideos: list[RequirementVideo] = []
    batteryThreshold: int = 20
    scanInterval: int = 30
    networkSubnet: str = ""
    serverPort: int = 8000
    playerPort: int = 8080
    deviceOfflineTimeout: int = 30
    statusPollInterval: int = 5
    updateConcurrency: int = 5
    ignoreRequirements: bool = False


class DeviceRegistration(BaseModel):
    deviceId: str
    ip: str
    battery: int = -1
    deviceName: str = ""
    playerVersion: str = ""
    installedPackages: list[str] = []


class DeviceState:
    def __init__(self, device_id: str, ip: str):
        self.device_id: str = device_id
        self.ip: str = ip
        self.name: str = ""
        self.battery: int = -1
        self.battery_charging: bool = False
        self.online: bool = True
        self.adb_connected: bool = False
        self.player_connected: bool = False
        self.player_version: str = ""
        self.requirements_met: bool | None = None  # None = not checked yet
        self.requirements_detail: list[dict] = []
        self.playback_state: str = "idle"  # idle/playing/paused/loading/completed/error
        self.current_video: str = ""
        self.current_mode: str = "360"
        self.playback_time: float = 0.0
        self.playback_duration: float = 0.0
        self.loop: bool = False
        self.locked: bool = False
        self.uptime_minutes: int = 0
        self.last_seen: float = time.time()
        self.last_player_response: float = 0.0
        self.installed_packages: list[str] = []
        self.update_in_progress: bool = False
        self.update_progress: dict | None = None
        self.usb_connected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "deviceId": self.device_id,
            "ip": self.ip,
            "name": self.name or self.device_id,
            "battery": self.battery,
            "batteryCharging": self.battery_charging,
            "online": self.online,
            "adbConnected": self.adb_connected,
            "playerConnected": self.player_connected,
            "playerVersion": self.player_version,
            "requirementsMet": self.requirements_met,
            "requirementsDetail": self.requirements_detail,
            "playbackState": self.playback_state,
            "currentVideo": self.current_video,
            "currentMode": self.current_mode,
            "playbackTime": self.playback_time,
            "playbackDuration": self.playback_duration,
            "loop": self.loop,
            "locked": self.locked,
            "uptimeMinutes": self.uptime_minutes,
            "lastSeen": self.last_seen,
            "installedPackages": self.installed_packages,
            "updateInProgress": self.update_in_progress,
            "updateProgress": self.update_progress,
            "usbConnected": self.usb_connected,
        }


class PlaybackCommand(BaseModel):
    deviceIds: list[str] = []


class OpenCommand(BaseModel):
    videoId: str = ""
    deviceIds: list[str] = []


class DeviceNameUpdate(BaseModel):
    name: str


class UsbInitOptions(BaseModel):
    enableWirelessAdb: bool = True
    updateApp: bool = True
    updateContent: bool = True
