from __future__ import annotations

import json
import sys
from pathlib import Path

from .models import UpdaterSettings


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def config_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "quest_updater.config.json"
    return repo_root() / "tools" / "quest_updater" / "quest_updater.config.json"


def default_settings() -> UpdaterSettings:
    root = repo_root()
    return UpdaterSettings(
        app_config_path=str(root / "App" / "config.json"),
        apk_path=str(root / "VRClassroomPlayer" / "Builds" / "VRClassroomVideoPlayer.apk"),
        content_root=str(root),
    ).normalized()


def load_settings() -> UpdaterSettings:
    path = config_path()
    defaults = default_settings()
    if not path.exists():
        return defaults

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return defaults

    try:
        return UpdaterSettings(**data).normalized()
    except TypeError:
        return defaults


def save_settings(settings: UpdaterSettings) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(settings.normalized().to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
