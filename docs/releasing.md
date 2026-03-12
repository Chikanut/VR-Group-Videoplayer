# Release Checklist

Use this checklist whenever you publish a new public GitHub Release.

## Asset Naming Standard

Upload release files with these exact names:

- `VRClassroomPlayer-Quest.apk`
- `VRClassroomControlPanel-Android.apk`
- `VRClassroomControlPanel-Windows.exe`

## 1. Build the Windows Control Panel

From the repository root:

```bat
App\build_windows_exe.bat
```

Expected output:

- `App/dist/VRClassroomControl.exe`

Rename before upload:

- `VRClassroomControl.exe` -> `VRClassroomControlPanel-Windows.exe`

## 2. Build the Android Control Panel

1. Open `App/android/chaquopy` in Android Studio.
2. Confirm the React frontend has already been built in `App/frontend/dist`.
3. Build a release APK from the `app` module.

Expected public upload name:

- `VRClassroomControlPanel-Android.apk`

## 3. Build the Quest Player

1. Open `VRClassroomPlayer/` in Unity.
2. Build the Android APK for Meta Quest.
3. Confirm the generated APK launches on a headset.

Current repository artifact reference:

- `VRClassroomPlayer/Builds/VRClassroomVideoPlayer.apk`

Rename before upload:

- `VRClassroomVideoPlayer.apk` -> `VRClassroomPlayer-Quest.apk`

## 4. Verify Before Publishing

Check all three artifacts:

- Windows EXE starts the control panel
- Android APK opens the embedded control panel
- Quest APK launches on a headset

Check product behavior:

- control panel opens
- at least one headset is discovered
- one configured video can be opened by filename
- playback can start successfully

## 5. Create the GitHub Release

1. Create a new GitHub Release from the repository Releases page.
2. Use a clear version tag such as `v1.0.0`.
3. Use the template in [release-notes-template.md](release-notes-template.md).
4. Upload all three assets.
5. Mark in the release body which asset is for Quest, Android, and Windows.

## 6. Final Public Check

After publishing:

1. Open the repository as a public visitor.
2. Open `README.md`.
3. Click the Releases link.
4. Confirm all three files are present with the public names.
5. Confirm the English and Ukrainian documentation links still work.
