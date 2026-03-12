# Networking and Troubleshooting

## Goal

Fix the most common reasons why devices do not appear or videos do not start.

## Basic Network Rules

- the control panel and all headsets must be on the same local network
- the network must allow devices to reach each other directly
- guest Wi-Fi or client isolation can block discovery

## If Headsets Are Not Discovered

Check these items in order:

1. Confirm the player app is open on the headset.
2. Confirm the headset and control panel are on the same Wi-Fi or LAN.
3. Confirm the control panel subnet setting matches your network.
4. Make sure the router is not isolating wireless clients.
5. On Windows, check firewall rules if discovery is still failing.

## If A Headset Appears Offline

- confirm the headset still has network access
- keep the player app open in the foreground
- verify the device has not gone to sleep
- wait for the next scan cycle and refresh the dashboard

## If Playback Does Not Start

Check:

1. the headset is online
2. the lesson filename exists on that headset
3. the video was copied to `/sdcard/Movies/`
4. the selected mode matches the content type

## If A Video Looks Missing

- compare the configured filename with the real file name exactly
- avoid using folder paths in the control panel
- make sure the same file exists on every headset

## If Windows Cannot Open the Control Panel

- try opening `http://localhost:8000` manually
- restart the EXE
- confirm no other app is already using port `8000`

## Advanced Reference

For lower-level command and endpoint details, see the [Player API reference](../../PlayerAPI.md).
