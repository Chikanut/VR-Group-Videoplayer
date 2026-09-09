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


class VideoProbeInfo(BaseModel):
    """Technical data read from the video file headers (see video_probe.py)."""
    width: int = 0
    height: int = 0
    fps: float = 0.0
    codec: str = ""
    bitDepth: int = 0
    chromaFormat: str = ""
    profile: str = ""
    tier: str = ""
    level: str = ""
    bitrateMbps: float = 0.0
    durationSec: float = 0.0
    sizeBytes: int = 0
    container: str = ""
    faststart: bool = False
    colorPrimaries: int = 0
    colorTransfer: int = 0
    colorMatrix: int = 0
    pixelAspect: str = ""
    audioCodec: str = ""
    audioChannels: int = 0
    audioSampleRate: int = 0
    trackTypes: List[str] = Field(default_factory=list)
    metadataProjection: str = ""   # verbatim from the file, NOT trusted
    metadataStereo: str = ""
    metadataSource: str = ""
    projectionBounds: Dict[str, float] = Field(default_factory=dict)
    detectedType: str = ""         # result of auto-detection
    detectionSource: str = ""      # "manual" | "filename" | "aspect+metadata" | "aspect" | "metadata" | "default"
    autoDetectedType: str = ""     # auto-detection result even when a manual format was given
    autoDetectionSource: str = ""
    warnings: List[str] = Field(default_factory=list)


class RequirementVideo(BaseModel):
    id: str = ""
    name: str = ""
    filename: str = ""
    loop: bool = False
    # Canonical formatId: 2d | 360 | 360_sbs | 360_tb | 180 | 180_sbs | 180_tb | auto.
    # Aliases (sphere, flat, 180_LR, 360_OU ...) are normalized by config.py.
    videoType: str = "360"
    placementMode: str = "default"
    swapEyes: bool = False
    forwardYaw: float = 0.0
    detectedType: str = ""
    detectionSource: str = ""
    probe: Optional[VideoProbeInfo] = None
    advancedSettings: Optional[VideoAdvancedSettings] = None


class VideoProbeRequest(BaseModel):
    """POST /api/videos/probe body: a path on the control-panel machine."""
    path: str
    filename: str = ""      # override the name used for suffix detection (defaults to basename)
    videoType: str = "auto"  # manual format, or "auto" to detect


class VideoDetectRequest(BaseModel):
    """POST /api/videos/detect body: filename-only detection (no file access)."""
    filename: str
    videoType: str = "auto"


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
        self.current_mode: str = "360"          # legacy "360" / "2d" as reported by the player
        self.current_projection: str = ""       # "flat" | "180" | "360" (derived from mode for old players)
        self.current_stereo: str = ""           # "mono" | "sbs" | "tb"
        self.swap_eyes: bool = False
        self.video_width: int = 0
        self.video_height: int = 0
        self.backend: str = ""                  # "unity" | "native" | "" (old player)
        self.decoder_caps: Dict[str, Any] = {}  # from /status decoderCaps, empty for old players
        self.stereo_capable: Optional[bool] = None  # None = unknown, False = pre-stereo player
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
        self.ws_connected: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "deviceId": self.device_id,
            "ip": self.ip,
            "name": self.name or self.device_id,
            "battery": self.battery,
            "batteryCharging": self.battery_charging,
            "online": self.online,
            "playerConnected": self.player_connected,
            "wsConnected": self.ws_connected,
            "playerVersion": self.player_version,
            "requirementsMet": self.requirements_met,
            "requirementsDetail": self.requirements_detail,
            "playbackState": self.playback_state,
            "currentVideo": self.current_video,
            "currentMode": self.current_mode,
            "currentProjection": self.current_projection,
            "currentStereo": self.current_stereo,
            "swapEyes": self.swap_eyes,
            "videoWidth": self.video_width,
            "videoHeight": self.video_height,
            "backend": self.backend,
            "decoderCaps": self.decoder_caps,
            "stereoCapable": self.stereo_capable,
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


class SeekCommand(BaseModel):
    deviceIds: List[str] = []
    time: float = Field(ge=0.0)


class DeviceNameUpdate(BaseModel):
    name: str

class VolumeUpdate(BaseModel):
    volume: float = Field(ge=0.0, le=1.0)


class DeviceVolumeUpdate(VolumeUpdate):
    deviceId: str
