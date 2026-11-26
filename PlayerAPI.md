# VR Classroom Player API

Плеєр керується через локальний HTTP API на порту `8080` та через WebSocket-команди від control panel.

- Порт плеєра: `8080`
- Каталог відео на пристрої: `/sdcard/Movies/`
- У командах `open` потрібно передавати лише **ім'я файлу**, без повного шляху

---

## Режими перегляду

| Значення | Режим |
|---|---|
| `360` або `sphere` | Сферичне 360° відео |
| `2d` або `flat` | Плоске 2D відео |

## Placement Override

Для `open` можна додатково передати `placementMode`:

| Значення | Поведінка |
|---|---|
| `default` | Використати стандартну логіку режиму |
| `locked` | Прив'язати відео до камери |
| `free` | Розмістити відео у вільному просторі |

Старі версії плеєра просто ігнорують `placementMode`.

---

## Основні команди

### `POST /open`

Відкриває файл з `/sdcard/Movies/` та автоматично запускає відтворення.

```bash
curl -X POST http://<IP>:8080/open \
  -H "Content-Type: application/json" \
  -d '{
    "file":"lesson01.mp4",
    "mode":"2d",
    "loop":false,
    "placementMode":"free"
  }'
```

Параметри:

| Поле | Тип | Опис |
|---|---|---|
| `file` | string | Ім'я файлу, наприклад `lesson01.mp4` |
| `mode` | string | `360` або `2d` |
| `loop` | bool | Чи повторювати відео |
| `placementMode` | string | `default`, `locked`, `free` |
| `advancedSettings` | object | Необов'язкові override transform/material налаштування |
| `autoRecenterOnOpen` | bool | За замовчуванням `true` |

### `POST /play`

```bash
curl -X POST http://<IP>:8080/play
```

### `POST /pause`

```bash
curl -X POST http://<IP>:8080/pause
```

### `POST /stop`

```bash
curl -X POST http://<IP>:8080/stop
```

### `POST /restart`

Перезапускає поточне відео.

```bash
curl -X POST http://<IP>:8080/restart
```

### `POST /recenter`

```bash
curl -X POST http://<IP>:8080/recenter
```

### `POST /volume`

```bash
curl -X POST http://<IP>:8080/volume \
  -H "Content-Type: application/json" \
  -d '{"globalVolume":0.8,"personalVolume":0.6}'
```

### `POST /seek`

Встановлює позицію відтворення у секундах. Значення clamp-иться в межах `0..duration`.
Поточний стан (playing/paused) зберігається. Якщо `canSetTime == false`, плеєр логує
попередження і команда ігнорується.

```bash
curl -X POST http://<IP>:8080/seek \
  -H "Content-Type: application/json" \
  -d '{"time":30}'
```

### `POST /sleep`

Приспає окуляри (віртуальний датчик наближення «знято», екран гасне, сон через ~15 с).

```bash
curl -X POST http://<IP>:8080/sleep
```

### `POST :8081/wake`

Будить окуляри. Слухає **сторож плеєра** на порту `8081`, а не сам плеєр: під час довгого сну Quest
вбиває процес плеєра, а сторож лишається доступним. Після пробудження сторож сам відкриває плеєр.

```bash
curl -X POST http://<IP>:8081/wake
```

### `POST :8081/autostart/off`, `POST :8081/autostart/on`, `GET :8081/autostart`

Вимикає / вмикає автозапуск плеєра сторожем (плеєр 1.8.2+). Стан зберігається в окулярах і переживає
перезавантаження та оновлення. Сторож і далі слухає порт `8081`, тож автозапуск можна повернути,
навіть коли плеєр закритий. Відповідь: `{"ok":true,"autostart":false}`.

```bash
curl -X POST http://<IP>:8081/autostart/off
```

### `POST :8081/server?address=ip:port`, `GET :8081/status`

Агент 1.9.0+: сервер підказує свою адресу (discovery сервера робить це сам), `GET` віддає останній
статус агента (див. «Агент окулярів»).

### `GET /status`

```bash
curl http://<IP>:8080/status
```

Приклад відповіді:

```json
{
  "deviceId": "quest-01",
  "deviceName": "12",
  "ip": "192.168.1.42",
  "androidId": "quest-01",
  "deviceModel": "Quest 3",
  "macAddress": "aa:bb:cc:dd:ee:ff",
  "state": "playing",
  "file": "lesson01.mp4",
  "mode": "2d",
  "time": 45.2,
  "duration": 180.0,
  "loop": false,
  "locked": false,
  "battery": 85,
  "batteryCharging": false,
  "uptimeMinutes": 12,
  "globalVolume": 1.0,
  "personalVolume": 1.0,
  "effectiveVolume": 1.0,
  "playerVersion": "1.7.0"
}
```

- `deviceId` — `android_id` пристрою (стабільний для встановленого APK).
- `deviceName` — ім'я/номер, збережене в окулярах; поле присутнє завжди (порожній рядок, якщо ім'я не задане).
- JSON формується на головному потоці Unity кожні ~0.5 с; HTTP-потік віддає кешований знімок, тому
  `/status` ніколи не повертає порожній `{}` через помилки потоку.

### `GET /files`

Повертає список файлів у `/sdcard/Movies/`.

```bash
curl http://<IP>:8080/files
```

Приклад:

```json
{
  "files": [
    {
      "name": "lesson01.mp4",
      "path": "/sdcard/Movies/lesson01.mp4",
      "size": 123456789,
      "hasAdvancedSettings": false
    }
  ]
}
```

### `PUT /name`

Задає ім'я/номер пристрою. Значення **зберігається в самих окулярах** (PlayerPrefs) і
показується на HUD плеєра; сервер лише віддзеркалює його. Після збереження плеєр одразу
надсилає серверу оновлений `status` з новим `deviceName`.

```bash
curl -X PUT http://<IP>:8080/name \
  -H "Content-Type: application/json" \
  -d '{"name":"12"}'
```

Відповідь: `{"ok":true,"name":"12"}`. Порожнє `name` очищає ім'я.

### `GET /device-info`

```json
{"deviceId":"<android_id>","deviceName":"12","ip":"192.168.1.42","playerVersion":"1.7.0"}
```

### `GET /debug` / `POST /debug`

Перемикає debug-панель.

```bash
curl http://<IP>:8080/debug
curl -X POST http://<IP>:8080/debug
```

### `PUT /server-ip`

Зберігає адресу control panel для WebSocket-підключення.

```bash
curl -X PUT http://<IP>:8080/server-ip \
  -H "Content-Type: application/json" \
  -d '{"serverIp":"192.168.1.10:8000"}'
```

### `POST /media/scan`

Перескановує вказані файли у системній медіатеці Android, щоб вони стали видимими в файлових застосунках і стандартному програвачі Quest.

```bash
curl -X POST http://<IP>:8080/media/scan \
  -H "Content-Type: application/json" \
  -d '{
    "files":[
      "/sdcard/Movies/lesson01.mp4"
    ]
  }'
```

Якщо `files` не передати, плеєр пересканує весь каталог `/sdcard/Movies/`.

---

## Агент окулярів (1.9.0+): єдиний канал до сервера

```
сервер  <── WebSocket /ws/agent ──>  агент (процес :watchdog)  <── 127.0.0.1:8082, JSON по рядку ──>  плеєр (Unity)
```

Агент (`Agent.java`) живе в процесі сторожа, тобто працює, поки ввімкнені окуляри: з плеєром і без
нього, під час сну теж (перевірено на Quest 3S: WS лишається відкритим, `wake` через нього будить
окуляри). Сам знаходить сервер (збережена адреса → сканування `/24` на порт 8000 → підказка від
сервера `POST :8081/server?address=ip:port`) і тримає keep-awake, поки сервер на звʼязку й увімкнено
автозапуск. Плеєр більше не ходить у мережу: він підключається лише до агента по localhost.

**Агент → сервер:** ті самі `register` / `status`, що й нижче. Це останній статус плеєра, доповнений
полями агента: `agent: true`, `agentVersion`, `playerRunning`, `autostart`, `files`
(`[{name,size}]` у `/sdcard/Movies`), `storageFreeMb`, `content` (прогрес завантажень:
`state` = `idle|downloading|waiting|error`, `file`, `done`, `total`, `queued`, `error`) та `update`
(`up to date`, `downloading N%`, `installing`, `failed: …`), `environment` (`default`, `custom`,
`downloading`, `failed: …`). Без плеєра `state` = `closed`.
`GET :8081/status` віддає той самий JSON (сервер пробує його, коли `:8080` мовчить).

**Сервер → агент:** ті самі `{"type":"command",...}`. Агент сам виконує:

| `action` | Поля | Опис |
|---|---|---|
| `launch_player`, `close_player`, `restart_player` | — | відкрити / закрити / перезапустити плеєр. Після `close_player` автозапуск не відкриває його, доки не прийде `launch_player` або не перезавантажаться окуляри |
| `wake`, `sleep` | — | розбудити / приспати окуляри (`sleep` спершу зупиняє відео в плеєрі) |
| `autostart` | `enabled` | як `POST :8081/autostart/on|off` |
| `set_name` | `name` | імʼя зберігає агент і передає плеєру для HUD |
| `apply_settings` | `settings` | профіль системних налаштувань (див. нижче) |
| `update` | `url`, `sha256` | агент сам завантажує й ставить APK, навіть коли плеєр закритий |
| `sync_content` | `files: [{name,size,url}]` | завантажити відео в `/sdcard/Movies`: файли з тим самим імʼям і розміром пропускаються, обрив докачується (HTTP Range), поки плеєр відтворює відео, завантаження на паузі |
| `cancel_content` | — | зупинити завантаження |
| `delete_content` | `files: [name]` | видалити відео з `/sdcard/Movies` |
| `set_environment` | `environment`, `logoUrl` | оточення кімнати очікування: `{custom, background: "#rrggbb", logoSha256, logoPosition: [x,y,z], logoSize, logoRotation: [x,y,z]}` (метри / градуси від точки старту глядача, X праворуч, Y вгору, Z вперед). Агент зберігає його й PNG у `files/` застосунку і передає плеєру командою `apply_environment {environment, logoPath}` (також щоразу, коли плеєр підключається). `custom: false` — стандартне оточення (модель логотипу + скайбокс) |

Решту команд (`open`, `play`, `pause`, `stop`, `seek`, …) агент передає плеєру. Для заміни файлів,
скопійованих кабелем, потрібен дозвіл `MANAGE_EXTERNAL_STORAGE`, який `tools/quest_deploy.py` видає
по USB.

## WebSocket-протокол (плеєр ↔ control panel)

Плеєри **до 1.9.0** самі підключаються до `ws://<server>:8000/ws/device` (адреса зберігається в
`instructor_ip`, або знаходиться скануванням підмережі). Плеєр 1.9.0+ надсилає ці самі повідомлення
агентові, а той пересилає їх на `/ws/agent`.

### Плеєр → сервер

| Повідомлення | Коли | Вміст |
|---|---|---|
| `{"type":"register", ...}` | одразу після підключення | усі поля `GET /status` |
| `{"type":"status", ...}` | одразу після `register`, далі кожні 5 с, а також після кожної команди та після зміни імені | усі поля `GET /status` |

Сервер бере стан відтворення **лише** зі `status`; `register` — це лише «привітання»
(старі версії плеєра надсилали в ньому `state: "idle"`, через що окуляри «блимали» станом
після кожного перепідключення).

### Сервер → плеєр

```json
{"type":"command","action":"<дія>", ...}
```

| `action` | Додаткові поля | Опис |
|---|---|---|
| `open` | `file`, `mode`, `loop`, `placementMode`, `autoRecenterOnOpen`, `advancedSettings` | як `POST /open` |
| `play`, `pause`, `stop`, `recenter`, `ping`, `toggle_debug` | — | як відповідні HTTP-команди |
| `seek` | `time` | як `POST /seek` |
| `sleep` | — | зупинити відео і приспати окуляри; розбудити — `POST :8081/wake` або кнопкою живлення |
| `set_volume` | `globalVolume`, `personalVolume` | як `POST /volume` |
| `set_mode` | `mode` | змінити режим перегляду |
| `set_name` | `name` | зберегти ім'я/номер в окулярах (як `PUT /name`); плеєр одразу відповідає `status` з новим `deviceName` |
| `apply_settings` | `settings` (рядки `global/<ключ>=<значення>` або `secure/<ключ>=<значення>`) | застосувати профіль системних налаштувань окулярів (плеєр 1.8.3+, потрібен дозвіл `WRITE_SECURE_SETTINGS`, який видає Deploy Manager по USB). Плеєр памʼятає початкові значення і повертає їх, коли рядок зникає з профілю; результат — поле `settingsProfile` у `status` (`ok` / `no permission` / `error`) |
| `update` | `url` (шлях на сервері, `/api/player/apk`), `sha256` | тихе самооновлення: якщо встановлений APK має інший sha256, плеєр завантажує APK із сервера і встановлює без підтвердження (потрібне одноразове налаштування через `tools/quest_deploy.py`) |

### Іменування пристроїв

1. Інструктор задає ім'я на панелі (`PUT /api/devices/{id}/name`).
2. Сервер надсилає `set_name` через WebSocket (або `PUT /name` через HTTP), показує ім'я
   як «очікує підтвердження» і зберігає його в `device_names.json` як резерв.
3. Окуляри зберігають ім'я (1.9.0+: в агенті, плеєр отримує копію для HUD; до 1.9.0: у PlayerPrefs
   плеєра), показують його на HUD і повертають у `status`.
4. Сервер бачить `deviceName` у `status` і вважає ім'я підтвердженим. Далі джерелом істини є
   окуляри: навіть якщо сервер перевстановити, ім'я з'явиться з першим же `status`.
5. Якщо окуляри були офлайн, ім'я буде надіслано при наступному підключенні.

---

## HTTP відповіді

Більшість POST/PUT ендпоінтів повертають:

```json
{"ok": true}
```

Типові помилки:

```json
{"error": "missing body"}
```

```json
{"error": "invalid json: ..."}
```
