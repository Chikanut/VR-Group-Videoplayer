# Prepare Videos

## Goal

Make sure lesson videos are stored correctly so the Quest player can find and open them, and that the control panel knows which **format** each video is (2D, 360°, VR180, mono or 3D).

## Required Storage Location

Copy every lesson video to:

`/sdcard/Movies/`

This path is important. The control panel sends only the filename, and the player looks for that file inside `/sdcard/Movies/`.

## File Naming Rule

Use the filename only in the control panel.

Examples:

- correct: `lesson01.mp4`
- correct: `history_360.mp4`
- not correct: `/sdcard/Movies/lesson01.mp4`

### Naming convention for format detection

Put the projection and the stereo layout at the **end** of the filename, before the extension:

```
<name>_<projection>_<stereo>.<ext>

projection: 180 | 360 | 2d
stereo:     LR (side-by-side 3D) | TB (top-bottom 3D) | MONO

reef-dive_180_LR.mp4          VR180 3D, left eye on the left half
classroom-tour_360_TB.mp4     360 3D, left eye on the top half
sunset_360_MONO.mp4           360 mono (also just sunset_360.mp4)
intro-lecture_2d_MONO.mp4     flat 2D
```

With this convention the control panel picks the format automatically (**Detect automatically** is on by default for new videos), and the same files also open correctly in the built-in Quest media player. Without a suffix the format falls back to 360 mono and the panel shows a warning — set it manually in that case.

## Supported Formats

| Format | Projection | Stereo | Typical source |
|---|---|---|---|
| **2D** | flat screen | mono | normal lecture video |
| **360°** | full sphere | mono | classic 360 video (default) |
| **360° 3D SBS / TB** | full sphere | left/right halves or top/bottom halves | 360 3D cameras, e.g. 5760x5760 top-bottom |
| **180°** | front hemisphere | mono | VR180 mono |
| **180° 3D SBS / TB** | front hemisphere | side-by-side or top-bottom | VR180 3D cameras, e.g. 8192x4096 side-by-side |

For 180° content the viewer must look at the front of the video; the player recenters automatically when such a video opens, and everything behind the viewer is black.

## Export Recommendations

- **Container:** MP4 or MOV (H.264 or HEVC). Both are probed the same way.
- **Resolution / frame rate:** the headset decoder is the limit. Modern Quest headsets decode HEVC up to 8192x4096 (Level 6.1). Use the **Probe file…** button in Settings to read the real resolution, fps, codec and bit depth of a file, and check the **Compatibility** section in a device's dialog: the panel warns when a file exceeds what a headset reports it can decode.
- **Bit depth:** 10-bit HEVC (Main10) needs a Main10-capable decoder. 8-bit is safer for older headsets.
- **Bitrate and size:** ~100 Mbit/s means about 730 MB per minute, i.e. ~7 GB for a 10-minute clip on every headset. Check free storage on the devices (shown in the device dialog) before copying.
- **Metadata:** some editors write wrong spherical metadata (e.g. VR180 tagged as full 360). The control panel trusts the filename first and the per-eye aspect ratio second, and shows a warning when the file's metadata disagrees.
- **Eye order:** if a 3D video looks "inside out", enable **Swap eyes** for that video in Settings instead of re-exporting.

## Recommended Preparation Workflow

1. Decide on the final filenames before copying files, following the naming convention above.
2. Copy the same filenames to every headset.
3. Open the control panel settings.
4. Add each lesson as a required video using that filename. The format is detected from the name; use **Probe file…** to verify the technical data and read the warnings.
5. Override the format manually only when the automatic result is wrong.

## Good Practice

- keep names short and clear, keep the `_180_LR` / `_360_TB` suffix
- avoid renaming files after you configure the lesson
- make sure every headset has the same content set
- test one video before class, and for 3D content check that depth looks natural (not inverted)
- headsets running an older player show 3D and 180° content as mono 360; the panel marks them with a **No 3D** badge

## Expected Result

When the control panel checks devices, the configured filename should be reported as available on each headset, and the video list shows the detected format badge (for example `180° 3D SBS`).

## Related Guides

- [Quick Start](quick-start.md)
- [Settings & Video Tuning](settings-and-video-tuning.md)
- [Daily Use](daily-use.md)
- [Networking and Troubleshooting](networking-troubleshooting.md)
