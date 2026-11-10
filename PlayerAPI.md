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

## WebSocket-протокол (плеєр ↔ control panel)

Плеєр сам підключається до `ws://<server>:8000/ws/device` (адреса зберігається в
`instructor_ip`, або знаходиться скануванням підмережі).

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
| `set_volume` | `globalVolume`, `personalVolume` | як `POST /volume` |
| `set_mode` | `mode` | змінити режим перегляду |
| `set_name` | `name` | зберегти ім'я/номер в окулярах (як `PUT /name`); плеєр одразу відповідає `status` з новим `deviceName` |
| `update` | `url` (шлях на сервері, `/api/player/apk`), `sha256` | тихе самооновлення: якщо встановлений APK має інший sha256, плеєр завантажує APK із сервера і встановлює без підтвердження (потрібне одноразове налаштування через `tools/quest_deploy.py`) |

### Іменування пристроїв

1. Інструктор задає ім'я на панелі (`PUT /api/devices/{id}/name`).
2. Сервер надсилає `set_name` через WebSocket (або `PUT /name` через HTTP), показує ім'я
   як «очікує підтвердження» і зберігає його в `device_names.json` як резерв.
3. Окуляри зберігають ім'я в PlayerPrefs, показують його на HUD і повертають у `status`.
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
