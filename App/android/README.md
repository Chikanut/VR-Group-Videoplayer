# Android packaging (Phase 4 scaffold)

Ця папка містить стартовий **Chaquopy**-проєкт для Android APK, який:

1. Запускає FastAPI сервер у фоновому `Service`.
2. Автоматично вимикає ADB (`VRCLASSROOM_DISABLE_ADB=1`).
3. Відкриває UI у `WebView` на `http://127.0.0.1:8000`.

## Структура

- `chaquopy/` — Android Studio проєкт.
- `app/src/main/java/.../ServerService.kt` — фоновий запуск Python сервера.
- `app/src/main/java/.../MainActivity.kt` — WebView wrapper.
- `app/src/main/python/android_service.py` — Python entrypoint для Uvicorn.

## Важливо

- `python.srcDirs` вказує на корінь репозиторію (`../../../`), щоб підхопити `App/server`.
- Для стабільного прод-збірки рекомендується зібрати окремий python package `control_panel` і підключити його як wheel, а не брати весь repo path.

## Як запустити

1. Відкрити `App/android/chaquopy` в Android Studio.
2. Дочекатись sync Gradle.
3. Запустити `app` на Android-девайсі.

Після старту, додаток підніме локальний сервер та відкриє control panel вбудовано в WebView.
