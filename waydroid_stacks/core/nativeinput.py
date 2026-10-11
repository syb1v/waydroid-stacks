"""Нативная инъекция ввода в Waydroid через evdev-FIFO (без scrcpy-server).

Android в Waydroid (патч EventHub «Add wayland inputs support») читает ввод
напрямую из FIFO-файлов:

    /dev/input/wl_touch_events
    /dev/input/wl_keyboard_events
    /dev/input/wl_pointer_events

Мы открываем FIFO на запись (одним постоянным ``adb shell cat``-процессом на
канал) и пишем туда бинарные структуры ``struct input_event`` (evdev, 24 байта
на 64-битной платформе) — событие попадает в EventHub напрямую, минуя
scrcpy-server и Java-инжектор InputManager. Задержка и оверхед ниже, доступен
полноценный мультитач (до 10 слотов).

API совместим с методами :class:`ScrcpySession` (touch/key), чтобы InputMapper
работал с любым бэкендом.
"""
from __future__ import annotations

import os
import struct
import subprocess
import threading
import time
from typing import Optional

from .adb import Adb, AdbError
from . import config

TOUCH_FIFO = "/dev/input/wl_touch_events"
KEYBOARD_FIFO = "/dev/input/wl_keyboard_events"
POINTER_FIFO = "/dev/input/wl_pointer_events"

# linux/input-event-codes.h
EV_SYN, EV_KEY, EV_ABS, EV_REL = 0x00, 0x01, 0x03, 0x02
SYN_REPORT = 0x00

BTN_TOUCH = 0x14A         # 330
ABS_MT_SLOT = 0x2F        # 47
ABS_MT_TOUCH_MAJOR = 0x30 # 48
ABS_MT_POSITION_X = 0x35  # 53
ABS_MT_POSITION_Y = 0x36  # 54
ABS_MT_TRACKING_ID = 0x39 # 57
ABS_MT_PRESSURE = 0x3A    # 58

REL_WHEEL = 0x08

# android.view.MotionEvent
ACTION_DOWN, ACTION_UP, ACTION_MOVE = 0, 1, 2

MAX_SLOTS = 10

# android keycode -> linux keycode (то, что принимает Generic.kl)
ANDROID_TO_LINUX = {
    3: 172,    # HOME
    4: 158,    # BACK
    19: 103, 20: 108, 21: 105, 22: 106,  # стрелки
    24: 115, 25: 114,                    # громкость
    61: 15,    # TAB
    62: 57,    # SPACE
    66: 28,    # ENTER
    67: 14,    # BACKSPACE
    111: 1,    # ESCAPE
    112: 111,  # FORWARD_DEL
    187: 580,  # APP_SWITCH (недавние)
}
# буквы A..Z: android 29..54 -> linux (раскладка QWERTY)
ANDROID_TO_LINUX.update({
    29: 30, 30: 48, 31: 46, 32: 32, 33: 18, 34: 33, 35: 34, 36: 35,
    37: 23, 38: 36, 39: 37, 40: 38, 41: 50, 42: 49, 43: 24, 44: 25,
    45: 16, 46: 19, 47: 31, 48: 20, 49: 22, 50: 47, 51: 17, 52: 45,
    53: 21, 54: 44,
})
# цифры 0..9: android 7..16 -> linux 11..2
ANDROID_TO_LINUX.update({7 + i: 11 - i for i in range(10)})


class _FifoWriter:
    """Постоянный писатель в FIFO через один ``adb shell`` процесс."""

    def __init__(self, adb: Adb, fifo: str):
        self.adb = adb
        self.fifo = fifo
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._next_retry = 0.0

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def ensure(self, timeout: float = 3.0) -> bool:
        if self._proc and self._proc.poll() is None:
            return True
        now = time.monotonic()
        if now < self._next_retry:
            return False
        self._next_retry = now + 2.0
        # создаём FIFO, если его нет (например, wl_touch_events появляется
        # только при наличии touch-устройства на хосте, которого может не быть)
        script = (
            f"[ -p {self.fifo} ] || (mkfifo {self.fifo} && chmod 777 {self.fifo}); "
            f"[ -w {self.fifo} ] && exec cat > {self.fifo}"
        )
        try:
            self._proc = subprocess.Popen(
                [self.adb.adb_path, "-s", self.adb.serial, "shell", script],
                stdin=subprocess.PIPE)
            # неблокирующий stdin: при мёртвом EventHub (замороженный
            # контейнер) запись не должна вешать UI-поток
            os.set_blocking(self._proc.stdin.fileno(), False)
        except OSError:
            self._proc = None
            return False
        time.sleep(0.1)
        if self._proc.poll() is not None:
            # cat завершился — FIFO не пишется (нет прав/каталога)
            self._proc = None
            return False
        return True

    def write(self, data: bytes) -> bool:
        with self._lock:
            if not self.ensure():
                return False
            try:
                self._proc.stdin.write(data)
                self._proc.stdin.flush()
                return True
            except BlockingIOError:
                # очередь adb переполнена — дропаем событие, не блокируемся
                return False
            except (BrokenPipeError, ValueError, OSError):
                self._proc = None
                return False

    def stop(self) -> None:
        with self._lock:
            if self._proc:
                try:
                    self._proc.stdin.close()
                    self._proc.wait(timeout=3)
                except Exception:  # noqa: BLE001
                    try:
                        self._proc.kill()
                    except OSError:
                        pass
                self._proc = None


class WaydroidNativeInput:
    """Инъекция touch/клавиш напрямую в EventHub Android через FIFO."""

    def __init__(self, adb: Adb):
        self.adb = adb
        self._touch = _FifoWriter(adb, TOUCH_FIFO)
        self._keys = _FifoWriter(adb, KEYBOARD_FIFO)
        self._pointer = _FifoWriter(adb, POINTER_FIFO)
        self._slot_of: dict[int, int] = {}
        self._free_slots: list[int] = list(range(MAX_SLOTS))
        self._tid = 0
        self._active_pointers = 0
        self.available = False
        # интерфейс, совместимый со ScrcpySession
        try:
            self.device_size: tuple[int, int] = adb.wm_size()
        except AdbError:
            self.device_size = config.DEFAULT_RESOLUTION
        self.video_size: tuple[int, int] = (0, 0)

    @property
    def input_size(self) -> tuple[int, int]:
        # FIFO-события EventHub масштабирует по waydroid.display_width/height,
        # т.е. координаты — в пикселях логического экрана Android
        return self.device_size

    # ------------------------------------------------------------- lifecycle
    def start(self) -> bool:
        ok_touch = self._touch.ensure()
        ok_keys = self._keys.ensure()
        self.available = ok_touch
        return ok_touch and ok_keys

    def reensure(self) -> None:
        """Пересоздать писателей (после разморозки/реконнекта)."""
        if not self.available:
            return
        self._touch.ensure()
        self._keys.ensure()

    def release_all(self) -> None:
        """Отпустить все активные пальцы (безопасное завершение)."""
        if not self._slot_of:
            return
        data = b""
        for slot in self._slot_of.values():
            data += (self._ev(EV_ABS, ABS_MT_SLOT, slot) +
                     self._ev(EV_ABS, ABS_MT_TRACKING_ID, -1))
        data += self._ev(EV_KEY, BTN_TOUCH, 0) + self._ev(EV_SYN, SYN_REPORT, 0)
        self._touch.write(data)
        self._slot_of.clear()
        self._free_slots = list(range(MAX_SLOTS))
        self._active_pointers = 0

    def stop(self) -> None:
        self.release_all()
        self._touch.stop()
        self._keys.stop()
        self._pointer.stop()
        self.available = False

    # -------------------------------------------------------------- encoding
    @staticmethod
    def _ev(type_: int, code: int, value: int) -> bytes:
        ns = time.clock_gettime(time.CLOCK_MONOTONIC_RAW)
        sec = int(ns)
        usec = int((ns - sec) * 1_000_000)
        return struct.pack("<qqHHi", sec, usec, type_, code, value)

    def _next_tid(self) -> int:
        self._tid = (self._tid % 60000) + 1
        return self._tid

    # ----------------------------------------------------------------- touch
    def touch(self, action: int, x: int, y: int, pointer_id: int,
              pressure: float = 1.0, buttons: int = 0) -> None:
        if action == ACTION_DOWN:
            if pointer_id in self._slot_of:
                return
            slot = self._free_slots.pop(0) if self._free_slots else 0
            self._slot_of[pointer_id] = slot
            self._active_pointers += 1
            data = (
                self._ev(EV_ABS, ABS_MT_SLOT, slot) +
                self._ev(EV_ABS, ABS_MT_TRACKING_ID, self._next_tid()) +
                self._ev(EV_ABS, ABS_MT_POSITION_X, int(x)) +
                self._ev(EV_ABS, ABS_MT_POSITION_Y, int(y)) +
                self._ev(EV_ABS, ABS_MT_TOUCH_MAJOR, 8) +
                self._ev(EV_ABS, ABS_MT_PRESSURE,
                         50 if pressure >= 0.5 else 30)
            )
            if self._active_pointers == 1:
                data += self._ev(EV_KEY, BTN_TOUCH, 1)
            data += self._ev(EV_SYN, SYN_REPORT, 0)
            self._touch.write(data)

        elif action == ACTION_MOVE:
            slot = self._slot_of.get(pointer_id)
            if slot is None:
                return
            self._touch.write(
                self._ev(EV_ABS, ABS_MT_SLOT, slot) +
                self._ev(EV_ABS, ABS_MT_POSITION_X, int(x)) +
                self._ev(EV_ABS, ABS_MT_POSITION_Y, int(y)) +
                self._ev(EV_SYN, SYN_REPORT, 0))

        elif action == ACTION_UP:
            slot = self._slot_of.pop(pointer_id, None)
            if slot is None:
                return
            self._active_pointers = max(0, self._active_pointers - 1)
            data = (
                self._ev(EV_ABS, ABS_MT_SLOT, slot) +
                self._ev(EV_ABS, ABS_MT_TRACKING_ID, -1)
            )
            if self._active_pointers == 0:
                data += self._ev(EV_KEY, BTN_TOUCH, 0)
            data += self._ev(EV_SYN, SYN_REPORT, 0)
            self._touch.write(data)
            self._free_slots.append(slot)
            self._free_slots.sort()

    # -------------------------------------------------------------- keyboard
    def key(self, action: int, keycode: int, repeat: int = 0,
            metastate: int = 0) -> None:
        linux_code = ANDROID_TO_LINUX.get(keycode)
        if linux_code is None:
            return
        self._keys.write(
            self._ev(EV_KEY, linux_code, 1 if action == 0 else 0) +
            self._ev(EV_SYN, SYN_REPORT, 0))

    def tap_key(self, keycode: int) -> None:
        self.key(0, keycode)
        self.key(1, keycode)

    # ------------------------------------------------------------------ misc
    def scroll(self, x: int, y: int, hscroll: float, vscroll: float) -> None:
        # колесо через pointer FIFO: сначала позиция, затем REL_WHEEL
        direction = -1 if vscroll > 0 else 1
        data = (
            self._ev(EV_ABS, 0x00, int(x)) +   # ABS_X
            self._ev(EV_ABS, 0x01, int(y)) +   # ABS_Y
            self._ev(EV_SYN, SYN_REPORT, 0)
        )
        for _ in range(max(1, min(10, int(abs(vscroll))))):
            data += (self._ev(EV_REL, REL_WHEEL, direction) +
                     self._ev(EV_SYN, SYN_REPORT, 0))
        self._pointer.write(data)
