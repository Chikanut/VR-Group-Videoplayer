# AGENTS.md — VR Group Videoplayer

Instructions and context for AI-assisted development with Codex.

## Project Overview

VR Group Videoplayer is a classroom VR video management system with two main components:

1. **Control Panel (App/)** — Python FastAPI server + React frontend for managing Meta Quest headsets
2. **VR Player (VRClassroomPlayer/)** — Unity C# application running on Meta Quest headsets

The system allows an instructor to discover Quest headsets on a local network, push video content, and control synchronized playback from a single web dashboard.

## Repository Structure

```
VR-Group-Videoplayer/
├── App/                              # Control panel (server + web UI)
│   ├── server/                       # Python FastAPI backend
│   │   ├── main.py                   # FastAPI app, all HTTP/WS endpoints
│   │   ├── config.py                 # Config persistence (config.json)
│   │   ├── models.py                 # Pydantic data models
│   │   ├── device_manager.py         # Device state tracking, WebSocket broadcasting
│   │   ├── device_discovery.py       # Network scanning, ADB + HTTP discovery
│   │   ├── playback_controller.py    # Send commands to devices (HTTP + ADB fallback)
│   │   ├── adb_executor.py           # ADB command wrapper with per-device locks
│   │   ├── requirements_manager.py   # APK + video push logic, progress tracking
│   │   └── websocket_manager.py      # WebSocket client management
│   ├── frontend/                     # React + Vite frontend
│   │   ├── src/
│   │   │   ├── App.jsx               # Router (/ and /settings)
│   │   │   ├── main.jsx              # React entry point
│   │   │   ├── api.js                # HTTP API client functions
│   │   │   ├── store/deviceStore.js  # Zustand state management
│   │   │   ├── hooks/useWebSocket.js # WebSocket hook with reconnection
│   │   │   ├── components/
│   │   │   │   ├── Layout.jsx        # Main page layout
│   │   │   │   ├── TopControlPanel.jsx
│   │   │   │   ├── DeviceGrid.jsx
│   │   │   │   ├── DeviceTile.jsx
│   │   │   │   ├── DeviceDialog.jsx
│   │   │   │   ├── VideoSelector.jsx
│   │   │   │   ├── FilePicker.jsx
│   │   │   │   ├── SettingsPage.jsx
│   │   │   │   ├── UpdateProgress.jsx
│   │   │   │   └── ConnectionButton.jsx  # QR code for phone connection
│   │   │   └── styles/globals.css    # All CSS styles
│   │   └── dist/                     # Built frontend (served by FastAPI)
│   ├── run.py                        # Server entry point
│   └── requirements.txt
├── VRClassroomPlayer/                # Unity project (Meta Quest)
│   └── Assets/
│       ├── Scripts/
│       │   ├── Core/
│       │   │   ├── VideoPlayerController.cs   # Video playback, RenderTexture management
│       │   │   ├── ViewModeManager.cs         # Sphere360 / Flat2D display switching
│       │   │   ├── ViewModeConfig.cs          # ScriptableObject per view mode
│       │   │   ├── ViewMode.cs                # Enum: Flat2D, Sphere360
│       │   │   ├── PlayerConfig.cs            # Constants (ports, paths, defaults)
│       │   │   ├── PlayerState.cs             # Enum: Idle, Loading, Playing, etc.
│       │   │   ├── PlayerStateManager.cs      # Central state singleton
│       │   │   ├── OrientationManager.cs      # Recenter: XR + content rotation
│       │   │   ├── StatusReporter.cs          # Status JSON, heartbeat to server
│       │   │   └── VideoRenderShaderFactory.cs # Material creation, shader resolution
│       │   ├── ADB/
│       │   │   ├── ADBCommandRouter.cs        # Intent → command dispatch
│       │   │   └── ADBReceiverBridge.cs       # Java ↔ C# bridge
│       │   ├── Network/
│       │   │   └── LanServer.cs               # HTTP server on port 8080
│       │   └── UI/
│       │       ├── PlayerHUD.cs               # VR HUD (state, file, IP)
│       │       └── DebugLogPanel.cs           # On-screen debug log
│       └── Shaders/
│           ├── VideoSphere.shader             # Inside-sphere rendering (Cull Front, mirror U)
│           └── VideoFlat.shader               # Standard quad rendering
├── PlayerAPI.md                       # Player HTTP+ADB API reference (Ukrainian)
├── start.sh / start.bat               # Quick start launchers
└── AGENTS.md                          # This file
```

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Server backend | Python 3.10+, FastAPI, aiohttp, asyncio |
| Web frontend | React 18, Vite 5, Zustand, react-router-dom |
| VR player | Unity (2021+/6000+), C#, Meta XR SDK |
| Device communication | HTTP REST (port 8080), ADB broadcasts, WebSocket |
| Shaders | Unity CG/HLSL (Cull Front for sphere, stereo-ready) |

## Development Commands

### Server (App/)
```bash
cd App
python3 -m venv venv && source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
python run.py                                       # Starts on http://localhost:8000
```

### Frontend (App/frontend/)
```bash
cd App/frontend
npm install
npm run dev      # Dev server with HMR
npm run build    # Production build to dist/
```

### Quick Start
```bash
./start.sh       # Linux/macOS — creates venv, installs deps, builds frontend, starts server
start.bat        # Windows equivalent
```

## Architecture Notes

### Communication Flow
```
Web Browser → WebSocket/HTTP → FastAPI Server → HTTP API (port 8080) → Unity Player on Quest
                                              → ADB broadcasts (fallback)
Unity Player → HTTP self-registration → FastAPI Server → WebSocket → Web Browser
```

### Device Discovery
- Server scans local `/24` subnet for port 5555 (ADB)
- Checks port 8080 for player HTTP API
- Devices self-register via `POST /api/devices/register`
- Offline detection after configurable timeout (default 30s)

### Command Priority
1. HTTP API to player app (`POST http://<device>:8080/play`)
2. ADB broadcast fallback (`am broadcast -a com.vrclass.player.PLAY`)

### RenderTexture Dynamic Sizing
- Initial RenderTexture: 2048x2048
- On video prepare: resized to match actual video resolution (max 4096)
- ViewModeManager receives updated texture via `OnRenderTextureResized` event

### Recenter Behavior
- XR InputSubsystem.TryRecenter() — resets headset tracking origin
- Content rotation — rotates sphere/plane to face viewer's current gaze direction
- Both happen together to ensure "front" of video is where user is looking

## Coding Conventions

- **Python**: async/await everywhere, logging via `logging.getLogger("vrclassroom.*")`
- **C#**: namespace `VRClassroom`, `[SerializeField]` for inspector refs, Debug.Log with `[ClassName]` prefix
- **React**: functional components, Zustand for state, plain CSS classes (no CSS modules)
- **Config**: all settings via web UI at `/settings`, persisted to `config.json`

## Key Constants

| Constant | Value | Location |
|----------|-------|----------|
| Server port | 8000 | `config.py` |
| Player HTTP port | 8080 | `PlayerConfig.cs` |
| Video path on device | `/sdcard/Movies/` | `PlayerConfig.cs` |
| Package ID | `com.vrclassroom.player` | `config.py` |
| Default view mode | Sphere360 | `PlayerConfig.cs` |
| Max RenderTexture | 4096x4096 | `VideoPlayerController.cs` |

## 360 Video Format Support — Plan

### Current State
- **Supported**: Equirectangular mono 360 (standard mapping), Flat 2D
- **UV mapping**: Standard sphere UV with horizontal mirror in shader for inside-out viewing
- **Stereo**: Basic `UNITY_VERTEX_OUTPUT_STEREO` in shaders (per-eye rendering supported by Unity XR)

### Planned Format Support

#### Video Projection Types
| Format | Aspect Ratio | Description | Priority |
|--------|-------------|-------------|----------|
| Equirectangular Mono | 2:1 | Standard 360 mono — current default | Done |
| Equirectangular SBS (Side-by-Side) | 4:1 or 2:1 | Left/right eye packed horizontally | High |
| Equirectangular OU (Over-Under) | 1:1 or 2:1 | Left/right eye packed vertically | High |
| EAC (Equi-Angular Cubemap) | varies | YouTube/Google format, 6 cube faces | Medium |
| Cubemap 6x1 / 3x2 | varies | Traditional cubemap layouts | Low |
| Fisheye / Dual Fisheye | varies | Raw camera output (Insta360 etc.) | Low |

#### Implementation Plan for Stereo 3D (SBS/OU)

1. **Detection**: Add `stereoLayout` field to video config (`mono`, `sbs`, `ou`)
   - Pass via `open` command extras: `--es stereo "sbs"`
   - Server config per video in `requirementVideos`

2. **Shader Changes** (`VideoSphere.shader`):
   ```hlsl
   // Add uniform for stereo layout
   int _StereoLayout; // 0=mono, 1=sbs, 2=ou

   // In vertex shader, adjust UVs per eye:
   if (_StereoLayout == 1) { // Side-by-Side
       uv.x = uv.x * 0.5 + (unity_StereoEyeIndex * 0.5);
   } else if (_StereoLayout == 2) { // Over-Under
       uv.y = uv.y * 0.5 + ((1 - unity_StereoEyeIndex) * 0.5);
   }
   ```

3. **Sphere UV Considerations**:
   - Unity default sphere: UV wraps equirectangularly, seam at back
   - Current mirror: `uv.x = 1.0 - uv.x` corrects inside-out flip
   - For SBS: each eye sees half the texture width → UV.x scaled to [0, 0.5] or [0.5, 1.0]
   - For OU: each eye sees half the texture height → UV.y scaled similarly

4. **RenderTexture**: Already dynamic — will match video resolution (e.g. 3840x1920 for SBS, 2048x2048 for OU)

#### Spatial Audio Considerations

- **Ambisonics**: Unity supports FOA (First Order Ambisonics) and HOA via AudioSource
  - Requires video files with ambisonic audio tracks
  - Unity `AudioSource.spatialize = true` + Oculus spatializer plugin
- **Stereo**: Current standard stereo playback works without changes
- **Head-locked stereo**: Audio stays fixed regardless of head rotation (current behavior)
- **Plan**: Add ambisonic support when using 360 mode by configuring AudioSource spatializer

#### ViewMode Extension Plan
```csharp
public enum ViewMode
{
    Flat2D,
    Sphere360,
    Sphere360SBS,   // Stereoscopic side-by-side
    Sphere360OU,    // Stereoscopic over-under
    Sphere180,      // Half-sphere (VR180 format)
    Sphere180SBS,   // VR180 stereoscopic
}
```

## Testing Notes

- No automated test suite currently
- Manual testing: connect Quest headset, run `adb devices`, launch server, open web UI
- Frontend: `npm run dev` for hot-reload development
- Unity: test in Editor with mock commands (ADB/HTTP not available in Editor)

## Common Tasks

### Adding a new playback command
1. Add endpoint in `App/server/main.py`
2. Add handler in `App/server/playback_controller.py`
3. Add case in `VRClassroomPlayer/.../ADBCommandRouter.cs`
4. Add HTTP route in `VRClassroomPlayer/.../LanServer.cs`
5. Add API function in `App/frontend/src/api.js`
6. Add UI button in appropriate React component

### Adding a new view mode
1. Add to `ViewMode.cs` enum
2. Create `ViewModeConfig` ScriptableObject asset
3. Add `CreateDisplay()` call in `ViewModeManager.Awake()`
4. Add shader variant or new shader if needed
5. Add mode string mapping in `ADBCommandRouter.ParseMode()`
