"""Управление Waydroid: статус, сессия, контейнер, props."""
from __future__ import annotations

import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class WaydroidStatus:
    session: str  # RUNNING / STOPPED
    container: str  # RUNNING / FROZEN / STOPPED
    vendor_type: str = ""
    ip: str = ""

    @property
    def session_running(self) -> bool:
        return self.session.upper() == "RUNNING"

    @property
    def container_running(self) -> bool:
        return self.container.upper() in ("RUNNING", "FROZEN")


class Waydroid:
    def __init__(self, binary: str | None = None):
        self.binary = binary or shutil.which("waydroid") or "waydroid"

    def status(self) -> WaydroidStatus:
        try:
            proc = subprocess.run([self.binary, "status"], capture_output=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            return WaydroidStatus("UNKNOWN", "UNKNOWN")
        out = proc.stdout.decode("utf-8", errors="replace")
        session = container = "STOPPED"
        vendor = ip = ""
        for line in out.splitlines():
            if line.startswith("Session:"):
                session = line.split(":", 1)[1].strip()
            elif line.startswith("Container:"):
                container = line.split(":", 1)[1].strip()
            elif line.startswith("Vendor type:"):
                vendor = line.split(":", 1)[1].strip()
            elif line.startswith("IP address:"):
                ip = line.split(":", 1)[1].strip()
        return WaydroidStatus(session, container, vendor, ip)

    def session_start(self) -> bool:
        """Запускает сессию в фоне (идемпотентно)."""
        st = self.status()
        if st.session_running:
            return True
        try:
            subprocess.Popen(
                ["setsid", self.binary, "session", "start"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True)
        except OSError:
            return False
        for _ in range(60):
            if self.status().session_running:
                return True
            time.sleep(1)
        return False

    def session_stop(self) -> bool:
        try:
            subprocess.run([self.binary, "session", "stop"], capture_output=True, timeout=30)
            return True
        except (OSError, subprocess.TimeoutExpired):
            return False

    def show_full_ui(self) -> None:
        try:
            subprocess.Popen(["setsid", self.binary, "show-full-ui"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        except OSError:
            pass

    def unfreeze(self) -> bool:
        """Размораживает контейнер (suspend_action=freeze замораживает его при
        остановке сессии, из-за чего adb начинает зависать)."""
        st = self.status()
        if not st.container_running:
            return False
        if st.container.upper() != "FROZEN":
            return True
        try:
            import dbus
            bus = dbus.SystemBus()
            obj = bus.get_object("id.waydro.Container", "/ContainerManager")
            iface = dbus.Interface(obj, "id.waydro.ContainerManager")
            iface.Unfreeze()
            for _ in range(10):
                time.sleep(0.5)
                if self.status().container.upper() == "RUNNING":
                    return True
            return True
        except Exception:  # noqa: BLE001
            # fallback: запуск любого app-запроса размораживает контейнер
            try:
                subprocess.run([self.binary, "app", "list"],
                               capture_output=True, timeout=20)
                return True
            except (OSError, subprocess.TimeoutExpired):
                return False

    def prop_get(self, key: str) -> str:
        try:
            proc = subprocess.run([self.binary, "prop", "get", key],
                                  capture_output=True, timeout=15)
            return proc.stdout.decode("utf-8", errors="replace").strip()
        except (OSError, subprocess.TimeoutExpired):
            return ""

    def prop_set(self, key: str, value: str) -> bool:
        try:
            proc = subprocess.run([self.binary, "prop", "set", key, value],
                                  capture_output=True, timeout=15)
            return proc.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def set_resolution(self, width: int, height: int) -> bool:
        ok1 = self.prop_set("persist.waydroid.width", str(width))
        ok2 = self.prop_set("persist.waydroid.height", str(height))
        return ok1 and ok2

    def get_resolution(self) -> tuple[int, int]:
        w = self.prop_get("persist.waydroid.width")
        h = self.prop_get("persist.waydroid.height")
        try:
            return int(w), int(h)
        except (TypeError, ValueError):
            return 0, 0

    def install_libndk_hint(self) -> str:
        """Проверяет наличие ARM-трансляции."""
        val = self.prop_get("ro.dalvik.vm.native.bridge")
        return val or "0"

    def check_service(self) -> str:
        try:
            proc = subprocess.run(["systemctl", "is-active", "waydroid-container"],
                                  capture_output=True, timeout=10)
            return proc.stdout.decode().strip()
        except (OSError, subprocess.TimeoutExpired):
            return "unknown"
