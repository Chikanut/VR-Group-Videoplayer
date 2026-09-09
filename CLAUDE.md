# CLAUDE.md — VR Group Videoplayer

Instructions and context for AI-assisted development with Claude Code.

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
│   │   ├── websocket_manager.py      # WebSocket client management
│   │   ├── player_probe.py           # Shared HTTP /status probe + status field mapping
│   │   ├── video_format.py           # Canonical formatId model, aliases, filename convention
│   │   ├── video_probe.py            # Header-only MP4/MOV probe + format auto-detection
│   │   └── format_compat.py          # Video vs. device decoder/storage warnings
│   ├── frontend/                     # React + Vite frontend
│   │   ├── src/
│   │   │   ├── App.jsx               # Router (/ and /settings)
│   │   │   ├── main.jsx              # React entry point
│   │   │   ├── api.js                # HTTP API client functions
│   │   │   ├── videoFormats.js       # formatId helpers, filename detection, compat warnings
│   │   │   ├── store/deviceStore.js  # Zustand state management
│   │   │   ├── hooks/useWebSocket.js # WebSocket hook with reconnection
│   │   │   ├── components/
│   │   │   │   ├── Layout.jsx        # Main page layout
│   │   │   │   ├── TopControlPanel.jsx
│   │   │   │   ├── DeviceGrid.jsx
│   │   │   │   ├── DeviceTile.jsx
│   │   │   │   ├── DeviceDialog.jsx
│   │   │   │   ├── VideoSelector.jsx
│   │   │   │   ├── VideoFormatEditor.jsx # Projection/stereo/auto-detect/probe editor
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
│       │   │   ├── VideoPlayerController.cs   # Video playback, RenderTexture management, source size
│       │   │   ├── ViewModeManager.cs         # Sphere360 / Flat2D display switching
│       │   │   ├── ViewModeConfig.cs          # ScriptableObject per view mode
│       │   │   ├── ViewMode.cs                # Legacy enum: Flat2D, Sphere360, None, Hemisphere180
│       │   │   ├── VideoProjection.cs         # Enum: Flat, Hemisphere180, Sphere360, None
│       │   │   ├── StereoLayout.cs            # Enum: Mono, SideBySide, TopBottom
│       │   │   ├── VideoFormat.cs             # projection + stereo + swapEyes + forwardYaw
│       │   │   ├── VideoFormatParser.cs       # formatId/mode parsing, /open compat rules
│       │   │   ├── VideoFormatDetector.cs     # Filename suffix detection (_180_LR, _360_TB)
│       │   │   ├── VideoOpenRequest.cs        # /open DTO + shared VideoOpenExecutor
│       │   │   ├── HemisphereMeshBuilder.cs   # Procedural VR180 hemisphere mesh
│       │   │   ├── DecoderCapabilities.cs     # MediaCodecList query, reported in /status
│       │   │   ├── PlayerRenderSettings.cs    # Runtime RenderTexture clamp (PUT /render-settings)
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
│           ├── VideoSphere.shader             # Inside-sphere/hemisphere, stereo split, crop, mirror U
│           └── VideoFlat.shader               # Quad rendering, stereo split
├── PlayerAPI.md                       # Player HTTP+ADB API reference (Ukrainian)
├── start.sh / start.bat               # Quick start launchers
└── CLAUDE.md                          # This file
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
- Liveness (`device_manager.py`): a device is alive while its player WebSocket is open OR it answers a direct HTTP `/status` probe. Quiet devices are probed every 5s; a device goes offline only after `deviceOfflineTimeout` (default 30s) with the WS closed and probes failing. Offline devices are re-probed every ~15s so they return without a full scan.

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
| Package ID | `com.vrclass.player` | `ProjectSettings.asset` (`applicationIdentifier`) |
| Default view mode | Sphere360 | `PlayerConfig.cs` |
| Max RenderTexture | 4096x4096 | `PlayerConfig.MaxRenderTextureDimension` (runtime override: `PUT /render-settings`) |

## 360 / 180 Video Formats and Stereo 3D

### Format model (shared by server, panel and player)
A format is two orthogonal axes, joined into one canonical `formatId`:

| `formatId` | projection | stereo | Notes |
|---|---|---|---|
| `2d` | `flat` | `mono` | flat quad |
| `360` | `360` | `mono` | default, legacy content |
| `360_sbs` / `360_tb` | `360` | `sbs` / `tb` | 360 3D, left eye = left / top half |
| `180` | `180` | `mono` | VR180 mono (procedural hemisphere) |
| `180_sbs` / `180_tb` | `180` | `sbs` / `tb` | VR180 3D (customer content is `_180_LR`) |
| `auto` | — | — | config only: detect from filename suffix, then per-eye aspect + metadata |

- Server: `App/server/video_format.py` (ids, aliases, filename convention, `legacy_mode_for`), `video_probe.py` (header-only MP4/MOV parser + detection algorithm), `format_compat.py` (video vs. device decoder warnings).
- Player: `VideoProjection` + `StereoLayout` enums, `VideoFormat`, `VideoFormatParser` (compat rules), `VideoFormatDetector` (filename), `VideoOpenRequest`/`VideoOpenExecutor` (shared open logic for HTTP + WS). `ViewMode` is kept as a legacy alias (1:1 with `VideoProjection`, `Hemisphere180` appended).
- Panel: `App/frontend/src/videoFormats.js` mirrors the server helpers; `VideoFormatEditor.jsx` is the projection/stereo/probe UI.
- Filename convention (also understood by the Quest media player): `<name>_<180|360|2d>_<LR|TB|MONO>.<ext>`, suffix at the end of the stem.

### Backward compatibility rules (do not break these)
- `/open` always carries legacy `mode` (`"360"`/`"2d"`; 180 maps to `"360"`) **plus** `format`, `projection`, `stereo`, `swapEyes`, `forwardYaw`. Old players read `mode` and ignore the rest (JsonUtility).
- Player precedence: `projection`/`stereo` > `format` > `mode` (+ filename refinement when only `mode` is present, i.e. old server) > current format > 360 mono.
- `/status` keeps legacy `mode` and adds `format`, `projection`, `stereo`, `swapEyes`, `videoWidth/Height`, `backend`, `decoderCaps`. `player_probe.status_to_kwargs` derives projection/stereo from `mode` for old players and sets `stereo_capable=False` so the panel can warn.
- Config: `videoType` accepts canonical ids, `auto` and aliases; old `"360"`/`"2d"` configs load unchanged. Extra fields `swapEyes`, `forwardYaw`, `detectedType`, `detectionSource`, `probe` default when absent.

### Rendering (current: Unity VideoPlayer backend, spec Phase 2)
- Stereo split happens in the fragment shader as the **last** UV step, in texture space (`_StereoLayout`, `_SwapEyes` in `VideoSphere.shader` / `VideoFlat.shader`). SBS: left eye = u in [0, 0.5]; TB: left eye = v in [0.5, 1].
- `VideoSphere.shader` also carries tiling/offset/crop, `_MirrorU` (1 for Unity's sphere primitive, 0 for the procedural hemisphere) and `_Cull`. Both shaders are in Always Included Shaders (GraphicsSettings) so `Shader.Find` works on device.
- `HemisphereMeshBuilder` builds the 180° mesh (64x64 segments, direct UVs); a black backdrop sphere sits behind the viewer. 180° content forces a recenter on open.
- The production 360 config (`Assets/Configs/360_Mode.asset`) uses a Shader Graph material without `_StereoLayout`; for stereo content `ViewModeManager` swaps in a fallback material (`ViewModeConfig.stereoMaterialOverride` or a runtime `VideoSphere` material with `fallbackMirrorU`). **Eye order and mirroring of that fallback must be verified on a headset with an L/R test clip** (spec risk R5).
- RenderTexture clamp stays 4096 (`PlayerConfig.MaxRenderTextureDimension`), overridable at runtime via `PUT /render-settings` for field tests. `DecoderCapabilities` queries `MediaCodecList` once and reports it in `/status`.

### Not implemented yet (see `docs/specs/stereo-3d-180-360.md`)
- Phase 0 device verification (8192x4096 Main10@60 decode, `OVROverlay` prototype) — needs hardware.
- Phase 3 native backend (`IVideoBackend`, Android MediaPlayer → `OVROverlay` external surface) for full-resolution 8K60 VR180.
- EAC / cubemap / fisheye projections, ambisonic audio, HDR.

## Testing Notes

- No automated test suite currently
- Server unit tests: `App/venv/Scripts/python.exe -m unittest App.server.tests.<module>` from the repo root (no pytest installed; tests import `App.server.*`). `test_video_probe.py` also runs against the real customer samples in `Video Samples/` when present (git-ignored) and skips otherwise.
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
