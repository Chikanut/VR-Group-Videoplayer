# Prepare Videos

## Goal

Make sure lesson videos are stored correctly so the Quest player can find and open them.

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

## Supported Viewing Modes

- `2D` or flat mode for normal video on a virtual screen
- `360` mode for equirectangular 360 video

## Recommended Preparation Workflow

1. Decide on the final filenames before copying files.
2. Copy the same filenames to every headset.
3. Open the control panel settings.
4. Add each lesson as a required video using that filename.
5. Select the correct video type for each lesson.

## Good Practice

- keep names short and clear
- avoid renaming files after you configure the lesson
- make sure every headset has the same content set
- test one video before class

## Expected Result

When the control panel checks devices, the configured filename should be reported as available on each headset.

## Related Guides

- [Quick Start](quick-start.md)
- [Daily Use](daily-use.md)
- [Networking and Troubleshooting](networking-troubleshooting.md)
