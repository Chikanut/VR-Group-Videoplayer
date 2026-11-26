# Overview

VR Group Videoplayer runs the same lesson video on a whole class of Meta Quest headsets from one instructor device. It is made for schools, labs, museums and training rooms, works on a local network without internet, and needs no programming.

## Parts

| Part | Where it runs | What it does |
|---|---|---|
| **Player** (`VRClassroomPlayer-Quest.apk`) | every headset | plays the videos; its agent keeps the headset connected even while the player is closed or asleep |
| **Control panel** (`VRClassroomControlPanel-Windows.exe` / `-Android.apk`) | the instructor's PC or tablet | dashboard: shows every headset, sends commands, sends videos and updates over Wi-Fi |
| **Deploy Manager** (`QuestDeployManager.exe`) | a Windows PC, USB | first setup, recovery and roll back of headsets |

## What You Can Do

- see every headset with its status, battery, video and progress;
- play, pause, resume, stop, seek and recenter for the class or for selected headsets;
- set the volume for everyone or one headset;
- put the class to sleep and wake it over Wi-Fi;
- open, restart and close the player, and switch its autostart;
- send the lesson videos and new player versions over Wi-Fi;
- set the waiting-room look and Android system settings for every headset;
- set up, fix and remove headsets over USB;
- update everything from GitHub.

## A Typical Lesson

1. The headsets are set up once over USB with Deploy Manager.
2. The instructor starts the control panel; the headsets appear by themselves.
3. **Sync content** sends the lesson videos to every headset.
4. **Play All** starts the video for the class; **Recenter All** turns it to where the students look.
5. **Sleep All** at the end, **Wake All** next time.

## Limits

- the videos play from the headset storage (`/sdcard/Movies/`), not streamed;
- the control panel refers to videos by file name;
- 360° mono and flat 2D videos; stereo 3D is planned.

## Where To Go Next

- [Quick Start](quick-start.md)
- [Downloads](downloads.md)
- [Deploy Manager](deploy-manager.md)
