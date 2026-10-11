"""Тихий IME-мост: ввод текста в поля Android без экранной клавиатуры.

Экранные клавиатуры (LatinIME и т.п.) при фокусе на текстовом поле выезжают
поверх игры и перекрывают кадр. Наша IME без UI (``third_party/wdsime.apk``,
исходники в ``ime/``) принимает текст broadcast'ами и коммитит его прямо в
сфокусированное поле через ``InputConnection.commitText``.

Ведение:
* при старте игрового окна APK ставится при необходимости, IME включается и
  выбирается; при закрытии окна возвращается прежняя клавиатура;
* фоновый поток опрашивает ``dumpsys input_method`` и публикует
  :attr:`text_active` — когда игра запросила ввод текста (``mShowRequested``),
  печатные клавиши и спецклавиши уходят в IME вместо FIFO-инъекции;
* текст и коды клавиш отправляются из отдельного потока, чтобы не блокировать
  UI-поток GTK; порядок «текст → спецклавиша» сохраняется.
"""
from __future__ import annotations

import base64
import threading

from . import config
from .adb import Adb, AdbError

IME_PKG = "io.github.syb1v.wdsime"
IME_ID = f"{IME_PKG}/.WdsIme"
ACTION_B64 = f"{IME_PKG}.INPUT_B64"
ACTION_CODE = f"{IME_PKG}.INPUT_CODE"


class ImeBridge:
    """Жизненный цикл тихой IME и очередь отправки текста/клавиш."""

    POLL_INTERVAL = 0.8

    def __init__(self, adb: Adb):
        self.adb = adb
        self.available = False
        self.text_active = False
        self._prev_ime = ""
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._queue: list[tuple[str, object]] = []
        self._wake = threading.Event()
        self._threads: list[threading.Thread] = []

    # ------------------------------------------------------------ lifecycle
    def start(self) -> bool:
        """Установить APK при необходимости, включить и выбрать IME."""
        try:
            if IME_PKG not in self.adb.shell_text(f"pm list packages {IME_PKG}"):
                apk = config.BUNDLED_IME_APK
                if not apk.exists():
                    return False
                self.adb.install_apk(str(apk))
            self._prev_ime = self.adb.shell_text(
                "settings get secure default_input_method", timeout=10).strip()
            self.adb.shell(f"ime enable {IME_ID}", timeout=10)
            self.adb.shell(f"ime set {IME_ID}", timeout=10)
        except AdbError:
            return False
        self.available = True
        for target in (self._send_loop, self._poll_loop):
            th = threading.Thread(target=target, daemon=True)
            th.start()
            self._threads.append(th)
        return True

    def stop(self) -> None:
        """Остановить потоки и вернуть прежнюю клавиатуру."""
        self._stop.set()
        self._wake.set()
        for th in self._threads:
            th.join(timeout=2)
        self._threads.clear()
        self.available = False
        if self._prev_ime and self._prev_ime != IME_ID:
            try:
                current = self.adb.shell_text(
                    "settings get secure default_input_method",
                    timeout=10).strip()
                if current == IME_ID:
                    self.adb.shell(f"ime set {self._prev_ime}", timeout=10)
            except AdbError:
                pass

    # -------------------------------------------------------------- send API
    def queue_text(self, text: str) -> None:
        """Поставить текст в очередь отправки (non-blocking)."""
        with self._lock:
            if self._queue and self._queue[-1][0] == "text":
                self._queue[-1] = ("text", str(self._queue[-1][1]) + text)
            else:
                self._queue.append(("text", text))
        self._wake.set()

    def queue_key(self, code: int) -> None:
        """Поставить код клавиши Android (non-blocking)."""
        with self._lock:
            self._queue.append(("key", int(code)))
        self._wake.set()

    # ---------------------------------------------------------------- workers
    def _send_loop(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(0.15)
            self._wake.clear()
            with self._lock:
                items, self._queue = self._queue, []
            for kind, payload in items:
                try:
                    if kind == "text":
                        b64 = base64.b64encode(
                            str(payload).encode("utf-8")).decode("ascii")
                        self.adb.shell(
                            f"am broadcast -a {ACTION_B64} --es msg {b64}",
                            timeout=10)
                    else:
                        self.adb.shell(
                            f"am broadcast -a {ACTION_CODE} --ei code "
                            f"{int(payload)}",
                            timeout=10)
                except AdbError:
                    pass

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            try:
                out = self.adb.shell_text("dumpsys input_method", timeout=10)
                self.text_active = (
                    "mShowRequested=true" in out
                    and f"mCurMethodId={IME_ID}" in out)
            except AdbError:
                self.text_active = False
            self._stop.wait(self.POLL_INTERVAL)

    # ------------------------------------------------------------------ misc
    def send_text(self, text: str) -> bool:
        """Синхронная отправка (для тестов/скриптов)."""
        try:
            b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
            self.adb.shell(f"am broadcast -a {ACTION_B64} --es msg {b64}",
                           timeout=10)
            return True
        except AdbError:
            return False


__all__ = ["ImeBridge", "IME_ID", "ACTION_B64", "ACTION_CODE"]
