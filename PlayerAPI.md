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

### `GET /status`

```bash
curl http://<IP>:8080/status
```

Приклад відповіді:

```json
{
  "deviceId": "quest-01",
  "ip": "192.168.1.42",
  "state": "playing",
  "file": "lesson01.mp4",
  "mode": "2d",
  "time": 45.2,
  "duration": 180.0,
  "loop": false,
  "locked": false,
  "battery": 85,
  "batteryCharging": false,
  "uptimeMinutes": 12
}
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
