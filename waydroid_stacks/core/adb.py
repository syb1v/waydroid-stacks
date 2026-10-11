"""Обёртка над adb: подключение к Waydroid-контейнеру и shell-операции."""
from __future__ import annotations

import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Iterable, Sequence


class AdbError(RuntimeError):
    pass


@dataclass
class ShellResult:
    returncode: int
    stdout: bytes
    stderr: bytes

    @property
    def text(self) -> str:
        return self.stdout.decode("utf-8", errors="replace").strip()


class Adb:
    """Тонкая обёртка над adb с автоподключением к устройству."""

    _connect_lock = None  # инициализируется лениво

    def __init__(self, serial: str = "192.168.240.112:5555", adb_path: str | None = None):
        self.serial = serial
        self.adb_path = adb_path or shutil.which("adb") or "adb"
        if Adb._connect_lock is None:
            import threading
            Adb._connect_lock = threading.Lock()

    # ------------------------------------------------------------------ base
    def _run(self, args: Sequence[str], timeout: float = 30.0,
             binary: bool = False) -> ShellResult:
        cmd = [self.adb_path, "-s", self.serial, *args]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
        except FileNotFoundError as exc:
            raise AdbError("adb не найден. Установите android-tools.") from exc
        except subprocess.TimeoutExpired as exc:
            raise AdbError(f"adb timeout: {' '.join(args[:3])}") from exc
        return ShellResult(proc.returncode, proc.stdout, proc.stderr)

    def shell(self, command: str | Iterable[str], timeout: float = 30.0) -> ShellResult:
        if isinstance(command, str):
            args = ["shell", command]
        else:
            args = ["shell", *command]
        return self._run(args, timeout=timeout)

    def shell_text(self, command: str, timeout: float = 30.0) -> str:
        res = self.shell(command, timeout=timeout)
        if res.returncode != 0 and res.stderr:
            raise AdbError(res.stderr.decode("utf-8", errors="replace").strip())
        return res.text

    # ------------------------------------------------------------- connection
    def connect(self, retries: int = 4) -> bool:
        with Adb._connect_lock:
            # Уже подключены — ничего не делаем (повторный connect рвёт reverse-туннели)
            if self.is_online():
                return True
            last = None
            for _ in range(retries):
                self._run(["disconnect", self.serial], timeout=10)
                res = self._run(["connect", self.serial], timeout=15)
                out = (res.stdout + res.stderr).decode("utf-8", errors="replace").lower()
                if "connected" in out and "cannot" not in out:
                    state = self._run(["get-state"], timeout=10).text
                    if state == "device":
                        return True
                last = out.strip()
                time.sleep(1.5)
            raise AdbError(f"Не удалось подключиться к {self.serial}: {last}")

    def is_online(self) -> bool:
        try:
            return self._run(["get-state"], timeout=8).text == "device"
        except AdbError:
            return False

    def wait_boot(self, timeout: float = 120.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if self.shell_text("getprop sys.boot_completed", timeout=8) == "1":
                    return True
            except AdbError:
                pass
            time.sleep(1.5)
        return False

    # ----------------------------------------------------------------- system
    def wm_size(self) -> tuple[int, int]:
        out = self.shell_text("wm size")
        m = re.search(r"Override size:\s*(\d+)x(\d+)", out)
        if not m:
            m = re.search(r"Physical size:\s*(\d+)x(\d+)", out)
        if not m:
            raise AdbError(f"Не удалось определить размер экрана: {out!r}")
        return int(m.group(1)), int(m.group(2))

    # ---------------------------------------------------------------- fm / io
    def push(self, local: str, remote: str) -> None:
        res = self._run(["push", local, remote], timeout=120)
        if "1 file pushed" not in (res.stdout + res.stderr).decode("utf-8", "replace"):
            raise AdbError(f"adb push failed: {(res.stdout + res.stderr).decode()}")

    def pull(self, remote: str, local: str) -> None:
        res = self._run(["pull", remote, local], timeout=120)
        if res.returncode != 0:
            raise AdbError(res.stderr.decode("utf-8", errors="replace"))

    def exec_out(self, command: str, timeout: float = 60.0) -> bytes:
        res = self._run(["exec-out", command], timeout=timeout)
        if res.returncode != 0:
            raise AdbError(res.stderr.decode("utf-8", errors="replace"))
        return res.stdout

    # --------------------------------------------------------------- packages
    def list_packages(self, user_only: bool = True) -> list[str]:
        flag = "-3" if user_only else ""
        out = self.shell_text(f"pm list packages {flag}".strip())
        return sorted({line.removeprefix("package:").strip()
                       for line in out.splitlines() if line.startswith("package:")})

    def find_launchable(self) -> dict[str, str]:
        """Возвращает {package: activity} для всего, что можно запустить."""
        out = self.shell_text(
            "cmd package query-activities --brief "
            "-a android.intent.action.MAIN -c android.intent.category.LAUNCHER")
        result: dict[str, str] = {}
        for line in out.splitlines():
            line = line.strip()
            if "/" not in line or line.startswith(("Activity #", "priority=")):
                continue
            if "=" in line and not line.startswith("com."):
                continue
            pkg, _, activity = line.partition("/")
            pkg = pkg.strip()
            if not pkg or " " in pkg:
                continue
            result.setdefault(pkg, activity)
        return result

    def package_apk_path(self, package: str) -> str | None:
        out = self.shell_text(f"pm path {package}")
        for line in out.splitlines():
            if line.startswith("package:"):
                return line.removeprefix("package:").strip()
        return None

    def launch_app(self, package: str, activity: str | None = None) -> None:
        if activity:
            comp = f"{package}/{activity}"
            self.shell(f"am start -n {comp}")
        else:
            self.shell(f"monkey -p {package} -c android.intent.category.LAUNCHER 1")

    def stop_app(self, package: str) -> None:
        self.shell(f"am force-stop {package}")

    def install_apk(self, local_path: str) -> str:
        res = self._run(["install", "-r", "-g", local_path], timeout=600)
        out = (res.stdout + res.stderr).decode("utf-8", errors="replace")
        if "Success" not in out:
            raise AdbError(out.strip())
        return out.strip()

    def uninstall(self, package: str) -> None:
        out = self.shell_text(f"pm uninstall {package}")
        if "Success" not in out:
            raise AdbError(out.strip())

    # ------------------------------------------------------------- properties
    def getprop(self, prop: str) -> str:
        return self.shell_text(f"getprop {prop}")

    def screencap(self, local_path: str) -> None:
        data = self.exec_out("screencap -p", timeout=30)
        # некоторые процессы контейнера пишут предупреждения в stdout,
        # которые adb может подмешать в поток — обрезаем до сигнатуры PNG
        magic = data.find(b"\x89PNG")
        if magic < 0:
            raise AdbError("screencap: PNG не найден в выводе")
        with open(local_path, "wb") as f:
            f.write(data[magic:])

    def icmp_ok(self) -> bool:
        res = self.shell("ping -c 1 -W 2 8.8.8.8", timeout=15)
        return b"1 packets transmitted, 1 received" in res.stdout or b"1 received" in res.stdout
