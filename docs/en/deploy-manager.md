# Deploy Manager

`QuestDeployManager.exe` sets up Meta Quest headsets over USB: it installs the player, copies videos, saves Wi-Fi networks, fixes stuck headsets and removes everything again. It runs on Windows and opens as its own window. The interface is in Ukrainian; the English names are given in brackets below.

![Deploy Manager with four headsets connected over USB](../assets/screenshots/deploy-devices.png)

## Before the First Use

1. **Developer mode.** In the Meta Horizon phone app open the headset → *Headset settings* → *Developer mode* and switch it on. This needs a Meta developer account (free) once per account.
2. **ADB.** Deploy Manager needs `adb.exe` from Android *platform-tools*. If it is not found, set its path in **Налаштування** (Settings).
3. **USB debugging.** Connect the headset, put it on and allow USB debugging. Tick *Always allow from this computer*, so it does not ask again.

The headset then appears in **Окуляри** (Headsets) with its serial number, model and installed player version. **Оновити список** (Refresh) looks again.

## What to Deploy

| Section | What you add |
|---|---|
| **Додатки (APK)** (Apps) | `VRClassroomPlayer-Quest.apk` and any other APK |
| **Файли** (Files) | lesson videos; the default destination is `/sdcard/Movies/` |
| **Wi-Fi** | the network name, password and security type |

The lists are saved in `quest_deploy_config.json` next to the exe and stay there for next time.

## Deploy

In **Окуляри** (Headsets) choose the options and press **Розгорнути** (Deploy):

- **Контент** (Content): apps and files, files only, or APKs only.
- **Автозапуск плеєра** (Player autostart): keep, switch on, or switch off.
- **Перевстановити APK** (Reinstall APK): uninstall and install again even when the same version is already there.

Tick headsets in the table to deploy only to them; with nothing ticked Deploy goes to every connected headset. The progress bars show the current file and the whole job; **Скасувати** (Cancel) stops after the current step.

When the player is installed, Deploy also prepares the headset once:

- makes the player its own installer, so later updates from the control panel install silently;
- lets the player start itself in the background and after a reboot;
- lets the player manage the videos in `/sdcard/Movies/` and apply the headset system settings from the control panel;
- lets it notice when the Meta Store opens on top of it;
- switches off Meta's first-time setup and tips windows, which hang without internet and block the player;
- sets `captive_portal_mode=0`, so a router without internet is not treated as a login page.

None of this can be done over Wi-Fi, which is why every headset goes through USB once.

## Wi-Fi

**Застосувати на окуляри** (Apply to headsets) saves the networks from the list on the connected headsets. With *Застосовувати Wi-Fi перед кожним розгортанням* (Apply Wi-Fi before every deploy) ticked, Deploy does it as its first step.

**Wireless ADB** is for debugging only: Quest forgets it on every reboot.

## Recover a Stuck Headset

Use **Відновити** (Recover) when a headset shows only the camera view (passthrough) without the Quest menu, or the dashboard tile says **Player will not open**. Recover closes the stuck Meta window (first-time setup, tips or Store), repairs the player's data folder if needed and starts the player again. If the menu does not come back within a minute, press **Перезавантажити** (Reboot).

## Roll Back Headsets

**Відкотити окуляри…** (Roll back headsets) returns the ticked headsets, or all connected ones, to their state before VR Classroom.

![Roll back panel](../assets/screenshots/deploy-rollback.png)

| Option | What it does |
|---|---|
| **Видалити плеєр** (Remove the player) | uninstalls `com.vrclass.player` with its data, permissions, autostart and headset name |
| **Увімкнути вікна Meta** (Turn Meta windows back on) | first-time setup and tips (`pm enable`) |
| **Повернути системні налаштування** (Restore system settings) | `captive_portal_mode` back to the default |
| **Видалити відео уроку** (Delete lesson videos) | the files from the **Файли** list and unfinished `.partial-*` downloads |
| **Забути Wi-Fi мережі** (Forget Wi-Fi networks) | the networks from the **Wi-Fi** list |

Other lines of the control panel's **Headset system settings** are restored by the player itself when that profile is empty. So before a roll back clear the profile in the control panel, save, and let the headsets connect once.

A roll back cannot be undone. To use a headset again, deploy it again.

## Updates

**Оновлення** (Updates) checks the latest GitHub release:

- **Завантажити APK плеєра** (Download player APK) downloads the new player and puts it in **Додатки** in place of the old one; then press Deploy;
- **Завантажити і перезапустити** (Download and restart) replaces Deploy Manager itself and starts the new version.

![Deploy Manager updates](../assets/screenshots/deploy-updates.png)

See [Updates](updates.md) for updating the headsets over Wi-Fi instead.
