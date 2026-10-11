"""Конфигурация и пути приложения."""
from __future__ import annotations

import os
from pathlib import Path

APP_ID = "io.github.syb1v.WaydroidStacks"
APP_NAME = "Waydroid Stacks"

XDG_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
XDG_DATA = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
XDG_CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))

CONFIG_DIR = XDG_CONFIG / "waydroid-stacks"
DATA_DIR = XDG_DATA / "waydroid-stacks"
CACHE_DIR = XDG_CACHE / "waydroid-stacks"

SETTINGS_FILE = CONFIG_DIR / "settings.json"
KEYMAP_DIR = CONFIG_DIR / "keymaps"
ICON_CACHE_DIR = CACHE_DIR / "icons"
APK_CACHE_DIR = CACHE_DIR / "apks"
SHOT_DIR = CACHE_DIR / "shots"

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BUNDLED_SCRCPY_SERVER = PROJECT_ROOT / "third_party" / "scrcpy-server"
BUNDLED_IME_APK = PROJECT_ROOT / "third_party" / "wdsime.apk"
SCRCPY_VERSION = "3.3.1"

DEFAULT_ADB_SERIAL = "192.168.240.112:5555"

# Разрешение виртуального экрана Android по умолчанию
DEFAULT_RESOLUTION = (1920, 1080)

# scrcpy max_size по умолчанию (0 = нативное)
DEFAULT_MAX_SIZE = 1280
DEFAULT_MAX_FPS = 60

DEFAULTS = {
    "adb_serial": DEFAULT_ADB_SERIAL,
    "max_size": DEFAULT_MAX_SIZE,
    "max_fps": DEFAULT_MAX_FPS,
    "theme": "dark",
    "show_system_apps": False,
    "start_session_on_launch": True,
}


def ensure_dirs() -> None:
    for d in (CONFIG_DIR, DATA_DIR, CACHE_DIR, KEYMAP_DIR, ICON_CACHE_DIR,
              APK_CACHE_DIR, SHOT_DIR):
        d.mkdir(parents=True, exist_ok=True)


def load_settings() -> dict:
    import json
    ensure_dirs()
    data = dict(DEFAULTS)
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data.update(json.load(f))
    except (OSError, ValueError):
        pass
    return data


def save_settings(settings: dict) -> None:
    import json
    ensure_dirs()
    tmp = SETTINGS_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    tmp.replace(SETTINGS_FILE)


def _xdg_user_dir(name: str, fallback: str) -> Path:
    import subprocess
    try:
        proc = subprocess.run(["xdg-user-dir", name], capture_output=True, timeout=5)
        if proc.returncode == 0:
            p = proc.stdout.decode().strip()
            if p and p != str(Path.home()):
                return Path(p)
    except (OSError, subprocess.TimeoutExpired):
        pass
    return Path.home() / fallback


def pictures_dir() -> Path:
    return _xdg_user_dir("PICTURES", "Изображения")


def videos_dir() -> Path:
    return _xdg_user_dir("VIDEOS", "Видео")
