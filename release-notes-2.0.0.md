## 🇬🇧 English

### Summary
VR Classroom 2.0 is the first release we consider stable for daily lessons. Since 1.7, a lot was fixed on the headsets: memory, sleep and wake, autostart, lost connections and stuck Meta windows. 2.0 adds a new design for the control panel and Deploy Manager, updates straight from GitHub, and a full roll back of headsets.

### ✨ New
- **New design** for the control panel and Deploy Manager: one dark, clear look for both, readable in a lit classroom and on a phone.
  - Dashboard counters: online, playing, need attention, content ready.
  - Filters (all / online / problems / offline) and search by number or IP.
  - Commands grouped into Playback, Headsets, Player, and Autostart · content.
  - Settings with a section menu.
  - The headset app keeps its look.
- **Updates from GitHub.**
  - Control panel → *Settings → Updates* shows the panel version, the player versions on the headsets and the latest release with its notes.
  - *Download and restart* updates the Windows control panel in place.
  - *Update all headsets* sends the new player to the whole class over Wi-Fi.
  - The check needs internet only on the instructor PC and can be switched off.
- **Deploy Manager 2.0** opens in its own window and shows progress per file and for the whole job.
  - **Roll back headsets:** removes the player with its data, permissions and autostart, turns Meta's first-time setup and tips back on, and restores the system settings it changed. Deleting the lesson videos and forgetting the Wi-Fi networks are optional.
  - **Updates:** downloads the newest player APK and updates Deploy Manager itself.
- **Documentation** rewritten in English and Ukrainian: setup, Deploy Manager, settings, updates and troubleshooting, with screenshots.

### 🛠 Fixes in this release
- **Recover** also closes Meta's tips window (`com.oculus.guidebook`). Without internet it waits for a Meta sign-in and blocks the player the same way the first-time setup does. Deploy now switches it off too.
- **"VRPlayer isn't responding" after a reinstall.** Quest keeps the old player's data folder after an uninstall, and the new player could not write to it. Deploy Manager now clears the player data before every uninstall, and *Recover* repairs it.
- The headset agent no longer touches the network on the main thread when a blocked launch clears. That could stop the agent's status report.
- The update card no longer offers to "update" headsets to an older release.

### 🧱 Stability work since 1.7 (all included)
- **Long sessions:** a fresh decoder for every video; no freeze or crash after several long videos.
- **Memory:** waiting-room GPU memory went from ~1.65 GB to ~0.7 GB, and a fresh player opens after sleep. This fixed the freezes after wake-up with 8K video.
- **Always connected (1.9):** the headset agent keeps the connection while the player is closed and while the headset sleeps. It finds the control panel by itself.
- **Commands are not lost:** a Stop sent while a headset sleeps is re-sent when it wakes. Short Wi-Fi drops no longer flip the tiles offline.
- **Autostart and keep-awake:** the player opens by itself after wake or reboot, and the headsets stay awake during a lesson.
- **Stuck Quest windows (1.9.2):** "Player will not open" warning on the tiles, the Meta Store closes by itself, and *Recover* in Deploy Manager.

### ⚠️ Notes
- **Updating from 1.9.x:** replace the control panel exe and keep `config.json` and `device_names.json` next to it. Then *Settings → Updates → Update all headsets*.
- **Headsets on 1.8.x or older:** do one USB pass with Deploy Manager → *Deploy* first.
- Run **Deploy** once more on each headset to switch off the Meta tips window (new in this release). Without it, *Recover* still closes it when it appears.
- Tested: the builds, the new control panel and Deploy Manager with simulated headsets, plus the server tests. The new roll back was tested with simulated ADB, not yet on a real headset.

### 📦 Included Downloads
- `VRClassroomPlayer-Quest.apk`: player for Meta Quest headsets (2.0.0)
- `VRClassroomControlPanel-Windows.exe`: control panel for Windows
- `VRClassroomControlPanel-Android.apk`: control panel for Android phones/tablets
- `QuestDeployManager.exe`: USB setup, recovery, roll back and updates (Windows)

---

## 🇺🇦 Українська

### Коротко
VR Classroom 2.0 — перший реліз, який ми вважаємо стабільним для щоденних уроків. Починаючи з 1.7 на окулярах виправлено багато: пам'ять, сон і пробудження, автозапуск, втрату зв'язку і вікна Meta, що зависали. У 2.0 — новий дизайн панелі керування і Deploy Manager, оновлення прямо з GitHub і повний відкат окулярів.

### ✨ Нове
- **Новий дизайн** панелі керування і Deploy Manager: один темний і зрозумілий вигляд для обох, добре читається у світлому класі й на телефоні.
  - Лічильники на пульті: на зв'язку, відтворюють, потребують уваги, контент готовий.
  - Фільтри (усі / на зв'язку / проблеми / офлайн) і пошук за номером чи IP.
  - Команди згруповано: Відтворення, Окуляри, Плеєр, Автозапуск · контент.
  - Налаштування з меню розділів.
  - Вигляд застосунку в окулярах не змінився.
- **Оновлення з GitHub.**
  - Панель → *Налаштування → Оновлення* показує версію панелі, версії плеєра на окулярах і останній реліз з описом.
  - *Завантажити і перезапустити* оновлює панель на Windows на місці.
  - *Оновити всі окуляри* надсилає новий плеєр усьому класу по Wi-Fi.
  - Інтернет потрібен лише на ПК викладача; перевірку можна вимкнути.
- **Deploy Manager 2.0** відкривається в окремому вікні з прогресом для кожного файлу і всього завдання.
  - **Відкотити окуляри:** видаляє плеєр разом з даними, дозволами й автозапуском, знову вмикає першу настройку і підказки Meta та повертає змінені системні налаштування. Видалення відео уроку і забування мереж Wi-Fi — за бажанням.
  - **Оновлення:** завантажує найновіший APK плеєра і оновлює сам Deploy Manager.
- **Документацію** переписано англійською та українською: налаштування, Deploy Manager, параметри, оновлення й усунення проблем, зі скріншотами.

### 🛠 Виправлення в цьому релізі
- **Відновити** також закриває вікно підказок Meta (`com.oculus.guidebook`). Без інтернету воно чекає входу в акаунт Meta і так само блокує плеєр, як перша настройка. Розгортання тепер теж його вимикає.
- **«VRPlayer isn't responding» після перевстановлення.** Quest залишає папку даних старого плеєра після видалення, і новий плеєр не міг у неї писати. Deploy Manager тепер очищає дані плеєра перед кожним видаленням, а *Відновити* лагодить їх.
- Агент окулярів більше не звертається до мережі з головного потоку, коли заблокований запуск відновлюється. Це могло зупинити звіт про стан.
- Картка оновлень більше не пропонує «оновити» окуляри до старішого релізу.

### 🧱 Робота над стабільністю з 1.7 (усе включено)
- **Довгі заняття:** новий декодер для кожного відео; немає зависань і вильотів після кількох довгих відео.
- **Пам'ять:** у кімнаті очікування ~0.7 ГБ замість ~1.65 ГБ пам'яті GPU, а після сну відкривається свіжий плеєр. Це прибрало зависання після пробудження з 8K відео.
- **Завжди на зв'язку (1.9):** агент окулярів тримає з'єднання, коли плеєр закритий і коли окуляри сплять. Панель він знаходить сам.
- **Команди не губляться:** «Зупинити», надіслане під час сну, повторюється після пробудження. Короткі обриви Wi-Fi не перемикають плитки в офлайн.
- **Автозапуск і «не спати»:** плеєр сам відкривається після пробудження чи перезавантаження, а окуляри не засинають під час уроку.
- **Вікна Quest, що зависали (1.9.2):** попередження «Плеєр не відкривається» на плитках, магазин Meta закривається сам, *Відновити* в Deploy Manager.

### ⚠️ Примітки
- **Оновлення з 1.9.x:** замініть exe панелі, `config.json` і `device_names.json` залиште поруч. Потім *Налаштування → Оновлення → Оновити всі окуляри*.
- **Окуляри на 1.8.x і старіших:** спершу один раз через USB у Deploy Manager → *Розгорнути*.
- Зробіть **Розгорнути** ще раз для кожних окулярів, щоб вимкнути вікно підказок Meta (нове в цьому релізі). Без цього *Відновити* все одно закриває його, коли воно з'являється.
- Перевірено: збірки, нова панель і Deploy Manager з імітованими окулярами, тести сервера. Новий відкат перевірено з імітованим ADB, на справжніх окулярах — ще ні.

### 📦 Файли
- `VRClassroomPlayer-Quest.apk`: плеєр для окулярів Meta Quest (2.0.0)
- `VRClassroomControlPanel-Windows.exe`: панель керування для Windows
- `VRClassroomControlPanel-Android.apk`: панель керування для Android телефонів/планшетів
- `QuestDeployManager.exe`: налаштування через USB, відновлення, відкат і оновлення (Windows)
