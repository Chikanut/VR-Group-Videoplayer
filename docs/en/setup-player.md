# Set Up the Quest Player

The player is the app on each headset. It plays the videos, and a small agent inside it keeps the headset connected to the control panel, also while the player is closed or the headset sleeps.

## Recommended: Deploy Manager

Install the player with [Deploy Manager](deploy-manager.md). Besides installing the APK, it does the one-time setup that silent updates, autostart and the system settings need, and it connects the headset to the classroom Wi-Fi.

1. Switch on Developer mode for the headset (Meta Horizon phone app).
2. Add `VRClassroomPlayer-Quest.apk` in **Додатки (APK)** and the classroom network in **Wi-Fi**.
3. Connect the headset by USB, allow USB debugging, and press **Розгорнути** (Deploy).

## Installing the APK by Hand

`adb install VRClassroomPlayer-Quest.apk` or SideQuest also work, but then the player:

- cannot update itself silently;
- may not start by itself after a reboot;
- cannot apply the headset system settings.

Run Deploy once later to add these.

## What You See in the Headset

While no video plays, the player shows its waiting room with a heads-up display:

- top left: the headset number or name;
- the state and the control panel address;
- bottom left: whether autostart is on.

The waiting room is the logo model on a maroon sky, or your own colour and picture from **Settings → Headset environment**.

## Autostart

With autostart on, the player opens by itself after the headset wakes up or reboots, and comes back if someone closes it. This is what a classroom normally wants. To use the headset for something else:

- switch autostart off for one headset (device window), for the selected headsets or for the class (dashboard), or with Deploy Manager;
- or, in the headset, hold a pinch with both index fingers for 3 seconds while no video plays.

Autostart stays off across reboots until you switch it on again.

## Finding the Control Panel

The headset remembers the control panel address. On a new network it searches the local `/24` subnet for port 8000 by itself; the control panel also tells every headset it can see where it is. Nothing has to be typed in the headset.

## Next Step

- [Prepare Videos](prepare-videos.md)
- [Daily Use](daily-use.md)
