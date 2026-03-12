# VR Group Videoplayer

VR Group Videoplayer is a two-part classroom VR video system:

1. `App/` — instructor control panel built with FastAPI + React
2. `VRClassroomPlayer/` — Unity player app running on Meta Quest

The system now uses **HTTP + WebSocket only**. ADB and USB provisioning logic have been removed from both the control panel and the player.

## Main Flow

- The control panel scans the local subnet for players on port `8080`
- Players expose HTTP endpoints and connect back over WebSocket
- The dashboard shows device state, battery, playback, and file availability
- Videos are configured by **filename only**
- When playback starts, the control panel sends just the filename
- The player opens that filename from `/sdcard/Movies/`

## Current Feature Set

- Network discovery of Quest players
- Live dashboard with playback/battery/device state
- Playback control for all devices or a single device
- Per-device and global volume control
- Configurable required videos by filename
- Import/export of `config.json` and `device_names.json`
- Player app download link with QR code in the connection popup
- Per-video placement override:
  - `default`
  - `locked`
  - `free`

## Repository Structure

```text
App/                 Control panel (FastAPI + React)
VRClassroomPlayer/   Unity player for Meta Quest
PlayerAPI.md         Player HTTP API reference
```

## Quick Start

### Control Panel

```bash
cd App
pip install -r requirements.txt
cd frontend
npm install
npm run build
cd ..
python run.py
```

### Player

Open `VRClassroomPlayer/` in Unity, build for Quest, and install the APK on the headset.

## Key Paths and Ports

- Control panel: `http://localhost:8000`
- Player HTTP API: `http://<device-ip>:8080`
- Player video directory: `/sdcard/Movies/`

## Notes

- The Android control-panel wrapper no longer bakes the repo's current `config.json` or `device_names.json` into the app.
- Older player versions safely ignore the new `placementMode` field.
- The control panel repo `App/config.json` is now a default template rather than a machine-specific runtime config.
