"""Страница настроек и обслуживания Waydroid."""
from __future__ import annotations

import subprocess
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk  # noqa: E402


class SettingsPage(Adw.Bin):
    def __init__(self, parent_window):
        super().__init__()
        self.parent_window = parent_window
        self.settings = parent_window.settings

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)

        title = Gtk.Label(label="Настройки", xalign=0)
        title.add_css_class("title-2")

        # --- статус
        self.status_group = Adw.PreferencesGroup(title="Состояние")
        self.status_row = Adw.ActionRow(title="Waydroid", subtitle="проверка...")
        self.status_group.add(self.status_row)

        check_btn = Gtk.Button(label="Проверить")
        check_btn.set_valign(Gtk.Align.CENTER)
        check_btn.connect("clicked", lambda *_: self.refresh_status())
        self.status_row.add_suffix(check_btn)

        # --- управление
        control_group = Adw.PreferencesGroup(title="Управление сессией")
        start_row = Adw.ActionRow(title="Запустить Android",
                                  subtitle="Старт сессии Waydroid и подключение adb")
        start_btn = Gtk.Button(label="Запустить")
        start_btn.set_valign(Gtk.Align.CENTER)
        start_btn.add_css_class("suggested-action")
        start_btn.connect("clicked", lambda *_: self._ensure())
        start_row.add_suffix(start_btn)

        stop_row = Adw.ActionRow(title="Остановить Android",
                                 subtitle="Остановить сессию (приложения перестанут работать)")
        stop_btn = Gtk.Button(label="Остановить")
        stop_btn.set_valign(Gtk.Align.CENTER)
        stop_btn.connect("clicked", lambda *_: self._stop_session())
        stop_row.add_suffix(stop_btn)

        ui_row = Adw.ActionRow(title="Полный интерфейс Android",
                               subtitle="Открыть системный лаунчер Waydroid")
        ui_btn = Gtk.Button(label="Открыть")
        ui_btn.set_valign(Gtk.Align.CENTER)
        ui_btn.connect("clicked", lambda *_: self.parent_window.waydroid.show_full_ui())
        ui_row.add_suffix(ui_btn)

        control_group.add(start_row)
        control_group.add(stop_row)
        control_group.add(ui_row)

        # --- встроенный стрим
        stream_group = Adw.PreferencesGroup(
            title="Встроенный игровой режим",
            description="Влияет на качество и плавность видеопотока в окне игры")

        self.max_size_row = Adw.ComboRow(
            title="Разрешение стрима",
            model=Gtk.StringList.new(["720p (960)", "HD (1280)", "Full HD (1920)", "Нативное"]))
        values = [960, 1280, 1920, 0]
        sizes = [960, 1280, 1920, 0]
        current = int(self.settings.get("max_size", 1280))
        self.max_size_row.set_selected(sizes.index(current) if current in sizes else 1)
        self.max_size_row.connect("notify::selected",
                                  lambda r, p: self._set_setting("max_size", values[r.get_selected()]))
        stream_group.add(self.max_size_row)

        self.fps_row = Adw.ComboRow(
            title="Ограничение FPS",
            model=Gtk.StringList.new(["30", "60", "120", "Без лимита"]))
        fps_values = [30, 60, 120, 0]
        current_fps = int(self.settings.get("max_fps", 60))
        self.fps_row.set_selected(fps_values.index(current_fps) if current_fps in fps_values else 1)
        self.fps_row.connect("notify::selected",
                             lambda r, p: self._set_setting("max_fps", fps_values[r.get_selected()]))
        stream_group.add(self.fps_row)

        # --- система
        sys_group = Adw.PreferencesGroup(title="Система")
        self.res_row = Adw.ActionRow(title="Разрешение Android", subtitle="...")
        sys_group.add(self.res_row)

        apps_row = Adw.ActionRow(title="Показывать системные приложения",
                                 subtitle="Отображать сервисы Android в библиотеке")
        switch = Gtk.Switch()
        switch.set_active(bool(self.settings.get("show_system_apps", False)))
        switch.set_valign(Gtk.Align.CENTER)
        switch.connect("notify::active",
                       lambda s, p: self._set_setting("show_system_apps", s.get_active()))
        apps_row.add_suffix(switch)
        sys_group.add(apps_row)

        ufw_row = Adw.ActionRow(title="Сетевые правила для Android",
                                subtitle="Разрешить интернет контейнеру (ufw)")
        ufw_btn = Gtk.Button(label="Применить")
        ufw_btn.set_valign(Gtk.Align.CENTER)
        ufw_btn.connect("clicked", lambda *_: self._fix_ufw())
        ufw_row.add_suffix(ufw_btn)
        sys_group.add(ufw_row)

        # --- расширения
        ext_group = Adw.PreferencesGroup(
            title="Расширения Android",
            description="ARM-трансляция (libndk) и сервисы Google (GApps)")

        self.libndk_row = Adw.ActionRow(title="ARM-трансляция (libndk)", subtitle="проверка...")
        libndk_btn = Gtk.Button(label="Установить")
        libndk_btn.set_valign(Gtk.Align.CENTER)
        libndk_btn.connect("clicked", lambda *_: self._open_waydroid_helper("libndk"))
        self.libndk_row.add_suffix(libndk_btn)
        ext_group.add(self.libndk_row)

        self.gapps_row = Adw.ActionRow(title="Google Play (GApps)", subtitle="проверка...")
        gapps_btn = Gtk.Button(label="Установить")
        gapps_btn.set_valign(Gtk.Align.CENTER)
        gapps_btn.connect("clicked", lambda *_: self._open_waydroid_helper("gapps"))
        self.gapps_row.add_suffix(gapps_btn)
        ext_group.add(self.gapps_row)

        hint = Gtk.Label(
            label="Для установки расширений используется приложение Waydroid Helper "
                  "(если установлено), иначе откроется подсказка.",
            xalign=0, wrap=True)
        hint.add_css_class("dim-label")
        ext_group.add(hint)

        box.append(title)
        box.append(self.status_group)
        box.append(control_group)
        box.append(stream_group)
        box.append(sys_group)
        box.append(ext_group)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_child(box)
        self.set_child(scrolled)

        self.refresh_status()

    # ------------------------------------------------------------------ status
    def refresh_status(self) -> None:
        def work():
            wd = self.parent_window.waydroid
            st = wd.status()
            service = wd.check_service()
            res = wd.get_resolution()
            bridge = wd.install_libndk_hint()
            gapps = ""
            try:
                self.parent_window.adb.connect()
                pkgs = self.parent_window.adb.list_packages(user_only=False)
                gapps = "установлены" if "com.android.vending" in pkgs else "не установлены"
            except Exception:  # noqa: BLE001
                gapps = "нет связи с Android"

            GLib.idle_add(self._apply_status, st.session, st.container, service,
                          res, bridge, gapps)

        threading.Thread(target=work, daemon=True).start()

    def _apply_status(self, session, container, service, res, bridge, gapps) -> None:
        self.status_row.set_subtitle(
            f"Сессия: {session} · Контейнер: {container} · Сервис: {service}")
        if res and res != (0, 0):
            self.res_row.set_subtitle(f"{res[0]}x{res[1]} (persist.waydroid)")
        else:
            self.res_row.set_subtitle("по умолчанию (1920x1080)")
        ndk_ok = bridge not in ("", "0")
        self.libndk_row.set_subtitle("активна" if ndk_ok else "не установлена")
        self.gapps_row.set_subtitle(gapps)

    # ---------------------------------------------------------------- actions
    def _ensure(self) -> None:
        self.parent_window.ensure_ready(callback=self.refresh_status)

    def _stop_session(self) -> None:
        def work():
            self.parent_window.waydroid.session_stop()
            GLib.idle_add(self.parent_window.toast, "Сессия остановлена")
            GLib.idle_add(self.refresh_status)
        threading.Thread(target=work, daemon=True).start()

    def _set_setting(self, key: str, value) -> None:
        self.settings[key] = value
        from ..core import config
        config.save_settings(self.settings)

    def _fix_ufw(self) -> None:
        script = (
            "ufw route allow in on waydroid0; "
            "ufw route allow out on waydroid0; "
            "ufw allow in on waydroid0 to any port 67 proto udp; "
            "ufw allow in on waydroid0 to any port 53; "
            "ufw reload"
        )
        try:
            subprocess.Popen(["pkexec", "bash", "-c", script])
            self.parent_window.toast("Запрошены права для настройки ufw")
        except OSError as exc:
            self.parent_window.toast(f"ufw: {exc}")

    def _open_waydroid_helper(self, what: str) -> None:
        import shutil
        if shutil.which("waydroid-helper"):
            subprocess.Popen(["waydroid-helper"])
            self.parent_window.toast("Открываю Waydroid Helper — установите расширение там")
        else:
            dialog = Adw.MessageDialog(
                transient_for=self.parent_window,
                heading="Установка расширений",
                body=(
                    "Установите Waydroid Helper (yay -S waydroid-helper) — в нём есть "
                    "установка libndk и GApps в один клик.\n\n"
                    "Либо установите вручную скриптом waydroid_script:\n"
                    "git clone https://github.com/casualsnek/waydroid_script\n"
                    "sudo venv/bin/python3 main.py install libndk"))
            dialog.add_response("ok", "Понятно")
            dialog.present()
