"""Клиент scrcpy-server: жизненный цикл и протокол управления (touch/key/text/scroll).

Протокол совместим со scrcpy 3.3.x (control-сокет, big-endian).
"""
from __future__ import annotations

import os
import secrets
import socket
import struct
import subprocess
import threading
import time
from typing import Callable, Optional

from .adb import Adb, AdbError
from . import config

# android.view.MotionEvent
ACTION_DOWN = 0
ACTION_UP = 1
ACTION_MOVE = 2
ACTION_HOVER_MOVE = 7

# scrcpy control message types
TYPE_INJECT_KEYCODE = 0
TYPE_INJECT_TEXT = 1
TYPE_INJECT_TOUCH_EVENT = 2
TYPE_INJECT_SCROLL_EVENT = 3
TYPE_BACK_OR_SCREEN_ON = 4

# scrcpy pointer id conventions
POINTER_ID_MOUSE = -1
POINTER_ID_GENERIC_FINGER = -2

SERVER_DEVICE_PATH = "/data/local/tmp/scrcpy-server.jar"


class ScrcpyError(RuntimeError):
    pass


class ScrcpySession:
    """Запускает scrcpy-server на устройстве и предоставляет control/video сокеты."""

    def __init__(
        self,
        adb: Adb,
        server_path: Optional[str] = None,
        version: str = config.SCRCPY_VERSION,
        max_size: int = 0,
        max_fps: int = 0,
    ):
        self.adb = adb
        self.server_path = str(server_path or config.BUNDLED_SCRCPY_SERVER)
        self.version = version
        self.max_size = max_size
        self.max_fps = max_fps

        self.scid_hex = format(secrets.randbelow(0x7FFFFFFF), "x")
        self.socket_name = "scrcpy_" + format(int(self.scid_hex, 16), "08x")

        self._srv_sock: Optional[socket.socket] = None
        self.video_sock: Optional[socket.socket] = None
        self.control_sock: Optional[socket.socket] = None
        self._lock = threading.Lock()
        self._video_size = (0, 0)
        try:
            self.device_size: tuple[int, int] = adb.wm_size()
        except AdbError:
            self.device_size = config.DEFAULT_RESOLUTION
        self._stopped = False

    # ------------------------------------------------------------------ start
    def start(self, video: bool = True, control: bool = True,
              connect_timeout: float = 15.0) -> None:
        if not os.path.isfile(self.server_path):
            raise ScrcpyError(f"scrcpy-server не найден: {self.server_path}")

        self.adb._run(["reverse", "--remove-all"], timeout=10)
        port = self._free_port()
        res = self.adb._run(
            ["reverse", f"localabstract:{self.socket_name}", f"tcp:{port}"], timeout=10)
        if res.returncode != 0:
            raise ScrcpyError(res.stderr.decode("utf-8", errors="replace"))

        self.adb.push(self.server_path, SERVER_DEVICE_PATH)

        srv = socket.socket()
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", port))
        srv.listen(2)
        srv.settimeout(connect_timeout)
        self._srv_sock = srv

        args = (
            f"CLASSPATH={SERVER_DEVICE_PATH} app_process / "
            f"com.genymobile.scrcpy.Server {self.version} "
            f"scid={self.scid_hex} log_level=warn "
            f"video={'true' if video else 'false'} "
            f"audio=false "
            f"control={'true' if control else 'false'} "
            f"send_device_meta=false send_dummy_byte=false cleanup=false"
        )
        if self.max_size:
            args += f" max_size={self.max_size}"
        if self.max_fps:
            args += f" max_fps={self.max_fps}"

        self._server_proc = subprocess.Popen(
            [self.adb.adb_path, "-s", self.adb.serial, "shell", args],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        try:
            if video:
                self.video_sock, _ = srv.accept()
                codec = self._recv_exact(self.video_sock, 4)
                if codec not in (b"h264", b"h265", b"av1\x00", b"vp8\x00", b"vp9\x00"):
                    raise ScrcpyError(f"Неожиданный видеокодек: {codec!r}")
                self.codec = codec
                w, h = struct.unpack(">II", self._recv_exact(self.video_sock, 8))
                self._video_size = (w, h)
            if control:
                self.control_sock, _ = srv.accept()
                self.control_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except socket.timeout as exc:
            self.stop()
            raise ScrcpyError("scrcpy-server не подключился вовремя") from exc

    def _free_port(self) -> int:
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        return port

    @staticmethod
    def _recv_exact(sock: socket.socket, n: int) -> bytes:
        data = b""
        while len(data) < n:
            chunk = sock.recv(n - len(data))
            if not chunk:
                raise ScrcpyError("соединение закрыто")
            data += chunk
        return data

    @property
    def video_size(self) -> tuple[int, int]:
        return self._video_size

    # ---------------------------------------------------------------- control
    def touch(self, action: int, x: int, y: int, pointer_id: int,
              pressure: float = 1.0, buttons: int = 0) -> None:
        w, h = self._video_size if self._video_size != (0, 0) else self.device_size
        msg = struct.pack(
            ">BBQiiHHHII", TYPE_INJECT_TOUCH_EVENT, action, pointer_id & 0xFFFFFFFFFFFFFFFF,
            int(x), int(y), w, h, int(max(0.0, min(1.0, pressure)) * 0xFFFF), 0, buttons)
        self._send(msg)

    def key(self, action: int, keycode: int, repeat: int = 0, metastate: int = 0) -> None:
        msg = struct.pack(">BBIII", TYPE_INJECT_KEYCODE, action, keycode, repeat, metastate)
        self._send(msg)

    def text(self, s: str) -> None:
        data = s.encode("utf-8")
        msg = struct.pack(">BI", TYPE_INJECT_TEXT, len(data)) + data
        self._send(msg)

    def scroll(self, x: int, y: int, hscroll: float, vscroll: float) -> None:
        w, h = self._video_size if self._video_size != (0, 0) else self.device_size
        hs = int(max(-1.0, min(1.0, hscroll / 16.0)) * 0x7FFF)
        vs = int(max(-1.0, min(1.0, vscroll / 16.0)) * 0x7FFF)
        msg = struct.pack(">BiiHHhhI", TYPE_INJECT_SCROLL_EVENT, int(x), int(y),
                          w, h, hs, vs, 0)
        self._send(msg)

    def back(self) -> None:
        self.key(ACTION_DOWN, 4)  # KEYCODE_BACK
        self.key(ACTION_UP, 4)

    def _send(self, msg: bytes) -> None:
        if not self.control_sock:
            return
        with self._lock:
            try:
                self.control_sock.sendall(msg)
            except OSError:
                self._stopped = True

    # ------------------------------------------------------------------ video
    def stream_video(self, on_packet: Callable[[bytes], None]) -> threading.Thread:
        """Читает видеопакеты в отдельном потоке и отдаёт H.264 NAL-пакеты в callback."""
        if not self.video_sock:
            raise ScrcpyError("видеосокет не открыт")

        def _reader():
            sock = self.video_sock
            while not self._stopped:
                try:
                    header = self._recv_exact(sock, 12)
                except (ScrcpyError, OSError):
                    break
                size = struct.unpack(">I", header[8:12])[0]
                if size == 0:
                    continue
                try:
                    payload = self._recv_exact(sock, size)
                except (ScrcpyError, OSError):
                    break
                on_packet(payload)

        t = threading.Thread(target=_reader, name="scrcpy-video", daemon=True)
        t.start()
        return t

    # ------------------------------------------------------------------- stop
    def stop(self) -> None:
        self._stopped = True
        for sock in (self.video_sock, self.control_sock, self._srv_sock):
            try:
                if sock:
                    sock.close()
            except OSError:
                pass
        self.video_sock = self.control_sock = self._srv_sock = None
        try:
            self.adb.shell("pkill -f scrcpy-server", timeout=8)
        except AdbError:
            pass
        try:
            self.adb._run(["reverse", "--remove-all"], timeout=8)
        except AdbError:
            pass
