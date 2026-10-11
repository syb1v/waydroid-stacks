"""Движок преобразования клавиатуры/мыши в touch-события Android."""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Optional

from .keymap import Profile, Widget, W_TAP, W_HOLD, W_DPAD, W_AIM, W_SWIPE
from .scrcpy import ScrcpySession, ACTION_DOWN, ACTION_UP, ACTION_MOVE


@dataclass
class _Pointer:
    pid: int
    x: float = 0.0
    y: float = 0.0
    down: bool = False


class InputMapper:
    """Преобразует события клавиатуры/мыши хоста в мультитач-события Android.

    Координаты: x,y в диапазоне 0..1 относительно области видео.
    """

    def __init__(self, session: ScrcpySession, profile: Profile):
        self.session = session
        self.profile = profile
        self.device_w, self.device_h = session.device_size

        self._next_pid = 10
        self._pointers: dict[str, _Pointer] = {}   # widget-key -> pointer
        self._pressed: set[str] = set()            # активные клавиши
        self._dpad_state: dict[int, set[str]] = {} # id(widget) -> направления
        self._aim: Optional[dict] = None           # активный aim-виджет
        self._last_tick = 0.0
        self.enabled = True

    # ------------------------------------------------------------- helpers
    def _pid(self) -> int:
        self._next_pid += 1
        return self._next_pid

    def _px(self, nx: float, ny: float) -> tuple[int, int]:
        return int(nx * (self.device_w - 1)), int(ny * (self.device_h - 1))

    def _touch_down(self, pid: int, nx: float, ny: float) -> None:
        x, y = self._px(nx, ny)
        self.session.touch(ACTION_DOWN, x, y, pid)

    def _touch_move(self, pid: int, nx: float, ny: float) -> None:
        x, y = self._px(nx, ny)
        self.session.touch(ACTION_MOVE, x, y, pid)

    def _touch_up(self, pid: int, nx: float, ny: float) -> None:
        x, y = self._px(nx, ny)
        self.session.touch(ACTION_UP, x, y, pid)

    # --------------------------------------------------------------- public
    def key_press(self, keyname: str) -> None:
        if not self.enabled or not keyname:
            return
        keyname = keyname.lower()
        if keyname in self._pressed:
            return
        self._pressed.add(keyname)

        for widget in self.profile.widgets:
            if widget.type in (W_TAP, W_HOLD) and widget.key.lower() == keyname:
                pid = self._pid()
                self._pointers[keyname] = _Pointer(pid)
                self._touch_down(pid, widget.x, widget.y)
                if widget.type == W_TAP:
                    # мгновенный тап
                    self._touch_up(pid, widget.x, widget.y)
                    self._pointers.pop(keyname, None)
                return

            if widget.type == W_SWIPE and widget.key.lower() == keyname:
                self._do_swipe(widget)
                return

            if widget.type == W_AIM and widget.key.lower() == keyname:
                pid = self._pid()
                x, y = self._px(widget.x, widget.y)
                self._aim = {"widget": widget, "pid": pid, "x": x, "y": y}
                self.session.touch(ACTION_DOWN, x, y, pid)
                return

            if widget.type == W_DPAD:
                keys = {k.lower() for k in widget.keys.values()}
                if keyname in keys:
                    directions = self._dpad_state.setdefault(id(widget), set())
                    for direction, k in widget.keys.items():
                        if k.lower() == keyname:
                            directions.add(direction)
                    pid = self._pid_for(widget)
                    self._update_dpad(widget)
                    return

    def key_release(self, keyname: str) -> None:
        if not keyname:
            return
        keyname = keyname.lower()
        self._pressed.discard(keyname)

        for widget in self.profile.widgets:
            if widget.type == W_HOLD and widget.key.lower() == keyname:
                ptr = self._pointers.pop(keyname, None)
                if ptr:
                    self._touch_up(ptr.pid, widget.x, widget.y)
                return

            if widget.type == W_AIM and self._aim and \
                    widget.key.lower() == keyname and self._aim["widget"] is widget:
                self._close_aim()
                return

            if widget.type == W_DPAD:
                keys = {k.lower() for k in widget.keys.values()}
                if keyname in keys:
                    directions = self._dpad_state.get(id(widget), set())
                    for direction, k in widget.keys.items():
                        if k.lower() == keyname:
                            directions.discard(direction)
                    self._update_dpad(widget)
                    return

    def mouse_button(self, button: str, pressed: bool) -> None:
        """button: mouse1 / mouse2 / mouse3."""
        if pressed:
            # правой кнопкой можно назначить aim
            self.key_press(button)
        else:
            self.key_release(button)

    def mouse_move(self, dx: float, dy: float) -> None:
        if not self.enabled:
            return
        if self._aim:
            widget: Widget = self._aim["widget"]
            sens = max(0.05, widget.sensitivity)
            self._aim["x"] += dx * sens * 3.0
            self._aim["y"] += dy * sens * 3.0
            self._aim["x"] = min(max(0.0, self._aim["x"]), self.device_w - 1)
            self._aim["y"] = min(max(0.0, self._aim["y"]), self.device_h - 1)
            self.session.touch(ACTION_MOVE, int(self._aim["x"]), int(self._aim["y"]),
                               self._aim["pid"])

    def scroll(self, x_px: int, y_px: int, h: float, v: float) -> None:
        if self.enabled:
            self.session.scroll(x_px, y_px, h, v)

    def tick(self, now: Optional[float] = None) -> None:
        """Периодический вызов (~60 Гц): поддержка джойстиков и удержаний."""
        if not self.enabled:
            return
        now = now or time.monotonic()
        if now - self._last_tick < 1 / 60:
            return
        self._last_tick = now

        # джойстики продолжают слать движения (некоторые игры требуют поток)
        for widget in self.profile.widgets:
            if widget.type == W_DPAD and id(widget) in self._dpad_state:
                if self._dpad_state[id(widget)]:
                    self._update_dpad(widget)

    def reset(self) -> None:
        """Отпускает все активные касания."""
        for ptr in self._pointers.values():
            if ptr.down:
                self._touch_up(ptr.pid, 0.5, 0.5)
        self._pointers.clear()
        if self._aim:
            self._close_aim()
        self._pressed.clear()
        self._dpad_state.clear()

    # -------------------------------------------------------------- internal
    def _pid_for(self, widget: Widget) -> int:
        key = f"dpad:{id(widget)}"
        ptr = self._pointers.get(key)
        if not ptr:
            pid = self._pid()
            ptr = _Pointer(pid)
            self._pointers[key] = ptr
        return ptr.pid

    def _update_dpad(self, widget: Widget) -> None:
        directions = self._dpad_state.get(id(widget), set())
        key = f"dpad:{id(widget)}"
        ptr = self._pointers.get(key)
        if not ptr:
            return

        if not directions:
            if ptr.down:
                self._touch_up(ptr.pid, widget.x, widget.y)
                ptr.down = False
            self._pointers.pop(key, None)
            return

        vx = (1 if "right" in directions else 0) - (1 if "left" in directions else 0)
        vy = (1 if "down" in directions else 0) - (1 if "up" in directions else 0)
        norm = math.hypot(vx, vy) or 1.0
        vx, vy = vx / norm, vy / norm

        radius_x = widget.radius
        radius_y = widget.radius * (self.device_w / max(1, self.device_h)) \
            if self.device_h > self.device_w else widget.radius
        # радиус в нормализованных координатах по обеим осям одинаковый
        radius = widget.radius
        target_x = min(max(0.0, widget.x + vx * radius * 0.6), 1.0)
        target_y = min(max(0.0, widget.y + vy * radius * 0.6), 1.0)

        if not ptr.down:
            self._touch_down(ptr.pid, target_x, target_y)
            ptr.down = True
        else:
            self._touch_move(ptr.pid, target_x, target_y)
        ptr.x, ptr.y = target_x, target_y

    def _close_aim(self) -> None:
        if self._aim:
            self.session.touch(ACTION_UP, int(self._aim["x"]), int(self._aim["y"]),
                               self._aim["pid"])
            self._aim = None

    def _do_swipe(self, widget: Widget) -> None:
        pid = self._pid()
        self._touch_down(pid, widget.x, widget.y)
        steps = 8
        for i in range(1, steps + 1):
            nx = widget.x + widget.dx * (i / steps)
            ny = widget.y + widget.dy * (i / steps)
            self._touch_move(pid, min(max(0.0, nx), 1.0), min(max(0.0, ny), 1.0))
            time.sleep(max(0.005, widget.duration / steps))
        self._touch_up(pid, min(max(0.0, widget.x + widget.dx), 1.0),
                       min(max(0.0, widget.y + widget.dy), 1.0))
