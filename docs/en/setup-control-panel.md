# Set Up the Control Panel

The control panel is the instructor's dashboard. It runs on a Windows PC or on an Android phone or tablet, and it can be opened from any browser on the same network.

## Windows

1. Download `VRClassroomControlPanel-Windows.exe` and put it in its own folder: it keeps `config.json` and `device_names.json` next to itself.
2. Run it. A console window shows the server, and the dashboard opens in the browser at `http://localhost:8000`.
3. When Windows Defender Firewall asks, allow access on **private** networks. Without it the headsets cannot reach the panel.
4. If SmartScreen warns about an unknown publisher, choose *More info → Run anyway*.

Keep the console window open during the lesson; closing it stops the panel.

## Android

1. Install `VRClassroomControlPanel-Android.apk` (allow installing from your file manager or browser).
2. Open the app. The server runs inside it and the dashboard loads on its own.
3. Keep the app open, or allow it to run in the background, during the lesson.

## Open the Panel from Another Device

Press **Connection** in the bottom-right corner of the dashboard. It shows a QR code and the address, for example `http://192.168.1.10:8000`. Scan it with a phone or tablet on the same network to control the class from there.

## First Settings

Open **Settings**:

![Settings → System](../assets/screenshots/settings-system.png)

1. **Lesson videos:** add each video by file name and choose its type.
2. **System → Video library folder:** the folder on this PC with the videos, for **Sync content**.
3. **System → Network Subnet:** leave empty; set it only when the PC has several networks and the panel picks the wrong one.
4. **Headset environment:** optional, your own waiting-room colour and picture.
5. Press **Save changes**.

All settings: [Settings & Video Tuning](settings-and-video-tuning.md).

## Back Up the Setup

**Settings → Import / export** downloads `config.json` and the headset names, and loads them on another PC.

## Next Step

- [Set Up the Quest Player](setup-player.md)
- [Prepare Videos](prepare-videos.md)
