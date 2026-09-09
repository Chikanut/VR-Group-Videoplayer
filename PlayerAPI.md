# VR Classroom Player API

Плеєр керується через локальний HTTP API на порту `8080` та через WebSocket-команди від control panel.

- Порт плеєра: `8080`
- Каталог відео на пристрої: `/sdcard/Movies/`
- У командах `open` потрібно передавати лише **ім'я файлу**, без повного шляху

---

## Формати відео

Формат відео складається з двох незалежних осей — **проєкції** та **стерео-розкладки**.
Разом вони утворюють канонічний `formatId`, який використовується в конфізі сервера (`videoType`), у REST API панелі та в полі `format` команди `open`.

| `formatId` | Проєкція (`projection`) | Стерео (`stereo`) | Опис |
|---|---|---|---|
| `2d` | `flat` | `mono` | Плоске 2D відео на віртуальному екрані |
| `360` | `360` | `mono` | Equirectangular 360° моно (дефолт) |
| `360_sbs` | `360` | `sbs` | 360° 3D, ліве око — ліва половина кадру |
| `360_tb` | `360` | `tb` | 360° 3D, ліве око — верхня половина кадру |
| `180` | `180` | `mono` | VR180 моно (півсфера 180°×180°) |
| `180_sbs` | `180` | `sbs` | VR180 3D side-by-side (`_180_LR`) |
| `180_tb` | `180` | `tb` | VR180 3D top-bottom |
| `auto` | — | — | Лише в конфізі сервера: визначити автоматично (ім'я файлу → пропорції + метадані) |

Аліаси, які приймають і сервер, і плеєр (регістр не важливий, порядок токенів не важливий):
`flat`→`2d`; `sphere`, `360_mono`→`360`; `180_lr`, `180_3dh`→`180_sbs`; `360_ou`, `360_3dv`→`360_tb`;
`360_lr`, `360_3dh`→`360_sbs`; `180_ou`, `180_3dv`→`180_tb`; `180_mono`→`180`.

### Legacy-поле `mode`

Плеєри до версії 1.7 знають лише `mode`: `360` або `2d`. Сервер **завжди** надсилає `mode` разом із новими полями:

| `formatId` | `mode` для старих плеєрів |
|---|---|
| `2d` | `2d` |
| `360`, `360_sbs`, `360_tb` | `360` |
| `180`, `180_sbs`, `180_tb` | `360` (старий плеєр розтягне півсферу на повну сферу, але не впаде) |

### Правила сумісності для `open`

1. Якщо в запиті є `projection` (і, опційно, `stereo`) — вони виграють. Якщо `mode` їм суперечить — плеєр пише попередження в лог і використовує `projection`/`stereo`.
2. Інакше, якщо є `format` — використовується він.
3. Інакше використовується `mode`. Якщо `mode` = `360`, а ім'я файлу має суфікс за конвенцією (`_180_LR`, `_360_TB` …), плеєр уточнює формат за ім'ям (сценарій «новий плеєр + старий сервер»).
4. Якщо нічого немає — лишається поточний формат, а якщо нічого не грає — `360` моно.
5. Невідомі поля ігноруються (`JsonUtility`), відсутні лишаються дефолтними. Старий плеєр просто не бачить нових полів.

### Конвенція імен файлів

```
<name>_<projection>_<stereo>.<ext>      projection: 180 | 360 | 2d     stereo: LR | TB | MONO
reef-dive_180_LR.mp4   classroom-tour_360_TB.mp4   sunset_360_MONO.mp4   intro_2d_MONO.mp4
```

Суфікс має стояти **в кінці** імені (перед розширенням). Це та сама конвенція, яку розуміє стандартний медіаплеєр Quest.

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
    "file":"reef-dive_180_LR.mp4",
    "mode":"360",
    "format":"180_sbs",
    "projection":"180",
    "stereo":"sbs",
    "swapEyes":false,
    "forwardYaw":0.0,
    "loop":false,
    "placementMode":"default",
    "autoRecenterOnOpen":true
  }'
```

Параметри:

| Поле | Тип | Опис |
|---|---|---|
| `file` | string | Ім'я файлу, наприклад `lesson01.mp4` |
| `mode` | string | Legacy: `360` або `2d`. Для старих плеєрів |
| `format` | string | Канонічний `formatId` (`180_sbs`, `360_tb` …). Необов'язкове |
| `projection` | string | `flat`, `180`, `360`. Має пріоритет над `mode`/`format` |
| `stereo` | string | `mono`, `sbs`, `tb`. Дефолт `mono` |
| `swapEyes` | bool | Поміняти ліве/праве око (матеріал експортовано навпаки). Дефолт `false` |
| `forwardYaw` | float | Довгота відео (градуси, `+` = праворуч від центру кадру), яка має опинитись перед глядачем після recenter. Дефолт `0` |
| `loop` | bool | Чи повторювати відео |
| `placementMode` | string | `default`, `locked`, `free` |
| `advancedSettings` | object | Необов'язкові override transform/material налаштування |
| `autoRecenterOnOpen` | bool | За замовчуванням `true`. Для `180` recenter виконується **завжди** (позаду глядача чорнота) |

Ті самі поля приймає WebSocket-команда `{"type":"command","action":"open", ...}`.

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

Приклад відповіді (плеєр ≥ 1.7):

```json
{
  "deviceId": "quest-01",
  "ip": "192.168.1.42",
  "state": "playing",
  "file": "reef-dive_180_LR.mp4",
  "mode": "360",
  "format": "180_sbs",
  "projection": "180",
  "stereo": "sbs",
  "swapEyes": false,
  "forwardYaw": 0.0,
  "videoWidth": 8192,
  "videoHeight": 4096,
  "backend": "unity",
  "maxTextureDimension": 4096,
  "decoderCaps": {
    "available": true,
    "hevcMaxWidth": 8192,
    "hevcMaxHeight": 8192,
    "hevcMain10": true,
    "hevcMaxLevel": "6.1",
    "hevcMaxFrameRateAt8K": 60,
    "hevcSupports8192x4096": true,
    "hevcSupports5760x5760": true,
    "hevcDecoder": "c2.qti.hevc.decoder",
    "avcMaxWidth": 4096,
    "avcMaxHeight": 4096,
    "maxTextureSize": 16384,
    "maxRenderTextureDimension": 4096,
    "systemMemoryMb": 7800,
    "graphicsMemoryMb": 1024,
    "storageFreeBytes": 41234567890,
    "storageTotalBytes": 118000000000
  },
  "time": 45.2,
  "duration": 180.0,
  "loop": false,
  "locked": false,
  "battery": 85,
  "batteryCharging": false,
  "uptimeMinutes": 12
}
```

- `mode` завжди лишається legacy-значенням (`360`/`2d`), щоб старі сервери працювали без змін.
- Старий плеєр не надсилає `projection`/`stereo`/`decoderCaps`; сервер виводить проєкцію з `mode` і позначає пристрій як такий, що не підтримує 3D (`stereoCapable: false` у стані пристрою на панелі).
- `decoderCaps` збирається один раз при старті через `MediaCodecList` (лише апаратні декодери), `storageFreeBytes` оновлюється кожні 30 с.

### `GET /decoder-caps`

Повертає лише об'єкт `decoderCaps` (див. вище).

### `GET /render-settings` / `PUT /render-settings`

Керує лімітом RenderTexture без перезбирання APK (для польових тестів 8K). Діє з наступного `open`.

```bash
curl http://<IP>:8080/render-settings
# {"maxTextureDimension":4096,"defaultMaxTextureDimension":4096,"hardwareMaxTextureSize":16384}

curl -X PUT http://<IP>:8080/render-settings \
  -H "Content-Type: application/json" \
  -d '{"maxTextureDimension":8192}'

curl -X PUT http://<IP>:8080/render-settings \
  -H "Content-Type: application/json" \
  -d '{"reset":true}'
```

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

Задає відображувану назву пристрою.

```bash
curl -X PUT http://<IP>:8080/name \
  -H "Content-Type: application/json" \
  -d '{"name":"Front Row 1"}'
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

## REST API панелі керування (порт 8000), пов'язане з форматами

| Метод і шлях | Опис |
|---|---|
| `GET /api/video-formats` | Список канонічних `formatId` з розбиттям на `projection`/`stereo` і `legacyMode` |
| `POST /api/videos/detect` `{"filename": "...", "videoType": "auto"}` | Визначення формату лише за ім'ям файлу |
| `POST /api/videos/probe` `{"path": "C:\\...\\clip_180_LR.mp4", "videoType": "auto"}` | Читає заголовки MP4/MOV (тільки `moov`, працює з `moov` у кінці файлу) і повертає роздільність, fps, кодек, профіль/рівень, бітову глибину, бітрейт, тривалість, розмір, аудіо, VR-метадані, `detectedType`, `detectionSource`, `warnings` |
| `GET /api/videos/{videoId}/compatibility` | Попередження по кожному онлайн-пристрою (ліміти декодера, старий плеєр, вільне місце) |
| `POST /api/playback/open` | Відповідь тепер містить `format` і `warnings` (по пристроях) додатково до `success`/`failed`/`missing` |

Поля `RequirementVideo` у `config.json`: `videoType` (`formatId` або `auto`), `swapEyes`, `forwardYaw`, і кеш автовизначення `detectedType`, `detectionSource`, `probe`. Старі конфіги без цих полів працюють без змін.

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
