# VR Group Videoplayer — Control Panel

Control panel for managing Meta Quest headsets over the local network.

Current architecture is **HTTP + WebSocket only**. ADB/USB provisioning flow has been removed.

## What It Does

- Discovers player devices on the local network
- Shows live device status in the dashboard
- Stores a simple list of required videos by **filename**
- Sends playback commands to one device or all devices
- Checks whether configured filenames exist on each player
- Lets you import/export `config.json` and `device_names.json`
- Shows QR codes for web control access and player app download link

## Requirements

- Python 3.10+
- Node.js 18+ for frontend builds

## Quick Start

### Windows

```bat
start.bat
```

### Linux / macOS

```bash
chmod +x start.sh
./start.sh
```

### Manual

```bash
cd App
pip install -r requirements.txt
cd frontend
npm install
npm run build
cd ..
python run.py
```

Open [http://localhost:8000](http://localhost:8000).

## Settings Model

The app now keeps a much simpler config:

- `playerAppUrl`
- `requirementVideos`
- `batteryThreshold`
- `scanInterval`
- `networkSubnet`
- `serverPort`
- `deviceOfflineTimeout`

Each required video stores:

- `id`
- `name`
- `filename`
- `videoType`
- `loop`
- `placementMode`
- optional `advancedSettings`

Important: only the **filename** is stored and sent to the player. The player opens files from `/sdcard/Movies/`.

## Import / Export

The Settings page supports:

- Import `config.json`
- Import `device_names.json`
- Export current `config.json`
- Export current `device_names.json`

Import fully replaces the current data on the app.

## Android Build Note

The Android control-panel wrapper now starts from default settings and does **not** package the current repo `config.json` or `device_names.json` into the APK.

## Main API

| Endpoint | Method | Description |
|---|---|---|
| `/api/config` | GET / PUT | Read or replace config |
| `/api/device-names` | GET / PUT | Read or replace device names |
| `/api/devices` | GET | List discovered devices |
| `/api/devices/{id}/name` | PUT | Rename one device |
| `/api/devices/{id}/requirements` | GET | Re-check filenames on one device |
| `/api/playback/open` | POST | Open one configured video |
| `/api/playback/play` | POST | Play |
| `/api/playback/pause` | POST | Pause |
| `/api/playback/stop` | POST | Stop |
| `/api/playback/recenter` | POST | Recenter |
| `/api/playback/volume/global` | GET / POST | Global volume |
| `/api/devices/{id}/volume` | POST | Per-device volume |
| `/ws` | WebSocket | Frontend live updates |
| `/ws/device` | WebSocket | Player live connection |
