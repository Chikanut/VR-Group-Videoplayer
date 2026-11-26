# Prepare Videos

The player opens videos from `/sdcard/Movies/` on the headset. The control panel refers to a video by its file name only.

## Name the Files

- use the file name only in the control panel: `lesson01.mp4`, not `/sdcard/Movies/lesson01.mp4`;
- keep the names short and do not rename files after adding them;
- every headset needs the same files.

Supported types: `360` (equirectangular 360°) and `2D` (a flat screen). MP4 with H.264 or H.265 works best; Quest 3 / 3S play 8K 360° video.

## Add Them to the Lesson

**Settings → Lesson videos → + Add Video**: a name you choose, the exact file name and the type. Press **Save changes**.

![Settings → Lesson videos](../assets/screenshots/settings-videos.png)

## Copy Them to the Headsets

### Over Wi-Fi (player 1.9.0+)

1. Put all videos in one folder on the PC running the control panel.
2. Enter it as **Settings → System → Video library folder** and save.
3. Press **Sync content** on the dashboard.

Each headset downloads the lesson videos it does not have yet:

- files with the same name and size are skipped;
- a file of another size is replaced;
- downloads pause while a video plays and continue after a dropped connection.

The tiles show the progress (`Content: lesson01.mp4 40%`).

### Over USB

Add the files in Deploy Manager → **Файли** (Files) with the destination `/sdcard/Movies/` and deploy with **Контент: Лише файли / відео** (files only). This is faster for the first copy of large files.

## Check

When every headset has every video, the tiles say **Requirements met** and the **Content** counter shows all headsets ready. A tile with a red frame says which video is missing; the device window lists them.

## Related Guides

- [Settings & Video Tuning](settings-and-video-tuning.md)
- [Daily Use](daily-use.md)
