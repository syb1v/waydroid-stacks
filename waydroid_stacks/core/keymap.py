"""Модель профилей кеймаппинга и их хранение."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from . import config

# Типы виджетов
W_TAP = "tap"        # нажатие клавиши -> тап по точке
W_HOLD = "hold"      # удержание клавиши -> палец держится на точке
W_DPAD = "dpad"      # WASD -> виртуальный джойстик
W_AIM = "aim"        # мышь (обзор) -> свайп-область камеры
W_SWIPE = "swipe"    # нажатие клавиши -> свайп по направлению

WIDGET_TYPES = (W_TAP, W_HOLD, W_DPAD, W_AIM, W_SWIPE)


@dataclass
class Widget:
    type: str = W_TAP
    key: str = ""                 # для tap/hold/aim/swipe: имя клавиши
    x: float = 0.5                # нормализованная позиция 0..1
    y: float = 0.5
    label: str = ""
    # dpad
    keys: dict = field(default_factory=lambda: {"up": "w", "down": "s", "left": "a", "right": "d"})
    radius: float = 0.12          # радиус джойстика (доля от min(w,h))
    # aim
    sensitivity: float = 1.0
    # swipe
    dx: float = 0.0               # нормализованное смещение свайпа
    dy: float = 0.0
    duration: float = 0.15        # сек
    # общее
    size: float = 0.06            # визуальный радиус маркера

    def to_json(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_json(data: dict) -> "Widget":
        known = {f for f in Widget.__dataclass_fields__}
        return Widget(**{k: v for k, v in data.items() if k in known})


@dataclass
class Profile:
    package: str
    widgets: list[Widget] = field(default_factory=list)

    def to_json(self) -> dict:
        return {"version": 1, "package": self.package,
                "widgets": [w.to_json() for w in self.widgets]}

    @staticmethod
    def from_json(data: dict) -> "Profile":
        return Profile(package=data.get("package", ""),
                       widgets=[Widget.from_json(w) for w in data.get("widgets", [])])


class ProfileStore:
    def __init__(self, directory: Optional[Path] = None):
        self.directory = directory or config.KEYMAP_DIR
        self.directory.mkdir(parents=True, exist_ok=True)

    def path_for(self, package: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", package)
        return self.directory / f"{safe}.json"

    def load(self, package: str) -> Profile:
        path = self.path_for(package)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Profile.from_json(data)
        except (OSError, ValueError):
            return Profile(package=package)

    def save(self, profile: Profile) -> Path:
        path = self.path_for(profile.package)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(profile.to_json(), ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(path)
        return path

    def exists(self, package: str) -> bool:
        return self.path_for(package).exists()

    def delete(self, package: str) -> None:
        try:
            self.path_for(package).unlink()
        except OSError:
            pass

    def list_packages(self) -> list[str]:
        result = []
        for f in sorted(self.directory.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                result.append(data.get("package", f.stem))
            except (OSError, ValueError):
                continue
        return result
