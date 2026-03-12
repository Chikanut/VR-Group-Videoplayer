# Overview

## Purpose

VR Group Videoplayer is a classroom system for running the same lesson video across multiple Meta Quest headsets from one instructor device.

It is designed for schools, labs, museums, and training spaces where the operator needs a practical setup flow rather than custom development.

## What You Can Do

- discover headset players on the local network
- check which devices are online
- prepare a lesson list by video filename
- launch playback on one headset or the whole class
- pause, stop, restart, recenter, and adjust volume
- use flat 2D or 360 video content

## Main Components

### 1. Quest Player

Installed on each Meta Quest headset.

Responsibilities:

- plays videos stored on the headset
- reports device status back to the control panel
- receives playback commands over the local network

Public release file:

- `VRClassroomPlayer-Quest.apk`

### 2. Control Panel

Installed on one instructor device.

Responsibilities:

- discovers available Quest players
- shows current headset state
- stores the list of required lesson videos
- sends playback and volume commands

Public release files:

- `VRClassroomControlPanel-Windows.exe`
- `VRClassroomControlPanel-Android.apk`

## Typical Classroom Scenario

1. Install the player on each headset.
2. Copy lesson videos to each headset.
3. Install the control panel on the teacher's Windows PC or Android tablet.
4. Connect all devices to the same network.
5. Open the control panel and wait for devices to appear.
6. Choose the lesson video and start playback for the full group.

## Supported Setup

- Meta Quest headsets for playback
- Windows PC for instructor control
- Android phone or tablet for instructor control
- local Wi-Fi or LAN where devices can reach each other directly

## Important Limits

- videos must already exist on each headset
- the control panel references videos by filename only
- headset videos should be stored in `/sdcard/Movies/`
- the system is designed for local network use, not cloud streaming

## Where To Go Next

- [Downloads](downloads.md)
- [Quick Start](quick-start.md)
- [Set Up the Control Panel](setup-control-panel.md)
- [Set Up the Quest Player](setup-player.md)
