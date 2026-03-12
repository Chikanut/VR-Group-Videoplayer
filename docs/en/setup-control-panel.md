# Set Up the Control Panel

## Goal

Install and open the instructor control panel on either Windows or Android.

## Choose Your Platform

- use Windows if you want a larger screen and a standard desktop workflow
- use Android if you want a portable phone or tablet setup

## Option A: Windows

### Prerequisites

- Windows PC or laptop
- `VRClassroomControlPanel-Windows.exe` from [GitHub Releases](https://github.com/Chikanut/VR-Group-Videoplayer/releases/latest)
- local network access to the same Wi-Fi or LAN as the headsets

### Steps

1. Download `VRClassroomControlPanel-Windows.exe`.
2. Run the file on the instructor PC.
3. If Windows shows a security prompt, allow the app to run if it matches your release source.
4. Wait for the control panel window or browser page to open.
5. Confirm the app is reachable at `http://localhost:8000` on that computer.

### Expected Result

You should see the control panel dashboard and later be able to discover Quest players on the network.

## Option B: Android

### Prerequisites

- Android phone or tablet
- `VRClassroomControlPanel-Android.apk` from [GitHub Releases](https://github.com/Chikanut/VR-Group-Videoplayer/releases/latest)
- permission to install APK files on the device

### Steps

1. Download `VRClassroomControlPanel-Android.apk`.
2. Install the APK on the Android device.
3. Allow installation from your chosen file source if Android asks.
4. Open the app.
5. Wait for the embedded control panel interface to load.

### Expected Result

You should see the same control dashboard used on Windows, but inside the Android app.

## First Configuration Tasks

After the control panel opens:

1. Open Settings.
2. Add your lesson videos by filename.
3. Check battery threshold, scan interval, and network subnet if needed.
4. Return to the dashboard and wait for devices to appear.

## Next Step

- [Set Up the Quest Player](setup-player.md)
- [Prepare Videos](prepare-videos.md)
