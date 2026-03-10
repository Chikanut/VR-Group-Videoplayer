# VR Group Videoplayer — Control Panel

> See the [root README](../README.md) for the full project overview.

Control panel for managing a fleet of Meta Quest VR headsets in a classroom / training environment.
Push videos, install apps, and control playback across multiple devices simultaneously from a single web interface.

## Features

- **Device Discovery** - Automatic network scanning finds Quest devices via ADB (Wi-Fi and USB)
- **Video Management** - Push video files to devices with real-time progress tracking
- **APK Management** - Install and auto-upgrade the VR player app with version comparison
- **Playback Control** - Play, pause, stop, recenter on all devices simultaneously
- **Media Scanner** - Files are automatically registered with Android after push (visible in file manager)
- **USB Initialization** - Connect new headsets via USB cable for automated setup (APK + videos + enable wireless ADB)
- **File Picker** - Browse server file system to select APK and video files (no manual path typing)
- **Ignore Requirements** - Optional mode to send commands regardless of requirement status
- **Real-time Monitoring** - WebSocket-based live updates for device status, battery, and progress
- **HTTP + ADB Fallback** - Commands prioritize HTTP API, fall back to ADB when player is unavailable

## Requirements

- **Python 3.10+**
- **Node.js 18+** (for building frontend)
- **ADB** (Android Debug Bridge) - from [Android Platform Tools](https://developer.android.com/tools/releases/platform-tools)
- **aapt2** (optional) - for APK version detection (included in Android build-tools)

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
2. Install dependencies
3. Build the frontend (if Node.js is available)
4. Start the server on `http://localhost:8000`

## Manual Setup

```bash
# Install Python dependencies
cd App
pip install -r requirements.txt

# Build frontend
cd frontend
npm install
npm run build
cd ..

# Start server
python run.py
```

## Android APK (no-ADB mode)

У репозиторії додано scaffold для Android пакування через **Chaquopy**:

- Проєкт: `App/android/chaquopy`
- Runtime режим: ADB вимикається автоматично (`adbAvailable=false`)
- UI: WebView wrapper, який відкриває `http://127.0.0.1:8000`

Базові кроки:

1. Відкрити `App/android/chaquopy` в Android Studio.
2. Запустити `app` на Android пристрої.
3. Додаток підніме FastAPI у background service і покаже control panel у WebView.

## Configuration

All settings are managed through the web UI at `/settings`:

- **APK Path** - Select the player APK file via file browser
- **Package ID** - Android package name (default: `com.vrclassroom.player`)
- **Requirement Videos** - List of video files to push to devices
- **Ignore Requirements** - Allow commands even if requirements are not met
- **Network Subnet** - Manual subnet override (auto-detected by default)
- **Battery Threshold** - Low battery warning level

Videos are always stored at `/sdcard/Movies/<filename>` on devices.

## Architecture

- **Backend**: FastAPI (Python) with async ADB and HTTP device management
- **Frontend**: React + Vite + Zustand, served as static files by FastAPI
- **Communication**: WebSocket for real-time updates, HTTP REST API for commands
- **Device Control**: HTTP API (player app) with ADB fallback

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/config` | GET/PUT | Get or update configuration |
| `/api/devices` | GET | List all devices |
| `/api/devices/{id}/update` | POST | Push missing content to device |
| `/api/devices/update-all` | POST | Update all devices |
| `/api/usb-devices` | GET | List USB-connected devices |
| `/api/usb-devices/{serial}/update` | POST | Initialize USB device |
| `/api/browse` | GET | Browse server file system |
| `/api/playback/open` | POST | Open video on devices |
| `/api/playback/play\|pause\|stop\|recenter` | POST | Playback control |
| `/ws` | WebSocket | Real-time device updates |
