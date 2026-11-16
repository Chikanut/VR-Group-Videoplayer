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
│   │   └── player_probe.py           # Shared HTTP /status probe + status field mapping
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
- A closed player WebSocket is reported to the dashboard only after `WS_DISCONNECT_GRACE_SEC` (8s) without a reconnect, so short Wi-Fi blips do not flip the WS/HTTP badge.
- A `/status` answer without a device ID never creates a new device keyed by IP; it only refreshes the device already known at that IP.

### Device Naming (number / name shown on the dashboard)
- The **headset owns its name**: the player stores it in PlayerPrefs (`device_name`) and reports it in every `register`/`status` payload as `deviceName` (always present, possibly empty). The HUD shows it top-left while idle.
- The server mirrors it: priority is *instructor-assigned but unconfirmed* (`pending`) > *reported by device* > `device_names.json` fallback > device ID. `DeviceState.name_source` tells the UI which one is in effect.
- Renaming (`PUT /api/devices/{id}/name`) pushes the name to the headset via WS command `set_name` (fallback HTTP `PUT /name`), stores it in `device_names.json` as a fallback, and keeps it `pending` until the device reports it back. If the device is offline the push is retried on its next report or WS registration.
- `device_names.json` import never overrides what a headset reports; it only fills in for players that report no name.

### Player status thread model (Unity)
- `StatusReporter` builds the status JSON on the main thread (every 0.5s or on state change). The HTTP listener thread and WS thread-pool continuations only read the cached string, so they never touch Unity APIs/JNI/PlayerPrefs.
- `VideoPlayerController` creates a fresh `VideoPlayer` (child GameObject `VideoPlayerInstance`) for every opened video and destroys the previous one; the new one is prepared only ~0.5s after the old one is released. The decoder is also released after completion/error/stop. Reusing one `VideoPlayer` and swapping `url` (or Stop+Prepare in the same frame) leaked hardware decoder resources: after 5-7 long videos the next open hung or the app crashed.
- Sleep: on `OnApplicationPause(true)` the player checks 1.5s later whether the headset is really asleep (`PowerManager.isInteractive()` false) and autostart is on; if so it kills its own process (`PlayerSystem.java closeIfAsleep`) and the watchdog opens a fresh player 2s after screen-on. Measured on a Quest 3S: waking a paused idle player grows its GPU memory 695 → 1941 MB within 3s (two ~617 MB steps, with or without MSAA, with or without video; cause unknown), which on top of an 8K video ran the headset out of memory (27s system freeze, kernel OOM) before a restart could act. Fallback when the process survives the sleep (autostart off, or a pause that was not a sleep): after the resume the player restarts itself ~0.5s after wake via `Assets/Plugins/Android/RestartActivity.java` (separate `:restart` process kills the player pid and relaunches the app) and comes back fresh in the waiting room — no attempt to resume the video. Reason (Quest 3S logcats): Unity's video pipeline leaks GPU memory across sleep/wake (8K player 1.8 GB → 3.1-4.6 GB, never freed, ~650 MB left for the system), after which videos froze the headset or would not start. Nothing touches the VideoPlayer while paused. `ServerConnection` closes the WS on pause, idles the connection loop while asleep, and holds off subnet discovery for 30s after wake.
- Missed stops (`App/server/pending_stops.py`): every stop marks its targets (a global stop marks *all* known devices, including offline/asleep ones). While marked, a WS/HTTP status showing `loading/ready/playing/paused` makes the server re-send `stop` (throttled 5s); a non-active state or a successful `open` clears the mark.
- Keep-awake: while the server WS is connected the player sends broadcast `com.oculus.vrpowermanager.prox_close` (headset thinks it is worn, never sleeps); 60s after losing the server it sends `automation_disable`. Any app may send these; they reset on reboot.
- Sleep / wake (dashboard "Sleep All" / "Wake All"): WS command `sleep` stops the video and sends `prox_far` (display off, asleep ~15s later); keep-awake is not re-asserted. During a long sleep Quest freezes and kills the player process (port 8080 dead), but the watchdog FGS process stays reachable: `POST http://<ip>:8081/wake` (WatchdogService) sends `prox_close`, then the watchdog's cached launch opens the player. The server sends wake to every known device IP (asleep devices are offline). On any other screen-on (power button) the watchdog sends `automation_disable`, so the virtual FAR does not put the headset straight back to sleep. `vrpowermanager.wake` does NOT wake the headset.
- Watchdog (`Assets/Plugins/Android/WatchdogService.java`, foreground service in process `:watchdog`): started on `BOOT_COMPLETED` / `MY_PACKAGE_REPLACED` (`BootReceiver`) and from `ServerConnection.Start()`. Every 10s (and 2s after screen-on), if the headset is awake (`PowerManager.isInteractive()`) and the player's main process is not at least VISIBLE, it launches the player. It must not launch while asleep: that resumed and paused Unity every 10s for the whole sleep. Background launch works only with appop `SYSTEM_ALERT_WINDOW allow`. Quest drops launches while the lock screen / a system dialog is up and may close the player on unlock leaving an empty process — hence "visible", not "process alive". Escape: Settings > Apps > Force stop (until next boot).
- Autostart switch: Settings → "Disable/Enable autostart" → server `POST http://<ip>:8081/autostart/off|on` to every known device IP. The watchdog keeps a marker file `files/autostart_off` (survives reboot and updates) and stops relaunching the player while it exists; the watchdog itself (wake listener) keeps running, so it can be switched back on with the player closed.
- Headset settings profile (`App/server/headset_settings.py`): config `headsetSettings` holds lines `global/<key>=<value>` / `secure/<key>=<value>` (default `global/captive_portal_mode=0`: a router without internet that redirects the connectivity check is otherwise treated as a captive portal). The server sends WS `apply_settings {settings}` on every WS registration and when the profile changes; `PlayerSystem.java applySettings` writes them, remembers each key's original value in SharedPreferences `settings_originals` and restores it when the line disappears (empty profile = restore all). Result is reported as status field `settingsProfile` (`ok` / `no permission` / `error`). Needs `WRITE_SECURE_SETTINGS`, granted once over USB by `tools/quest_deploy.py` `setup_player()`. Appops and grants are shell-only — they cannot go through the profile. Meta's updater cannot be frozen: `pm disable-user com.oculus.updater` fails with "Cannot disable a protected package" (Horizon OS v209).
- Self-update: Settings → "Player APK path" + "Update players" → server sends WS `update {url:/api/player/apk, sha256}`. C# compares the installed APK's sha256, downloads with Mono `HttpWebRequest` (Unity's generated network_sec_config blocks plain HTTP for Java), then `PlayerSystem.java` installs via `PackageInstaller` with `USER_ACTION_NOT_REQUIRED`. Silent only if the app is its own installer of record (`adb install -i com.vrclass.player`; `pm set-installer` is forbidden) — `tools/quest_deploy.py` `setup_player()` does this plus the appops once over USB. All builds must be signed with the same key, or the update fails (and ANDROID_ID, i.e. the device ID, changes with the key).
- Wireless ADB cannot survive a reboot on Quest (tested on Horizon OS v201): `setprop` is denied and the trusted Wi-Fi debugging network is forgotten on every boot.
- CLI build: `Unity.exe -batchmode -quit -projectPath VRClassroomPlayer -executeMethod BuildPlayerCli.BuildQuest [-buildOutput x.apk]`.
- `ProcessDiagnostics.Snapshot()` (RSS, open fds, managed heap) is logged on every open, on errors/timeouts and once a minute — check `adb logcat -s Unity` for growth when chasing long-session crashes.

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
