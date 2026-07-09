# v1.6.0 — Video Seek / Перемотка відео

---

## 🇬🇧 English

### Summary

This release adds **video seek** — you can now jump playback to any moment in a
video instead of only playing from the start. It works for the **whole class at
once** or for **one headset** on its own.

### ✨ What's New

- **Global Seek** — a new slider in the top control panel moves every connected
  headset to the same moment together, so the group stays in sync.
- **Per-headset Seek** — open a single headset and scrub only that one, without
  affecting the others (handy when one viewer needs to catch up).
- The seek slider follows playback automatically and shows the current time and
  total length (for example `1:12 / 3:40`). It stays disabled until a video is
  open and its length is known.
- The headset keeps playing or stays paused while you seek — it does not restart.

### 🩹 Also in this release

- Documentation now covers the **Settings page** and **how to tune videos**,
  including **removing black bars** by cropping and stretching the picture
  (English and Ukrainian, with illustrations).

### 📦 Included Downloads

- `VRClassroomPlayer-Quest.apk` — Meta Quest headset player
- `VRClassroomControlPanel-Windows.exe` — Windows control panel
- `VRClassroomControlPanel-Android.apk` — Android phone/tablet control panel

### 💻 Minimum Setup Requirements

- Meta Quest headset for playback
- Windows PC or Android device for instructor control
- Shared local Wi-Fi or LAN
- Lesson videos copied to `/sdcard/Movies/` on each headset

### 🔄 Upgrade Notes

- **Your settings are kept.** On the Windows control panel, just replace the
  `.exe` — do **not** delete `config.json` or `device_names.json` next to it.
  Older config files load and work unchanged.
- **Headsets:** reinstall the new player APK (upgrade in place keeps app data,
  and your videos in `/sdcard/Movies/` are never touched).
- The seek feature needs this player version on the headset **and** this control
  panel. Older players simply ignore the new command.

### 📖 Documentation

- English guides: `docs/en/` — see **Daily Use** and **Settings & Video Tuning**
- Ukrainian guides: `docs/uk/`

**Full changelog:** https://github.com/Chikanut/VR-Group-Videoplayer/compare/v1.5.5...v1.6.0

---

## 🇺🇦 Українська

### Коротко

Цей реліз додає **перемотку відео** — тепер можна перевести відтворення до
будь-якого моменту, а не лише запускати з початку. Це працює для **всього класу
одночасно** або для **однієї гарнітури** окремо.

### ✨ Що нового

- **Глобальна перемотка (Seek)** — новий повзунок у верхній панелі керування
  переводить усі підключені гарнітури до одного моменту разом, тож група
  залишається синхронною.
- **Перемотка окремої гарнітури** — відкрийте одну гарнітуру й перемотайте лише
  її, не зачіпаючи інші (зручно, коли одному глядачу треба наздогнати).
- Повзунок перемотки автоматично слідує за відтворенням і показує поточний час та
  загальну тривалість (наприклад `1:12 / 3:40`). Він неактивний, доки відео не
  відкрите і його тривалість невідома.
- Під час перемотки гарнітура продовжує відтворення або лишається на паузі — вона
  не перезапускається.

### 🩹 Також у цьому релізі

- Документація тепер описує **сторінку налаштувань (Settings)** і **як
  налаштовувати відео**, включно з **прибиранням чорних смуг** через обрізку і
  розтягування зображення (українською та англійською, з ілюстраціями).

### 📦 Файли для завантаження

- `VRClassroomPlayer-Quest.apk` — плеєр для гарнітури Meta Quest
- `VRClassroomControlPanel-Windows.exe` — панель керування для Windows
- `VRClassroomControlPanel-Android.apk` — панель керування для телефона/планшета Android

### 💻 Мінімальні вимоги

- Гарнітура Meta Quest для відтворення
- ПК на Windows або пристрій Android для керування
- Спільна локальна Wi-Fi або LAN мережа
- Відео уроків, скопійовані в `/sdcard/Movies/` на кожній гарнітурі

### 🔄 Нотатки щодо оновлення

- **Ваші налаштування зберігаються.** У панелі керування для Windows просто
  замініть `.exe` — **не** видаляйте `config.json` і `device_names.json` поруч із
  ним. Старі файли конфігурації завантажуються і працюють без змін.
- **Гарнітури:** перевстановіть новий APK плеєра (оновлення поверх зберігає дані
  додатку, а ваші відео в `/sdcard/Movies/` не чіпаються).
- Для перемотки потрібна ця версія плеєра на гарнітурі **та** ця панель керування.
  Старіші плеєри просто ігнорують нову команду.

### 📖 Документація

- Гайди англійською: `docs/en/` — див. **Daily Use** і **Settings & Video Tuning**
- Гайди українською: `docs/uk/`

**Повний список змін:** https://github.com/Chikanut/VR-Group-Videoplayer/compare/v1.5.5...v1.6.0
