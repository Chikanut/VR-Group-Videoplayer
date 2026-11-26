# Networking and Troubleshooting

## Network Rules

- the control panel and all headsets must be on the same network and subnet;
- the network must let devices reach each other: no guest Wi-Fi and no client isolation;
- the panel uses port 8000; the headsets use 8080 (player) and 8081 (agent);
- internet is not needed. A router without internet works; Deploy Manager sets `captive_portal_mode=0` so Quest does not treat it as a login page.

## Headsets Do Not Appear

1. Check that the headset is on the classroom Wi-Fi.
2. Windows: allow `VRClassroomControl` in Windows Defender Firewall for private networks, and make sure the network is marked *Private*.
3. Make sure no other program uses port 8000.
4. Check that the headset went through Deploy Manager once.
5. When the PC is on several networks (Ethernet, VPN, hotspot), set **Settings → System → Network Subnet** to the classroom one.

The headsets search for the panel themselves; after the PC changes its address they find it again within about a minute.

## A Headset Is Offline

- it may be asleep for a long time: press **Wake All**;
- it may be off or outside Wi-Fi range;
- the panel keeps checking offline headsets every 15 seconds, so they come back by themselves.

## The Tile Says "Player will not open", or the Headset Shows Only the Camera View

Quest sometimes keeps a system window in front of the player that waits for internet: the first-time setup, the tips window or the Store. The player cannot close it.

1. Connect the headset by USB and press **Відновити** (Recover) in Deploy Manager.
2. If the Quest menu does not come back within a minute, press **Перезавантажити** (Reboot).

After a reboot with the headset lying on the table, Quest waits until it is worn once before opening apps. The control panel wakes it by itself while it is connected.

## The Player Does Not Start a Video

- the tile must be online and show **Requirements met** for that video;
- the file name in Settings must match the file on the headset exactly;
- check the type: `360` or `2D`.

## The Meta Store Opens Over the Player

The player (1.9.2+) notices this within 3 seconds and comes back to the front. It needs the one-time Deploy Manager setup.

## A Player Update Fails

- the APK must be signed with the same key as the installed player. The releases are;
- the headset must have gone through Deploy Manager (silent install);
- `failed: ...` on the tile says why. Installing over USB with **Перевстановити APK** (Reinstall APK) always works.

## The Control Panel Does Not Open

- open `http://localhost:8000` by hand;
- restart the exe;
- check that port 8000 is free.

## Advanced Reference

Commands and endpoints: [Player API reference](../../PlayerAPI.md).
