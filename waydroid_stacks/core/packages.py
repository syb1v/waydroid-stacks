"""Каталог приложений: список, метки, иконки, ярлыки."""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import config
from .adb import Adb, AdbError

SYSTEM_SKIP = {
    "com.android.settings", "com.android.systemui", "com.android.shell",
    "com.android.providers.downloads", "com.android.providers.media",
    "com.waydroid.waydroid", "com.android.launcher3",
}


@dataclass
class AndroidApp:
    package: str
    label: str = ""
    activity: str = ""
    icon_path: Optional[str] = None
    system: bool = False

    @property
    def display_name(self) -> str:
        return self.label or self.package.rsplit(".", 1)[-1].capitalize()


class AppCatalog:
    """Список приложений Android с кэшированием иконок и названий."""

    def __init__(self, adb: Adb, waydroid=None):
        self.adb = adb
        self.waydroid = waydroid
        self._labels_file = config.CACHE_DIR / "labels.json"
        self._launchable: dict[str, str] = {}
        self._labels: dict[str, str] = {}
        self._icons: dict[str, str] = {}
        self._load_cache()

    # ------------------------------------------------------------------ cache
    def _load_cache(self) -> None:
        try:
            data = json.loads(self._labels_file.read_text(encoding="utf-8"))
            self._labels = data.get("labels", {})
            self._icons = data.get("icons", {})
        except (OSError, ValueError):
            pass

    def _save_cache(self) -> None:
        config.ensure_dirs()
        self._labels_file.write_text(
            json.dumps({"labels": self._labels, "icons": self._icons},
                       ensure_ascii=False, indent=1), encoding="utf-8")

    # ------------------------------------------------------------------- list
    def refresh(self, include_system: bool = False) -> list[AndroidApp]:
        self._launchable = self.adb.find_launchable()
        user_pkgs = set(self.adb.list_packages(user_only=True))
        apps: list[AndroidApp] = []
        for pkg, activity in self._launchable.items():
            is_system = pkg not in user_pkgs
            if is_system and not include_system:
                if pkg in SYSTEM_SKIP or pkg.startswith(("com.android.", "com.google.android.")):
                    continue
            apps.append(AndroidApp(
                package=pkg,
                label=self._labels.get(pkg, ""),
                activity=activity,
                icon_path=self._icons.get(pkg),
                system=is_system,
            ))
        apps.sort(key=lambda a: (a.display_name.lower()))
        return apps

    # ------------------------------------------------------------ label/icon
    def ensure_label_icon(self, package: str) -> tuple[str, Optional[str]]:
        if package in self._labels and package in self._icons and self._icons[package]:
            icon = self._icons[package]
            if isinstance(icon, str) and Path(icon).exists():
                return self._labels[package], icon

        label, icon_file = self._extract_from_device(package)
        if label:
            self._labels[package] = label
        if icon_file:
            self._icons[package] = icon_file
        self._save_cache()
        return self._labels.get(package, ""), self._icons.get(package)

    def _extract_from_device(self, package: str) -> tuple[str, Optional[str]]:
        apk_path = self.adb.package_apk_path(package)
        if not apk_path:
            return "", None

        label = ""
        icon_entry = ""
        try:
            manifest = self.adb.exec_out(f"unzip -p '{apk_path}' AndroidManifest.xml")
            arsc = self.adb.exec_out(f"unzip -p '{apk_path}' resources.arsc")
        except AdbError:
            return "", None

        if not manifest:
            return "", None

        with tempfile.TemporaryDirectory() as tmp:
            mini = Path(tmp) / "mini.zip"
            with zipfile.ZipFile(mini, "w", zipfile.ZIP_STORED) as z:
                z.writestr("AndroidManifest.xml", manifest)
                if arsc:
                    z.writestr("resources.arsc", arsc)
                z.writestr("resources.pb", b"")
            try:
                from pyaxmlparser import APK
                apk = APK(str(mini))
                label = apk.get_app_name() or ""
                icon_entry = apk.get_app_icon() or ""
            except Exception:
                label = label or ""

        icon_file: Optional[str] = None
        candidates: list[str] = []
        if icon_entry and icon_entry.lower().endswith((".png", ".webp", ".jpg")):
            candidates.append(icon_entry)
        # адаптивные иконки (xml) — ищем png внутри APK
        candidates += self._find_png_entries(apk_path, package)

        config.ensure_dirs()
        for entry in candidates:
            try:
                data = self.adb.exec_out(f"unzip -p '{apk_path}' '{entry}'")
            except AdbError:
                continue
            if not data or len(data) < 64:
                continue
            suffix = Path(entry).suffix.lower() or ".png"
            icon_file = str(config.ICON_CACHE_DIR / f"{package}{suffix}")
            Path(icon_file).write_bytes(data)
            break

        if not icon_file:
            icon_file = self._render_letter_icon(package, label)

        return label, icon_file

    def _render_letter_icon(self, package: str, label: str) -> Optional[str]:
        """Генерирует аватарку-заглушку (цветной круг с буквой) для адаптивных иконок."""
        try:
            import cairo
        except ImportError:
            return None

        size = 192
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
        cr = cairo.Context(surface)

        # цвет из хэша пакета (приятные пастельные тона)
        h = 0
        for ch in package:
            h = (h * 131 + ord(ch)) & 0xFFFFFFFF
        hue = (h % 360) / 360.0
        r, g, b = _hsv_to_rgb(hue, 0.45, 0.85)

        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.arc(size / 2, size / 2, size / 2, 0, 6.2832)
        cr.set_source_rgb(r, g, b)
        cr.fill()

        letter = (label or package.rsplit(".", 1)[-1] or "?")[0].upper()
        cr.set_source_rgb(1, 1, 1)
        cr.select_font_face("Sans", 1, 1)  # FontSlant.NORMAL, FontWeight.BOLD
        cr.set_font_size(size * 0.44)
        ext = cr.text_extents(letter)
        cr.move_to(size / 2 - (ext.width / 2 + ext.x_bearing),
                   size / 2 - (ext.height / 2 + ext.y_bearing))
        cr.show_text(letter)

        config.ensure_dirs()
        icon_file = str(config.ICON_CACHE_DIR / f"{package}.letter.png")
        surface.write_to_png(icon_file)
        return icon_file

    def _find_png_entries(self, apk_path: str, package: str) -> list[str]:
        try:
            listing = self.adb.shell_text(f"unzip -l '{apk_path}'")
        except AdbError:
            return []
        entries = []
        for line in listing.splitlines():
            m = re.search(r"(\S+ic_launcher\S*\.(?:png|webp))$", line.strip(), re.I)
            if m:
                entries.append(m.group(1))
        # xxxhdpi > xxhdpi > xhdpi > hdpi > mdpi
        def density_rank(path: str) -> int:
            for i, d in enumerate(("xxxhdpi", "xxhdpi", "xhdpi", "hdpi", "mdpi")):
                if d in path:
                    return i
            return 99
        entries.sort(key=density_rank)
        return entries[:3]

    # ------------------------------------------------------------ launch etc
    def launch(self, package: str) -> None:
        activity = self._launchable.get(package, "")
        if activity:
            self.adb.launch_app(package, activity)
        else:
            self.adb.launch_app(package)

    def stop(self, package: str) -> None:
        self.adb.stop_app(package)

    def uninstall(self, package: str) -> None:
        self.adb.uninstall(package)

    # ------------------------------------------------------------- shortcuts
    def create_desktop_shortcut(self, app: AndroidApp, target_dir: Optional[Path] = None) -> Path:
        """Создаёт .desktop ярлык на рабочем столе пользователя."""
        target_dir = target_dir or _desktop_dir()
        target_dir.mkdir(parents=True, exist_ok=True)
        launcher = shutil_which("waydroid-stacks") or "waydroid-stacks"
        icon = app.icon_path or "waydroid-stacks"
        content = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={app.display_name}\n"
            f"Comment=Android-приложение {app.package} (Waydroid Stacks)\n"
            f"Exec={launcher} --launch {app.package}\n"
            f"Icon={icon}\n"
            "Terminal=false\n"
            "Categories=Game;\n"
        )
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", app.package)
        path = target_dir / f"waydroid-{safe}.desktop"
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)
        return path


def shutil_which(name: str) -> Optional[str]:
    import shutil
    return shutil.which(name)


def _hsv_to_rgb(h: float, s: float, v: float) -> tuple[float, float, float]:
    i = int(h * 6)
    f = h * 6 - i
    p = v * (1 - s)
    q = v * (1 - f * s)
    t = v * (1 - (1 - f) * s)
    i %= 6
    return [
        (v, t, p), (q, v, p), (p, v, t),
        (p, q, v), (t, p, v), (v, p, q),
    ][i]


def _desktop_dir() -> Path:
    # XDG user dirs
    try:
        proc = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True, timeout=5)
        if proc.returncode == 0:
            p = proc.stdout.decode().strip()
            if p and p != str(Path.home()):
                return Path(p)
    except (OSError, subprocess.TimeoutExpired):
        pass
    for candidate in (Path.home() / "Desktop", Path.home() / "Рабочий стол"):
        if candidate.exists():
            return candidate
    return Path.home() / "Desktop"
