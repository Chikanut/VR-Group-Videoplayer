# Updates

Every part updates from [GitHub Releases](https://github.com/Chikanut/VR-Group-Videoplayer/releases/latest). The computer running the control panel or Deploy Manager needs internet for the check and the download; the headsets do not.

## Control Panel

Open **Settings → Updates**. The panel shows its own version, the player versions on the headsets and the latest release with its notes. It checks once on start; switch **Check for updates on start** off to never contact GitHub. **Check now** asks again.

![Settings → Updates](../assets/screenshots/settings-updates.png)

- **Windows exe:** **Download and restart** downloads the new `VRClassroomControlPanel-Windows.exe`, replaces the running file and starts it again. Your `config.json` and headset names stay.
- **Android and running from source:** **Open the release** opens the release page; install the new file by hand.

When a newer version is out, the panel shows a banner at the top of every page.

## Player on the Headsets

**Settings → Updates → Update all headsets** downloads the player APK from the release to the PC and sends it to every connected headset. Each headset downloads it over Wi-Fi and installs it without asking, also while the player is closed. The tiles show the progress (`Player update: Downloading 62%`).

To send your own APK instead, enter it as **Settings → System → Player APK path** and press **Update players**.

Silent updates need:

- the one-time setup from Deploy Manager;
- every APK signed with the same key, which is true for the releases.

A headset that already has the same APK skips it.

## Deploy Manager

Open **Оновлення** (Updates) in Deploy Manager:

- **Завантажити і перезапустити** (Download and restart) updates Deploy Manager itself;
- **Завантажити APK плеєра** (Download player APK) puts the new player in the APK list for the next Deploy over USB.

## Which Versions Work Together

The control panel works with older players, but new features need a recent player:

| Feature | Player version |
|---|---|
| Always connected agent, open/close player, content over Wi-Fi | 1.9.0+ |
| Headset environment | 1.9.1+ |
| Recover detection and Store guard | 1.9.2+ |

Updating the headsets to the same version as the control panel is the safe choice.
