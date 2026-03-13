from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class VideoTransformSettings(BaseModel):
    localPosition: Dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0, "z": 0.0})
    localRotation: Dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0, "z": 0.0})
    localScale: Dict[str, float] = Field(default_factory=lambda: {"x": 1.0, "y": 1.0, "z": 1.0})


class VideoMaterialSettings(BaseModel):
    tint: Dict[str, float] = Field(default_factory=lambda: {"r": 1.0, "g": 1.0, "b": 1.0, "a": 1.0})
    brightness: float = 1.0
    textureTiling: Dict[str, float] = Field(default_factory=lambda: {"x": 1.0, "y": 1.0})
    textureOffset: Dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0})
    topCrop: float = 0.0
    bottomCrop: float = 0.0


class VideoAdvancedSettings(BaseModel):
    overrideTransformSettings: bool = False
    overrideMaterialSettings: bool = False
    transformSettings: VideoTransformSettings = Field(default_factory=VideoTransformSettings)
    materialSettings: VideoMaterialSettings = Field(default_factory=VideoMaterialSettings)


class RequirementVideo(BaseModel):
    id: str = ""
    name: str = ""
    filename: str = ""
    loop: bool = False
    videoType: str = "360"
    placementMode: str = "default"
    advancedSettings: Optional[VideoAdvancedSettings] = None


class ConfigModel(BaseModel):
    mobileAppUrl: str = ""
    playerAppUrl: str = ""
    requirementVideos: List[RequirementVideo] = Field(default_factory=list)
    batteryThreshold: int = 20
    scanInterval: int = 30
    networkSubnet: str = ""
    serverPort: int = 8000
    deviceOfflineTimeout: int = 30


class DeviceRegistration(BaseModel):
    deviceId: str
    ip: str
    battery: int = -1
    deviceName: str = ""
    playerVersion: str = ""


class DeviceState:
    def __init__(self, device_id: str, ip: str):
        self.device_id: str = device_id
        self.ip: str = ip
        self.name: str = ""
        self.reported_name: str = ""
        self.battery: int = -1
        self.battery_charging: bool = False
        self.online: bool = True
        self.player_connected: bool = False
        self.player_version: str = ""
        self.requirements_met: Optional[bool] = None  # None = not checked yet
        self.requirements_detail: List[Dict] = []
        self.playback_state: str = "idle"  # idle/playing/paused/loading/completed/error
        self.current_video: str = ""
        self.current_mode: str = "360"
        self.playback_time: float = 0.0
        self.playback_duration: float = 0.0
        self.loop: bool = False
        self.locked: bool = False
        self.uptime_minutes: int = 0
        self.last_seen: float = time.time()
        self.android_id: str = ""
        self.device_model: str = ""
        self.mac_address: str = ""
        self.personal_volume: float = 1.0
        self.effective_volume: float = 1.0
        self.missed_discovery_cycles: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "deviceId": self.device_id,
            "ip": self.ip,
            "name": self.name or self.device_id,
            "battery": self.battery,
            "batteryCharging": self.battery_charging,
            "online": self.online,
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
            "androidId": self.android_id,
            "deviceModel": self.device_model,
            "macAddress": self.mac_address,
            "personalVolume": self.personal_volume,
            "effectiveVolume": self.effective_volume,
        }


class PlaybackCommand(BaseModel):
    deviceIds: List[str] = []


class OpenCommand(BaseModel):
    videoId: str = ""
    deviceIds: List[str] = []


class DeviceNameUpdate(BaseModel):
    name: str

class VolumeUpdate(BaseModel):
    volume: float = Field(ge=0.0, le=1.0)


class DeviceVolumeUpdate(VolumeUpdate):
    deviceId: str
