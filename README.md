# VR Group Videoplayer

A classroom/training management system for synchronized VR video playback on Meta Quest headsets. Control an entire fleet of Quest devices from a single web dashboard — push videos, install apps, and control playback simultaneously.

## Overview

The system consists of two components:

- **Control Panel** (`App/`) — A Python FastAPI server with a React web interface, running on the instructor's PC
- **VR Player** (`VRClassroomPlayer/`) — A Unity application installed on Meta Quest headsets

The instructor accesses the web dashboard at `http://localhost:8000`, where they can discover headsets on the network, push content, and control synchronized video playback in 360° or flat 2D modes.

## Features

### Control Panel (Web Dashboard)
- **Automatic Device Discovery** — Scans the local network for Quest devices via ADB (Wi-Fi and USB)
- **Video & APK Management** — Push video files and install/upgrade the player app with version comparison and real-time progress
- **Synchronized Playback** — Play, pause, stop, recenter across all devices simultaneously
- **USB Initialization** — Connect new headsets via USB cable for one-click setup (APK + videos + enable Wi-Fi ADB)
- **File Browser** — Browse the server filesystem to select files (no manual path typing)
- **Real-time Monitoring** — WebSocket-based live updates for device status, battery, playback progress
- **QR Connection** — Small "CONNECTION" button shows a QR code so you can open the dashboard from a phone
- **HTTP + ADB Fallback** — Commands prioritize the player's HTTP API, fall back to ADB when unavailable

### VR Player (Quest App)
- **360° Sphere & Flat 2D Modes** — Switch between immersive 360° and traditional flat video viewing
- **Dynamic Resolution** — RenderTexture automatically resizes to match video file resolution (up to 4096)
- **Recenter** — Rotates the video sphere/plane to face the viewer's current gaze direction
- **Remote Control** — HTTP API (port 8080) and ADB broadcast intents for all commands
- **Status Reporting** — Periodic heartbeat with playback state, battery, device info
- **Debug Panel** — On-screen log overlay, toggleable via command or triple-tap controller button
- **Lock Mode** — Instructor can lock playback controls on the headset

## Requirements

- **Python 3.10+**
- **Node.js 18+** (for building the frontend)
- **ADB** (Android Debug Bridge) — from [Android Platform Tools](https://developer.android.com/tools/releases/platform-tools)
- **aapt2** (optional) — for APK version detection (included in Android build-tools)
- **Unity 2021+** (for building the VR player from source)
- **Meta Quest headset(s)** with developer mode enabled

## Quick Start

### Windows
```
start.bat
```

### Linux / macOS
```bash
chmod +x start.sh
./start.sh
```

The launcher script will:
1. Create a Python virtual environment
2. Install Python dependencies
3. Build the React frontend (if Node.js is available)
4. Start the server at `http://localhost:8000`

### Connecting from a Phone
Click the small "CONNECTION" button in the bottom-right corner of the web UI to see a QR code with the server's network URL.

### Windows EXE Build (for end users)

If you want to distribute the control panel as a single `.exe`:

```bat
cd App
build_windows_exe.bat
```

Result: `App/dist/VRClassroomControl.exe` (built via PyInstaller, includes frontend assets).

## Manual Setup

```bash
# Python backend
cd App
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt

# React frontend
cd frontend
npm install
npm run build
cd ..

# Start server
python run.py
```

## Configuration

All settings are managed through the web UI at `/settings`:

| Setting | Default | Description |
|---------|---------|-------------|
| APK Path | — | Path to the VR player APK on the server |
| Package ID | `com.vrclassroom.player` | Android package name |
| Requirement Videos | — | List of videos to push to devices (name, path, type, loop) |
| Ignore Requirements | Off | Send playback commands even if content isn't pushed yet |
| Network Subnet | auto-detect | Override network range for device scanning |
| Battery Threshold | 20% | Low battery warning level |
| Server Port | 8000 | Web dashboard port |
| Player Port | 8080 | VR player HTTP API port |
| Scan Interval | 30s | How often to re-scan for devices |
| Update Concurrency | 5 | Max simultaneous device updates |

Videos are stored at `/sdcard/Movies/` on Quest devices.

## Architecture

```
┌─────────────────┐        ┌──────────────────────────────┐
│   Web Browser    │◄──────►│  FastAPI Server (port 8000)  │
│  (React + Vite)  │   WS   │                              │
└─────────────────┘        │  ┌────────────────────────┐  │
                           │  │  Device Manager         │  │
                           │  │  Discovery Loop         │  │
                           │  │  Playback Controller    │  │
                           │  │  Requirements Manager   │  │
                           │  └────────────────────────┘  │
                           └──────────┬───────────────────┘
                                      │ HTTP / ADB
                           ┌──────────▼───────────────────┐
                           │  Meta Quest Headsets          │
                           │  ┌────────────────────────┐  │
                           │  │  Unity VR Player        │  │
                           │  │  HTTP Server (8080)     │  │
                           │  │  ADB Broadcast Receiver │  │
                           │  │  360° Sphere / 2D Flat  │  │
                           │  └────────────────────────┘  │
                           └──────────────────────────────┘
```

### Communication Flow

1. **Web UI → Server**: REST API calls + WebSocket for real-time updates
2. **Server → Quest**: HTTP API to player app (primary) or ADB broadcast (fallback)
3. **Quest → Server**: Self-registration heartbeat every 10s, status reports every 2s
4. **Server → Web UI**: WebSocket broadcasts for device state changes

## Server API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/config` | GET/PUT | Get or update configuration |
| `/api/devices` | GET | List all discovered devices |
| `/api/devices/{id}` | GET | Single device details |
| `/api/devices/{id}/name` | PUT | Rename a device |
| `/api/devices/{id}` | DELETE | Remove device from list |
| `/api/devices/{id}/update` | POST | Push missing content (APK + videos) |
| `/api/devices/update-all` | POST | Update all devices needing content |
| `/api/devices/{id}/ping` | POST | Send audible beep to device |
| `/api/devices/launch-player` | POST | Start player app via ADB |
| `/api/usb-devices` | GET | List USB-connected devices |
| `/api/usb-devices/{serial}/update` | POST | Initialize USB device |
| `/api/browse` | GET | Browse server filesystem |
| `/api/server-info` | GET | Server IP and port (for QR code) |
| `/api/playback/open` | POST | Open video on devices |
| `/api/playback/play` | POST | Resume playback |
| `/api/playback/pause` | POST | Pause playback |
| `/api/playback/stop` | POST | Stop playback |
| `/api/playback/recenter` | POST | Recenter VR view |
| `/ws` | WebSocket | Real-time device updates |

## VR Player API

The VR player app on each Quest headset exposes an HTTP server on port 8080 and accepts ADB broadcast intents. See [PlayerAPI.md](PlayerAPI.md) for the complete reference.

### Key Commands

| Command | HTTP | ADB |
|---------|------|-----|
| Open video | `POST /open` | `am broadcast -a com.vrclass.player.OPEN --es file "video.mp4"` |
| Play | `POST /play` | `am broadcast -a com.vrclass.player.PLAY` |
| Pause | `POST /pause` | `am broadcast -a com.vrclass.player.PAUSE` |
| Stop | `POST /stop` | `am broadcast -a com.vrclass.player.STOP` |
| Recenter | `POST /recenter` | `am broadcast -a com.vrclass.player.RECENTER` |
| Status | `GET /status` | `am broadcast -a com.vrclass.player.GET_STATUS` |

### View Modes

| Mode | Description |
|------|-------------|
| `360` / `sphere` | Equirectangular 360° — viewer inside a UV-mapped sphere |
| `2d` / `flat` | Flat screen — video displayed on a quad in front of the viewer |

## 360 Video Technical Details

### Current Rendering

- **Sphere360**: Unity default sphere scaled to (-100, 100, 100), viewer at center
- **Shader**: Cull Front (see inside), mirror U coordinate (`1.0 - uv.x`) to correct horizontal flip
- **RenderTexture**: Dynamically resized to match video resolution (e.g. 3840x1920 for 4K equirectangular)

### Recenter Behavior

When recenter is triggered:
1. **Content rotation**: The sphere/plane parent rotates to align its "front" with the viewer's current yaw (horizontal gaze direction)
2. **XR recenter**: Calls `XRInputSubsystem.TryRecenter()` to reset the Quest tracking origin

This ensures the "front" of the 360 video is always where the viewer is looking when they hit recenter.

### Planned: Stereoscopic 3D Support

Future support for stereo 360 video (Side-by-Side and Over-Under layouts):
- UV adjustment per eye via `unity_StereoEyeIndex` in shader
- SBS: each eye samples half the texture width
- OU: each eye samples half the texture height
- Video type passed via `stereoLayout` parameter in open command

### Planned: Additional Formats

- **VR180**: Half-sphere rendering for 180° content
- **EAC (Equi-Angular Cubemap)**: YouTube/Google projection format
- **Ambisonics**: Spatial audio support for 360 content via Unity AudioSource spatializer

## Project Structure

```
VR-Group-Videoplayer/
├── App/                          # Control panel
│   ├── server/                   # Python FastAPI backend
│   ├── frontend/                 # React + Vite web UI
│   ├── run.py                    # Entry point
│   └── requirements.txt
├── VRClassroomPlayer/            # Unity project for Quest
│   └── Assets/
│       ├── Scripts/              # C# controllers and managers
│       └── Shaders/              # Video rendering shaders
├── PlayerAPI.md                  # VR player API reference
├── CLAUDE.md                     # AI development instructions
├── README.md                     # This file
├── start.sh                      # Linux/macOS launcher
└── start.bat                     # Windows launcher
```

## Development

### Frontend Development (with hot reload)
```bash
cd App/frontend
npm run dev    # Vite dev server with HMR
```

### Server Development
```bash
cd App
python run.py  # Auto-serves built frontend from frontend/dist/
```

### Unity VR Player
Open `VRClassroomPlayer/` in Unity Hub. Build for Android (Meta Quest).

## License

This project is proprietary. All rights reserved.
