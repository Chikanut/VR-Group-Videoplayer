# VR Classroom Player API

Плеєр підтримує два канали керування:

- **HTTP Server** — вбудований HTTP-сервер на порту `8080`, доступний по локальній мережі
- **ADB Broadcast** — широкомовні інтенти через `adb shell am broadcast`

Пакет додатку: `com.vrclass.player`
Відео шлях на пристрої: `/sdcard/Movies/`

---

## Стани плеєра

| Стан | Опис |
|------|------|
| `idle` | Нічого не завантажено |
| `loading` | Відео готується до відтворення |
| `ready` | Відео готове (автоматично переходить у `playing`) |
| `playing` | Відтворення |
| `paused` | Пауза |
| `completed` | Відтворення завершено |
| `error` | Помилка |

## Режими перегляду

| Значення | Режим |
|----------|-------|
| `360` або `sphere` | Сферичне 360° відео |
| `2d` або `flat` | Плоске 2D відео |

Режим за замовчуванням: `360` (Sphere360)

---

## Команди

### OPEN — Відкрити та відтворити відео

Відкриває файл з `/sdcard/Movies/` та автоматично починає відтворення.

**Параметри:**
| Параметр | Тип | Обов'язковий | Опис |
|----------|-----|:------------:|------|
| `file` | string | так | Ім'я файлу (напр. `lesson01.mp4`) |
| `mode` | string | ні | Режим перегляду: `360`, `sphere`, `2d`, `flat` |

**Server:**
```bash
curl -X POST http://<IP>:8080/open \
  -H "Content-Type: application/json" \
  -d '{"file":"lesson01.mp4","mode":"360"}'
```

**ADB:**
```bash
adb shell am broadcast -a com.vrclass.player.OPEN \
  --es file "lesson01.mp4" \
  --es mode "360"
```

---

### PLAY — Продовжити відтворення

Продовжує відтворення з паузи або після завершення.

**Server:**
```bash
curl -X POST http://<IP>:8080/play
```

**ADB:**
```bash
adb shell am broadcast -a com.vrclass.player.PLAY
```

---

### PAUSE — Поставити на паузу

**Server:**
```bash
curl -X POST http://<IP>:8080/pause
```

**ADB:**
```bash
adb shell am broadcast -a com.vrclass.player.PAUSE
```

---

### STOP — Зупинити відтворення

Повністю зупиняє відтворення, очищує екран та скидає стан у `idle`.

**Server:**
```bash
curl -X POST http://<IP>:8080/stop
```

**ADB:**
```bash
adb shell am broadcast -a com.vrclass.player.STOP
```

---

### RESTART — Перезапустити відео

Перемотує на початок та починає відтворення поточного відео.

**Server:**
```bash
curl -X POST http://<IP>:8080/restart
```

**ADB:**
```bash
adb shell am broadcast -a com.vrclass.player.RESTART
```

---

### RECENTER — Перецентрувати VR-вид

Скидає орієнтацію камери до поточного напрямку погляду користувача.

**Server:**
```bash
curl -X POST http://<IP>:8080/recenter
```

**ADB:**
```bash
adb shell am broadcast -a com.vrclass.player.RECENTER
```

---

### SET_MODE — Змінити режим перегляду

**Параметри:**
| Параметр | Тип | Обов'язковий | Опис |
|----------|-----|:------------:|------|
| `mode` | string | так | `360`, `sphere`, `2d`, `flat` |

**Server:** не має окремого ендпоінту — використовуйте параметр `mode` в `/open`.

**ADB:**
```bash
adb shell am broadcast -a com.vrclass.player.SET_MODE \
  --es mode "360"
```

---

### SET_LOOP — Увімкнути/вимкнути повтор

**Параметри:**
| Параметр | Тип | Обов'язковий | Опис |
|----------|-----|:------------:|------|
| `loop` | string | так | `true` або `false` |

**Server:** немає окремого ендпоінту.

**ADB:**
```bash
adb shell am broadcast -a com.vrclass.player.SET_LOOP \
  --es loop "true"
```

---

### LOCK — Заблокувати керування плеєром

Блокує UI-керування на шлемі. Учень не зможе змінювати відтворення.

**Server:**
```bash
curl -X POST http://<IP>:8080/lock
```

**ADB:** немає окремої команди.

---

### UNLOCK — Розблокувати керування

**Server:**
```bash
curl -X POST http://<IP>:8080/unlock
```

**ADB:** немає окремої команди.

---

### EMERGENCY STOP — Аварійна зупинка

Зупиняє відтворення та розблоковує керування одночасно.

**Server:**
```bash
curl -X POST http://<IP>:8080/emergencystop
```

**ADB:** немає окремої команди.

---

### GET_STATUS — Отримати статус пристрою

**Server:**
```bash
curl http://<IP>:8080/status
```

**ADB:**
```bash
adb shell am broadcast -a com.vrclass.player.GET_STATUS
```
> ADB-варіант виводить статус у Android logcat (тег `VRPlayer`):
> ```bash
> adb logcat -s VRPlayer
> ```

**Формат відповіді (JSON):**
```json
{
  "deviceId": "a1b2",
  "ip": "192.168.1.42",
  "online": true,
  "state": "playing",
  "file": "lesson01.mp4",
  "mode": "360",
  "time": 45.2,
  "duration": 180.0,
  "loop": false,
  "locked": false,
  "battery": 85,
  "batteryCharging": false,
  "uptimeMinutes": 12
}
```

| Поле | Тип | Опис |
|------|-----|------|
| `deviceId` | string | Коротке ID пристрою (останні 4 символи `deviceUniqueIdentifier` або з `device_id` у PlayerPrefs) |
| `ip` | string | Локальна IP-адреса |
| `online` | bool | Завжди `true` (пристрій відповідає) |
| `state` | string | Поточний стан плеєра |
| `file` | string | Ім'я поточного файлу |
| `mode` | string | `360` або `2d` |
| `time` | float | Поточна позиція в секундах |
| `duration` | float | Тривалість відео в секундах |
| `loop` | bool | Чи увімкнено повтор |
| `locked` | bool | Чи заблоковано керування |
| `battery` | int | Рівень заряду (0-100, або -1 якщо недоступно) |
| `batteryCharging` | bool | Чи заряджається |
| `uptimeMinutes` | int | Час роботи додатку в хвилинах |

---

### BATTERY — Отримати заряд батареї

**Server:**
```bash
curl http://<IP>:8080/battery
```

**Відповідь:**
```json
{
  "battery": 85,
  "charging": false
}
```

**ADB:** немає окремої команди (інформація є в `/status`).

---

### TOGGLE_DEBUG — Перемкнути панель налагодження

Показує або ховає екранну панель з логами. Також можна відкрити 3 швидкими натисканнями кнопки B на правому контролері.

**Server (GET — перемкнути):**
```bash
curl http://<IP>:8080/debug
```

**Server (POST — перемкнути або задати стан):**
```bash
# Перемкнути
curl -X POST http://<IP>:8080/debug

# Увімкнути
curl -X POST http://<IP>:8080/debug \
  -H "Content-Type: application/json" \
  -d '{"state":"on"}'

# Вимкнути
curl -X POST http://<IP>:8080/debug \
  -H "Content-Type: application/json" \
  -d '{"state":"off"}'
```

**ADB:**
```bash
adb shell am broadcast -a com.vrclass.player.TOGGLE_DEBUG
```

---

## Зведена таблиця

| Команда | HTTP Server | ADB Broadcast |
|---------|:-----------:|:-------------:|
| Відкрити відео | `POST /open` | `OPEN` |
| Відтворити | `POST /play` | `PLAY` |
| Пауза | `POST /pause` | `PAUSE` |
| Зупинити | `POST /stop` | `STOP` |
| Перезапустити | `POST /restart` | `RESTART` |
| Перецентрувати | `POST /recenter` | `RECENTER` |
| Змінити режим | (через `/open`) | `SET_MODE` |
| Увімкнути повтор | — | `SET_LOOP` |
| Заблокувати | `POST /lock` | — |
| Розблокувати | `POST /unlock` | — |
| Аварійна зупинка | `POST /emergencystop` | — |
| Отримати статус | `GET /status` | `GET_STATUS` |
| Батарея | `GET /battery` | — |
| Дебаг-панель | `GET/POST /debug` | `TOGGLE_DEBUG` |

## Відповіді HTTP-сервера

Всі POST-ендпоінти повертають `Content-Type: application/json`.

| Код | Відповідь | Опис |
|-----|-----------|------|
| `200` | `{"ok":true}` | Команда прийнята |
| `400` | `{"error":"..."}` | Невалідний запит (відсутні параметри, невалідний JSON) |
| `404` | `{"error":"not found"}` | Невідомий маршрут |
| `500` | `{"error":"..."}` | Внутрішня помилка сервера |

## Status Push (автоматичне надсилання статусу)

Якщо в `PlayerPrefs` встановлено `instructor_ip`, плеєр автоматично надсилає JSON-статус кожні 2 секунди на:
```
POST http://<instructor_ip>:9090/device_status
```
Це дозволяє інструкторській панелі отримувати оновлення без постійного опитування.
