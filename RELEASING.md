# Release & Update Guide — VR Group Videoplayer

How to build, version, publish to GitHub, and update existing installations **without losing user config**.

This guide is written for the current release (the **Video Seek** feature) but the process is the same for every release.

---

## 1. What ships in a release

The project produces **two independent artifacts**. A release usually updates one or both.

| Artifact | Source | Build script / tool | Output | Where users run it |
|---|---|---|---|---|
| **Control Panel** (server + web UI) | `App/` + `App/frontend/` | `App/build_windows_exe.bat` | `App/dist/VRClassroomControl.exe` | Instructor's Windows PC |
| **VR Player** (Quest app) | `VRClassroomPlayer/` (Unity) | Unity Editor → Build | `VRPlayer.apk` | Meta Quest headsets |

Key facts that drive the update procedure:

- The Control Panel stores its settings in **`config.json`** and **`device_names.json`**, written **next to the `.exe`** (`App/server/config.py` → `_desktop_base_dir()`). These files are **not** bundled into the `.exe`.
- On load, config is passed through `_normalize_config()`, which **migrates legacy keys forward** (e.g. `apkDownloadUrl`→`mobileAppUrl`, `localPath`/`devicePath`→`filename`, `sphere`→`360`). Old config files therefore keep working across versions.
- Player videos live in **`/sdcard/Movies/`** on the headset — external storage that survives app reinstall/uninstall.

---

## 2. Versioning

Current published tag: **`v1.5.5`**. This release adds the seek feature → bump to **`v1.6.0`** (new backward-compatible feature = minor bump, SemVer).

Bump the version in these places so everything stays in sync:

| File | Field | From → To |
|---|---|---|
| `VRClassroomPlayer/ProjectSettings/ProjectSettings.asset` | `bundleVersion` | `1.5.5` → `1.6.0` |
| `VRClassroomPlayer/ProjectSettings/ProjectSettings.asset` | `AndroidBundleVersionCode` | `3` → `4` |
| `App/frontend/package.json` | `"version"` | → `1.6.0` (optional, keeps UI/npm aligned) |
| Git tag | — | `v1.6.0` |

> `AndroidBundleVersionCode` **must** increase for every Quest build, otherwise `adb install -r` can refuse to upgrade. In Unity: **Edit → Project Settings → Player → Android → Other Settings → Version / Bundle Version Code**.

---

## 3. Pre-release checklist

Run from the repo root: `D:\UnityProjects\VRGroupViewer\VR Group Videoplayer`

```powershell
# Backend tests (uses the project venv Python)
.\App\venv\Scripts\python.exe -m unittest discover -s App\server\tests -p "test_*.py"

# Frontend production build sanity check
cd App\frontend; npm run build; cd ..\..
```

- [ ] All backend tests pass.
- [ ] `npm run build` succeeds with no errors.
- [ ] Unity project compiles with no console errors (open the project once; check the Console).
- [ ] Manual smoke test of the new feature (see `PlayerAPI.md` — `POST /seek`).
- [ ] Version numbers bumped (section 2).
- [ ] `CHANGELOG` / release notes drafted (section 6).

---

## 4. Build the Control Panel (`VRClassroomControl.exe`)

```powershell
cd "D:\UnityProjects\VRGroupViewer\VR Group Videoplayer\App"
.\build_windows_exe.bat
```

What it does (see `App/build_windows_exe.bat`):
1. Creates/activates `venv`, installs `requirements.txt` + `requirements-build.txt`.
2. Builds the frontend (`npm install` + `npm run build` → `frontend/dist`).
3. Runs PyInstaller (`--onefile`, bundling `frontend/dist`, icon `assets/icons/app.ico`).

Output: **`App/dist/VRClassroomControl.exe`** — a single self-contained file to hand to instructors.

> When prompted "Run full frontend rebuild?", answer **y** for a release build to guarantee a clean `node_modules`/`dist`.

---

## 5. Build the VR Player APK (Unity)

There is no headless build script — build from the Unity Editor:

1. Open `VRClassroomPlayer/` in Unity (the version the project was authored in — 2021+/6000+).
2. Confirm no compile errors in the Console.
3. Bump `bundleVersion` and `AndroidBundleVersionCode` (section 2).
4. **File → Build Settings → Android** → ensure `MainPlayer` scene is in the list → **Build**.
5. Save as **`VRPlayer.apk`** (package `com.vrclassroom.player`).

Keep the APK somewhere stable, e.g. `tools\builds\VRPlayer-1.6.0.apk`.

---

## 6. Release name & description

**Tag:** `v1.6.0`
**Release title:** `v1.6.0 — Video Seek`

**Description (paste into the GitHub release body):**

```markdown
## v1.6.0 — Video Seek

Adds the ability to scrub video playback to any position, both globally (all
headsets at once) and per‑device.

### ✨ New
- **Seek command** end‑to‑end across the stack:
  - VR Player: new `Seek(float seconds)` — clamps to `0..duration`, preserves
    the current play/pause state, and safely no‑ops with a warning when the
    video source reports `canSetTime == false`.
  - Player HTTP API: `POST /seek` with `{ "time": <seconds> }`.
  - Player WebSocket: new `seek` command (`time` field).
  - Control Panel API: `POST /api/playback/seek` + `playbackSeek(time, deviceIds)`.
- **UI**
  - Global seek slider in the top control panel (targets all connected players).
  - Per‑device seek slider in the device dialog.
  - Sliders follow live playback and hold position while dragging.

### 🧪 Tests
- Backend unit tests for `seek_video` (payload shape, per‑device targeting,
  negative‑time clamping, no‑devices path).

### 📖 Docs
- `PlayerAPI.md` documents `POST /seek`.

### ⬇️ Assets
- `VRClassroomControl.exe` — Windows Control Panel.
- `VRPlayer.apk` — Meta Quest player (packageVersionCode 4).

### 🔄 Updating
Your existing `config.json` and `device_names.json` are **fully compatible** —
see the "Updating an existing installation" section in `RELEASING.md`. In short:
replace the `.exe` / reinstall the APK; **do not delete your config files**.

**Full changelog:** https://github.com/Chikanut/VR-Group-Videoplayer/compare/v1.5.5...v1.6.0
```

---

## 7. Commit, tag, and push to GitHub

Remote: `https://github.com/Chikanut/VR-Group-Videoplayer.git` (branch `main`).

```powershell
cd "D:\UnityProjects\VRGroupViewer\VR Group Videoplayer"

git add -A
git commit -m "Release v1.6.0 — Video Seek"

# Annotated tag
git tag -a v1.6.0 -m "v1.6.0 — Video Seek"

git push origin main
git push origin v1.6.0
```

### Publish the GitHub Release

`gh` is **not installed** on this machine, so use the web UI (or install GitHub CLI):

**Web UI**
1. Go to `https://github.com/Chikanut/VR-Group-Videoplayer/releases/new`.
2. **Choose a tag** → `v1.6.0` (already pushed).
3. **Release title** → `v1.6.0 — Video Seek`.
4. Paste the description from section 6.
5. **Attach binaries**: drag in `VRClassroomControl.exe` and `VRPlayer.apk`.
6. **Publish release**.

**With GitHub CLI** (if you install it later — `winget install GitHub.cli`, then `gh auth login`):
```powershell
gh release create v1.6.0 `
  "App\dist\VRClassroomControl.exe" `
  "tools\builds\VRPlayer-1.6.0.apk" `
  --title "v1.6.0 — Video Seek" `
  --notes-file release-notes-1.6.0.md
```

---

## 8. Deploy the APK to headsets

Use **`tools/QuestDeployManager.exe`** (or `python tools/quest_deploy.py`).

> ⚠️ **Important for updates:** the deploy manager **skips** an APK if the package is
> already installed (`quest_deploy.py` → `is_package_installed`). To push a *new*
> version to headsets that already have the player, do **one** of:
>
> - **In‑place upgrade (keeps app data):** run manually
>   ```powershell
>   adb install -r -g "tools\builds\VRPlayer-1.6.0.apk"
>   ```
>   (`-r` = reinstall/keep data, `-g` = grant runtime permissions). This is what the
>   tool uses internally, but bypasses its "already installed → skip" guard.
> - **Clean reinstall:** uninstall first, then deploy —
>   ```powershell
>   adb uninstall com.vrclassroom.player
>   ```
>   Videos in `/sdcard/Movies/` are **not** removed by uninstall.

For fleets, loop over connected serials (`adb devices`) or let QuestDeployManager fan out after uninstalling the old build.

---

## 9. Updating an existing installation **without losing user config**

This is the part that matters most for users upgrading from a previous version.

### Control Panel (Windows PC)

The `.exe` is stateless; **all** user data lives in the two JSON files beside it:

```
<install folder>\
├── VRClassroomControl.exe   ← replace this on update
├── config.json              ← KEEP (videos list, ports, thresholds, network)
└── device_names.json        ← KEEP (headset friendly names)
```

**Safe update procedure:**
1. Close the running Control Panel.
2. **Back up** `config.json` and `device_names.json` (copy them elsewhere — one‑time safety net).
3. **Replace only** `VRClassroomControl.exe` with the new build.
4. **Do not** delete or overwrite `config.json` / `device_names.json`.
5. Start the new `.exe`. On launch it loads the existing config, auto‑migrates any
   legacy fields, and re‑saves in the current schema. Your videos, device names,
   ports, and network settings are preserved.

**If a user has no local files / fresh machine:** they can restore via the
**Settings page → Import `config.json` / Import `device_names.json`** (and use
**Export** beforehand to create the backup). Import fully replaces current data.

> Why this is safe: `config.py` resolves the config path from the `.exe`'s own
> folder and never ships a bundled config, so a new binary can't clobber existing
> settings. `_normalize_config()` tolerates old/missing keys and fills defaults,
> so older `config.json` files load without manual editing.

### VR Player (Quest)

- Use **`adb install -r`** to upgrade in place — this **keeps** app data (PlayerPrefs
  such as the verbose‑logging toggle) and, of course, all videos in `/sdcard/Movies/`.
- A full uninstall/reinstall also preserves videos (they're on external storage) but
  resets the app's own PlayerPrefs — acceptable, since the player pulls its behavior
  from the Control Panel at runtime.
- No player‑side config file needs to be preserved manually.

---

## 10. Rollback

- **Control Panel:** keep the previous `VRClassroomControl.exe`. To roll back, swap the
  binary back — config files are unchanged and remain compatible (the schema only grew).
- **Quest:** `adb install -r` the previous APK **only if** its `versionCode` is ≥ the
  installed one; otherwise `adb uninstall com.vrclassroom.player` then install the old APK.
- **Repo:** `git checkout v1.5.5` (or revert the release commit). Tags are immutable
  references to each shipped build.

---

## Quick reference

```powershell
# Build Control Panel
cd "D:\UnityProjects\VRGroupViewer\VR Group Videoplayer\App"; .\build_windows_exe.bat

# Tests
.\App\venv\Scripts\python.exe -m unittest discover -s App\server\tests -p "test_*.py"

# Tag & push
git tag -a v1.6.0 -m "v1.6.0 — Video Seek"; git push origin main; git push origin v1.6.0

# Upgrade a headset in place (keeps data + videos)
adb install -r -g "tools\builds\VRPlayer-1.6.0.apk"
```
```
