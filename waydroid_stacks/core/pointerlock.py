"""Захват указателя через XWayland (Xlib) для инерционного обзора.

Wayland не даёт приложениям «запереть» курсор (нет публичного API у GTK4),
но XWayland поддерживает XWarpPointer: пока активен режим обзора, мы
опрашиваем позицию указателя, считаем дельту от центра и возвращаем курсор
назад. Получается бесконечное относительное движение — «мышь как тачпад».

Если DISPLAY/XWayland недоступны, модуль не активируется — вызывающий код
использует обычные дельты GTK.
"""
from __future__ import annotations

from typing import Optional


class PointerCapture:
    def __init__(self) -> None:
        self._display = None
        self._root = None
        self._center: Optional[tuple[int, int]] = None
        try:
            from Xlib import display as _xdisplay
            self._display = _xdisplay.Display()
            self._root = self._display.screen().root
        except Exception:  # noqa: BLE001
            self._display = None
            self._root = None

    @property
    def available(self) -> bool:
        return self._display is not None

    @property
    def active(self) -> bool:
        return self._center is not None

    def start(self) -> bool:
        if not self.available:
            return False
        try:
            screen = self._display.screen()
            width = screen.width_in_pixels
            height = screen.height_in_pixels
            self._root.warp_pointer(width // 2, height // 2)
            self._display.sync()
            self._center = (width // 2, height // 2)
            return True
        except Exception:  # noqa: BLE001
            self._center = None
            return False

    def poll_delta(self) -> tuple[float, float]:
        """Дельта указателя от центра + возврат курсора в центр."""
        if self._center is None:
            return 0.0, 0.0
        cx, cy = self._center
        try:
            q = self._root.query_pointer()
            dx = float(q.root_x - cx)
            dy = float(q.root_y - cy)
            if dx or dy:
                self._root.warp_pointer(cx, cy)
                self._display.sync()
            return dx, dy
        except Exception:  # noqa: BLE001
            return 0.0, 0.0

    def stop(self) -> None:
        if self._center is not None and self.available:
            cx, cy = self._center
            try:
                self._root.warp_pointer(cx, cy)
                self._display.sync()
            except Exception:  # noqa: BLE001
                pass
        self._center = None

    def close(self) -> None:
        self.stop()
        if self._display is not None:
            try:
                self._display.close()
            except Exception:  # noqa: BLE001
                pass
            self._display = None
            self._root = None
