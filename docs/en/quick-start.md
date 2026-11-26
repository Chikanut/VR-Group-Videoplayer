# Quick Start

By the end of this guide one control panel runs a lesson video on every headset in the class.

## What You Need

- one Meta Quest headset per student (Quest 3 / 3S tested)
- a Windows PC for the first setup over USB, with a USB-C cable
- one instructor device for the lessons: the same Windows PC, or an Android phone or tablet
- a Wi-Fi network that the PC and all headsets join; internet is not needed
- the files from [GitHub Releases](https://github.com/Chikanut/VR-Group-Videoplayer/releases/latest):
  `VRClassroomPlayer-Quest.apk`, `QuestDeployManager.exe` and one control panel
  (`VRClassroomControlPanel-Windows.exe` or `VRClassroomControlPanel-Android.apk`)

## 1. Prepare each headset once (about 2 minutes per headset)

1. Turn on **Developer mode** for the headset in the Meta Horizon phone app.
2. Run `QuestDeployManager.exe` on the PC. It opens its own window.
3. In **Додатки (APK)** (Apps) add `VRClassroomPlayer-Quest.apk`.
4. In **Wi-Fi** add the classroom network.
5. Connect a headset by USB, put it on once and allow USB debugging (tick *Always allow*).
6. In **Окуляри** (Headsets) press **Розгорнути** (Deploy).

Deploy installs the player, sets it up to start by itself and to update silently, and connects the headset to Wi-Fi. Repeat for every headset; you can connect several at once through a USB hub.

Details: [Deploy Manager](deploy-manager.md).

## 2. Start the control panel

- **Windows:** run `VRClassroomControlPanel-Windows.exe`. The dashboard opens in the browser at `http://localhost:8000`. Allow it in the Windows firewall for *private* networks when Windows asks.
- **Android:** install and open `VRClassroomControlPanel-Android.apk`.

The headsets find the control panel on their own within a few seconds and appear as tiles.

Details: [Set Up the Control Panel](setup-control-panel.md).

## 3. Add the lesson videos

1. Open **Settings → Lesson videos** and press **+ Add Video** for every video. Enter the file name only, for example `lesson01.mp4`, and choose `360` or `2D`.
2. Put the video files in one folder on the PC and enter it as **Settings → System → Video library folder**.
3. Press **Save changes**, go back to the dashboard and press **Sync content**. The headsets download the videos over Wi-Fi.

You can also copy the videos over USB with Deploy Manager. Details: [Prepare Videos](prepare-videos.md).

## 4. Run the lesson

When the tiles say **Requirements met**, choose the video and press **Play All**.

![Dashboard with a class of 14 headsets](../assets/screenshots/dashboard.png)

Details: [Daily Use](daily-use.md).

## If Something Fails

- headsets do not appear: [Networking and Troubleshooting](networking-troubleshooting.md)
- the tile says **Player will not open**: [Deploy Manager → Recover](deploy-manager.md#recover-a-stuck-headset)
- a video is missing: [Prepare Videos](prepare-videos.md)
