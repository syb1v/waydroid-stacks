"""Страница «Мои игры» — библиотека Android-приложений."""
from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk, Gio, Gdk  # noqa: E402

from ..core.packages import AndroidApp  # noqa: E402


class AppTile(Gtk.FlowBoxChild):
    def __init__(self, app: AndroidApp, page: "LibraryPage"):
        super().__init__()
        self.app = app
        self.page = page

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_size_request(150, 160)
        box.set_valign(Gtk.Align.CENTER)
        box.add_css_class("app-tile")

        self.icon = Gtk.Image()
        self.icon.set_pixel_size(96)
        if app.icon_path:
            try:
                texture = Gdk.Texture.new_from_filename(app.icon_path)
                self.icon.set_from_paintable(texture)
            except GLib.Error:
                self.icon.set_from_icon_name("application-x-executable")
        else:
            self.icon.set_from_icon_name("application-x-executable")
        self.icon.set_margin_top(8)

        self.label = Gtk.Label(label=app.display_name, wrap=True,
                               justify=Gtk.Justification.CENTER, lines=2,
                               ellipsize=3)
        self.label.set_max_width_chars(18)
        self.label.add_css_class("app-label")

        box.append(self.icon)
        box.append(self.label)
        self.set_child(box)
        self.set_tooltip_text(app.package)

        # контекстное меню
        gesture = Gtk.GestureClick(button=3)
        gesture.connect("pressed", self._on_right_click)
        self.add_controller(gesture)

        gesture_left = Gtk.GestureClick(button=1)
        gesture_left.connect("released", self._on_left_click)
        self.add_controller(gesture_left)

        box.set_cursor(Gdk.Cursor.new_from_name("pointer"))

    def _on_left_click(self, gesture, n_press, x, y) -> None:
        if n_press >= 1:
            self.page.parent_window.launch_package(self.app.package,
                                                   with_keymap=False)

    def _on_right_click(self, gesture, n_press, x, y) -> None:
        menu = Gio.Menu()
        menu.append("Запустить (окно)", f"tile.launch_window")
        menu.append("Играть с кеймаппингом", f"tile.launch_keymap")
        menu.append("Редактировать клавиши", f"tile.edit_keymap")
        menu.append("Создать ярлык на рабочем столе", f"tile.shortcut")
        menu.append("Остановить", f"tile.stop")
        menu.append("Удалить", f"tile.uninstall")

        action_group = Gio.SimpleActionGroup()
        actions = {
            "launch_window": lambda: self.page.parent_window.launch_package(
                self.app.package, with_keymap=False),
            "launch_keymap": lambda: self.page.parent_window.launch_package(
                self.app.package, with_keymap=True),
            "edit_keymap": lambda: self.page.parent_window.open_keymap_editor(
                self.app.package),
            "shortcut": lambda: self._make_shortcut(),
            "stop": lambda: self.app_stop(),
            "uninstall": lambda: self._confirm_uninstall(),
        }
        for name, cb in actions.items():
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", lambda _a, _p, cb=cb: cb())
            action_group.add_action(act)
        self.insert_action_group("tile", action_group)

        popover = Gtk.PopoverMenu.new_from_model(menu)
        popover.set_parent(self)
        popover.set_has_arrow(False)
        popover.popup()

    def app_stop(self) -> None:
        def work():
            try:
                self.page.parent_window.catalog.stop(self.app.package)
                GLib.idle_add(self.page.parent_window.toast, f"{self.app.display_name} остановлено")
            except Exception as exc:  # noqa: BLE001
                GLib.idle_add(self.page.parent_window.toast, str(exc))
        threading.Thread(target=work, daemon=True).start()

    def _make_shortcut(self) -> None:
        try:
            path = self.page.catalog.create_desktop_shortcut(self.app)
            self.page.parent_window.toast(f"Ярлык создан: {path.name}")
        except OSError as exc:
            self.page.parent_window.toast(f"Ошибка ярлыка: {exc}")

    def _confirm_uninstall(self) -> None:
        dialog = Adw.MessageDialog(
            transient_for=self.page.parent_window,
            heading="Удалить приложение?",
            body=f"{self.app.display_name} ({self.app.package}) будет удалено из Android.",
        )
        dialog.add_response("cancel", "Отмена")
        dialog.add_response("delete", "Удалить")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)

        def on_response(dlg, response):
            if response != "delete":
                return
            def work():
                try:
                    self.page.catalog.uninstall(self.app.package)
                    GLib.idle_add(self.page.reload)
                except Exception as exc:  # noqa: BLE001
                    GLib.idle_add(self.page.parent_window.toast, str(exc))
            threading.Thread(target=work, daemon=True).start()

        dialog.connect("response", on_response)
        dialog.present()


class LibraryPage(Adw.Bin):
    def __init__(self, parent_window):
        super().__init__()
        self.parent_window = parent_window
        self.catalog = parent_window.catalog
        self._apps: list[AndroidApp] = []
        self._loading = False

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)

        # верхняя панель
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        self.search = Gtk.SearchEntry()
        self.search.set_hexpand(True)
        self.search.set_placeholder_text("Поиск приложений...")
        self.search.connect("search-changed", lambda *_: self._filter())

        refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh_btn.set_tooltip_text("Обновить список")
        refresh_btn.connect("clicked", lambda *_: self.reload())

        install_btn = Gtk.Button(label="Установить APK")
        install_btn.connect("clicked", lambda *_: self._install_apk())

        manage_btn = Gtk.Button(label="Открыть Android")
        manage_btn.set_tooltip_text("Открыть полный интерфейс Waydroid")
        manage_btn.connect("clicked", lambda *_: self.parent_window.waydroid.show_full_ui())

        top.append(self.search)
        top.append(install_btn)
        top.append(manage_btn)
        top.append(refresh_btn)

        self.status_label = Gtk.Label(label="Загрузка...", xalign=0)
        self.status_label.add_css_class("dim-label")

        self.flowbox = Gtk.FlowBox()
        self.flowbox.set_valign(Gtk.Align.START)
        self.flowbox.set_max_children_per_line(12)
        self.flowbox.set_min_children_per_line(3)
        self.flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.flowbox.set_homogeneous(True)
        self.flowbox.set_margin_top(6)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_child(self.flowbox)

        self.spinner = Gtk.Spinner()
        loading_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        loading_box.append(self.spinner)
        loading_box.append(self.status_label)

        box.append(top)
        box.append(loading_box)
        box.append(scrolled)
        self.set_child(box)

        self.reload()

    # ------------------------------------------------------------------ load
    def reload(self) -> None:
        if self._loading:
            return
        self._loading = True
        self.spinner.start()
        self.status_label.set_text("Подключаюсь к Android...")

        def work():
            try:
                self.parent_window.adb.connect()
                if not self.parent_window.adb.is_online():
                    GLib.idle_add(self._show_offline)
                    return
                self.parent_window.adb.wait_boot(60)
                apps = self.catalog.refresh(
                    include_system=self.parent_window.settings.get("show_system_apps", False))
                GLib.idle_add(self._populate, apps)
            except Exception as exc:  # noqa: BLE001
                GLib.idle_add(self._show_error, str(exc))

        threading.Thread(target=work, daemon=True).start()

    def _show_offline(self) -> None:
        self._loading = False
        self.spinner.stop()
        self.status_label.set_text("Android не запущен. Нажмите «Обновить» для запуска.")
        self.parent_window.ensure_ready(callback=self.reload)

    def _show_error(self, message: str) -> None:
        self._loading = False
        self.spinner.stop()
        self.status_label.set_text(f"Ошибка: {message}")

    def _populate(self, apps: list[AndroidApp]) -> None:
        self._loading = False
        self.spinner.stop()
        self._apps = apps
        self.status_label.set_text(f"Приложений: {len(apps)}. Иконки загружаются...")
        self._filter()
        self._load_icons_async()

    def _load_icons_async(self) -> None:
        def work():
            pending = [a for a in self._apps if not a.icon_path or a.label == ""]
            for app in pending:
                try:
                    label, icon = self.catalog.ensure_label_icon(app.package)
                    app.label = label or app.label
                    app.icon_path = icon or app.icon_path
                    GLib.idle_add(self._filter)
                except Exception:  # noqa: BLE001
                    continue
            GLib.idle_add(self.status_label.set_text, f"Приложений: {len(self._apps)}")

        threading.Thread(target=work, daemon=True).start()

    def _filter(self) -> None:
        query = self.search.get_text().strip().lower()

        child = self.flowbox.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.flowbox.remove(child)
            child = nxt

        shown = 0
        for app in self._apps:
            if query and query not in app.display_name.lower() \
                    and query not in app.package.lower():
                continue
            self.flowbox.append(AppTile(app, self))
            shown += 1

        if not self._loading:
            self.status_label.set_text(
                f"Приложений: {shown}" +
                (f" из {len(self._apps)}" if shown != len(self._apps) else ""))

    # ---------------------------------------------------------------- install
    def _install_apk(self) -> None:
        dialog = Gtk.FileDialog()
        dialog.set_title("Выберите APK-файл")

        def on_finish(dlg, result):
            try:
                file = dlg.open_finish(result)
            except GLib.Error:
                return
            path = file.get_path()

            def work():
                try:
                    GLib.idle_add(self.parent_window.toast, "Устанавливаю APK...")
                    self.parent_window.adb.install_apk(path)
                    GLib.idle_add(self.parent_window.toast, "APK установлен")
                    GLib.idle_add(self.reload)
                except Exception as exc:  # noqa: BLE001
                    GLib.idle_add(self.parent_window.toast, f"Ошибка установки: {exc}")

            def ready():
                threading.Thread(target=work, daemon=True).start()

            self.parent_window.ensure_ready(callback=ready)

        dialog.open(self.parent_window, None, on_finish)
