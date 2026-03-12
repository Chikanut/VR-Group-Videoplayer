# VR Quest Updater

Desktop provisioning utility for Meta Quest 3 / 3S.

## What it does

- Detects Quest devices over ADB (USB or Wi-Fi)
- Checks whether `com.vrclass.player` is installed and whether the version matches the local APK
- Uploads missing or outdated videos to `/sdcard/Movies/`
- Shows per-device and per-file progress for long transfers
- Triggers a media-library refresh after upload so videos become visible outside the VR player too

## Run

```bat
cd tools\quest_updater
python run.py
```

## Build EXE

```bat
cd tools\quest_updater
build_windows_exe.bat
```

## Notes

- The tool expects `adb` to be available in `PATH`
- APK metadata is read via `aapt` when available from the Android SDK
- Video requirements are imported from `App/config.json`, but local file paths are configured in the GUI
