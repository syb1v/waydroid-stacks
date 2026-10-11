"""Чтение геймпадов через evdev и трансляция в клавиши вида pad:*.

Кнопки и крестовина эмулируют обычные имена клавиш:
    pad:a, pad:b, pad:x, pad:y, pad:lb, pad:rb, pad:lt, pad:rt,
    pad:start, pad:select, pad:up, pad:down, pad:left, pad:right,
    pad:ls_x/pad:ls_y (оси левого стика как виртуальные направления
    pad:ls_left/pad:ls_right/pad:ls_up/pad:ls_down),
    pad:rs_* — аналогично для правого стика.
"""
from __future__ import annotations

import threading
from typing import Callable, Optional

try:
    from evdev import InputDevice, ecodes, list_devices
    HAS_EVDEV = True
except ImportError:  # evdev не установлен — геймпады отключены
    HAS_EVDEV = False

# Кнопки evdev -> имена pad:*
BUTTON_NAMES = {
    "BTN_A": "pad:a", "BTN_SOUTH": "pad:a",
    "BTN_B": "pad:b", "BTN_EAST": "pad:b",
    "BTN_X": "pad:x", "BTN_NORTH": "pad:x",
    "BTN_Y": "pad:y", "BTN_WEST": "pad:y",
    "BTN_TL": "pad:lb", "BTN_TR": "pad:rb",
    "BTN_TL2": "pad:lt", "BTN_TR2": "pad:rt",
    "BTN_SELECT": "pad:select", "BTN_START": "pad:start",
    "BTN_MODE": "pad:guide",
    "BTN_DPAD_UP": "pad:up", "BTN_DPAD_DOWN": "pad:down",
    "BTN_DPAD_LEFT": "pad:left", "BTN_DPAD_RIGHT": "pad:right",
    "BTN_THUMBL": "pad:l3", "BTN_THUMBR": "pad:r3",
}

AXIS_LEFT = {"ABS_X", "ABS_Y"}
AXIS_RIGHT = {"ABS_RX", "ABS_RY"}
HAT_MAP = {
    ("ABS_HAT0X", -1): "pad:left",
    ("ABS_HAT0X", 1): "pad:right",
    ("ABS_HAT0Y", -1): "pad:up",
    ("ABS_HAT0Y", 1): "pad:down",
}

STICK_THRESHOLD = 0.45   # доля от максимума
STICK_CENTER = 0.30      # гистерезис отпускания

if HAS_EVDEV:
    # обратный маппинг код -> имя (BTN_SOUTH и т.п.)
    CODE_TO_NAME: dict[int, str] = {}
    for _name, _code in ecodes.ecodes.items():
        if isinstance(_code, int):
            CODE_TO_NAME.setdefault(_code, _name)
else:
    CODE_TO_NAME = {}


def _which_stick(code_name: str) -> Optional[str]:
    if code_name in AXIS_LEFT:
        return "ls"
    if code_name in AXIS_RIGHT:
        return "rs"
    return None


class GamepadManager:
    """Слушает все подключённые геймпады и шлёт key_press/key_release."""

    def __init__(self, on_key: Callable[[str, bool], None]):
        self.on_key = on_key
        self._threads: list[threading.Thread] = []
        self._stop = threading.Event()
        self._devices: set[str] = set()
        self.connected: list[str] = []
        self._stick_state: dict[str, set[str]] = {}
        self._hat_state: dict[str, bool] = {}

    # -------------------------------------------------------------- control
    def start(self) -> None:
        if not HAS_EVDEV:
            return
        self._stop.clear()
        scanner = threading.Thread(target=self._scan_loop, name="gamepad-scan",
                                   daemon=True)
        scanner.start()
        self._threads.append(scanner)

    def stop(self) -> None:
        self._stop.set()

    def is_active(self) -> bool:
        return bool(self._threads) and not self._stop.is_set()

    # -------------------------------------------------------------- scanning
    def _scan_loop(self) -> None:
        while not self._stop.is_set():
            try:
                for path in list_devices():
                    if path in self._devices:
                        continue
                    try:
                        dev = InputDevice(path)
                    except OSError:
                        continue
                    caps = dev.capabilities()
                    keys = caps.get(ecodes.EV_KEY, [])
                    if not any(ecodes.ecodes.get(k, k) in BUTTON_NAMES or k in (304, 305)
                               for k in keys):
                        # не игровое устройство (клавиатура/мышь без кнопок пада)
                        if not (ecodes.BTN_GAMEPAD in keys or ecodes.BTN_SOUTH in keys):
                            dev.close()
                            continue
                    self._devices.add(path)
                    self.connected.append(dev.name)
                    t = threading.Thread(target=self._read_loop, args=(dev,),
                                         name=f"gamepad-{path.split('/')[-1]}",
                                         daemon=True)
                    t.start()
                    self._threads.append(t)
            except OSError:
                pass
            self._stop.wait(2.0)

    def _read_loop(self, dev: "InputDevice") -> None:
        try:
            for event in dev.read_loop():
                if self._stop.is_set():
                    break
                self._handle(dev, event)
        except (OSError, ValueError):
            pass
        finally:
            try:
                dev.close()
            except OSError:
                pass
            self._devices.discard(dev.path)
            try:
                self.connected.remove(dev.name)
            except ValueError:
                pass

    # -------------------------------------------------------------- mapping
    def _handle(self, dev: "InputDevice", event) -> None:
        name = CODE_TO_NAME.get(event.code, str(event.code)) \
            if isinstance(event.code, int) else str(event.code)
        if event.type == ecodes.EV_KEY:
            pad_name = BUTTON_NAMES.get(name)
            if pad_name:
                self.on_key(pad_name, event.value == 1)
        elif event.type == ecodes.EV_ABS:
            if name in ("ABS_HAT0X", "ABS_HAT0Y"):
                self._handle_hat(dev, name, event.value)
            else:
                self._handle_stick(dev, name, event.value, dev)

    def _handle_hat(self, dev, axis: str, value: int) -> None:
        for direction, axis_name in (("left", "ABS_HAT0X"), ("right", "ABS_HAT0X"),
                                     ("up", "ABS_HAT0Y"), ("down", "ABS_HAT0Y")):
            if axis_name != axis:
                continue
            want = -1 if direction in ("left", "up") else 1
            key = f"pad:{direction}"
            state_key = f"{id(dev)}:{key}"
            pressed = self._hat_state.get(state_key, False)
            should = value == want
            if should != pressed:
                self._hat_state[state_key] = should
                self.on_key(key, should)

    def _handle_stick(self, dev, axis: str, value: int, device) -> None:
        stick = _which_stick(axis)
        if not stick:
            return
        info = device.absinfo(ecodes.ecodes[axis])
        span = max(1, (info.max - info.min) / 2)
        norm = (value - (info.max + info.min) / 2) / span  # -1..1
        axis_letter = "x" if axis.endswith("X") else "y"
        neg_key = f"pad:{stick}_{'left' if axis_letter == 'x' else 'up'}"
        pos_key = f"pad:{stick}_{'right' if axis_letter == 'x' else 'down'}"
        state = self._stick_state.setdefault(str(id(dev)), set())

        for key, active in ((neg_key, norm <= -STICK_THRESHOLD),
                            (pos_key, norm >= STICK_THRESHOLD)):
            if active and key not in state:
                state.add(key)
                self.on_key(key, True)
            elif not active and key in state:
                # гистерезис: отпускаем, только когда стик вернулся ближе к центру
                if abs(norm) < STICK_CENTER:
                    state.discard(key)
                    self.on_key(key, False)
