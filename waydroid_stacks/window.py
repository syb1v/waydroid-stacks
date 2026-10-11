"""Главное окно приложения с боковой навигацией."""
from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk  # noqa: E402

from . import APP_NAME  # noqa: E402
from .core.adb import Adb, AdbError  # noqa: E402
from .core.packages import AppCatalog  # noqa: E402
from .core.waydroid import Waydroid  # noqa: E402
from .core.keymap import ProfileStore  # noqa: E402


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        settings = kwargs.pop("settings", None)
        super().__init__(**kwargs)
        self.settings = settings or {}
        self.set_title(APP_NAME)
        self.set_default_size(1180, 760)
        self.set_size_request(900, 560)

        self.waydroid = Waydroid()
        self.adb = Adb(serial=self.settings.get("adb_serial", "192.168.240.112:5555"))
        self.catalog = AppCatalog(self.adb, self.waydroid)
        self.profiles = ProfileStore()
        self._play_windows: dict[str, Gtk.Window] = {}

        self._build_ui()

    # -------------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        from .pages.library import LibraryPage
        from .pages.keymapper import KeymapperPage
        from .pages.settings import SettingsPage

        self.library_page = LibraryPage(self)
        self.keymapper_page = KeymapperPage(self)
        self.settings_page = SettingsPage(self)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)

        for name, title, icon, page in (
            ("library", "Мои игры", "applications-games-symbolic", self.library_page),
            ("keymap", "Клавиатура", "input-keyboard-symbolic", self.keymapper_page),
            ("settings", "Настройки", "emblem-system-symbolic", self.settings_page),
        ):
            page_holder = Adw.ToolbarView()
            header = Adw.HeaderBar()
            page_holder.add_top_bar(header)
            page_holder.set_content(page)
            self.stack.add_titled(page_holder, name, title)
            self.stack.get_page(page_holder).set_icon_name(icon)

        self.split_view = Adw.NavigationSplitView()
        self.split_view.set_show_content(True)

        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        sidebar_box.set_size_request(230, -1)

        sidebar_header = Adw.HeaderBar()
        sidebar_title = Adw.WindowTitle(title=APP_NAME, subtitle="BlueStacks-like для Waydroid")
        sidebar_header.set_title_widget(sidebar_title)

        self.nav_list = Gtk.ListBox()
        self.nav_list.add_css_class("navigation-sidebar")
        self.nav_list.set_selection_mode(Gtk.SelectionMode.SINGLE)

        self._nav_names: list[str] = []
        for name, title, icon in (
            ("library", "Мои игры", "applications-games-symbolic"),
            ("keymap", "Клавиатура", "input-keyboard-symbolic"),
            ("settings", "Настройки", "emblem-system-symbolic"),
        ):
            row = Gtk.ListBoxRow()
            row.set_activatable(True)
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            box.set_margin_top(8)
            box.set_margin_bottom(8)
            box.set_margin_start(12)
            box.set_margin_end(12)
            image = Gtk.Image.new_from_icon_name(icon)
            label = Gtk.Label(label=title, xalign=0)
            box.append(image)
            box.append(label)
            row.set_child(box)
            self.nav_list.append(row)
            self._nav_names.append(name)

        self.nav_list.connect("row-selected", self._on_nav_selected)
        self.nav_list.select_row(self.nav_list.get_row_at_index(0))

        sidebar_box.append(sidebar_header)
        sidebar_box.append(self.nav_list)

        sidebar_page = Adw.NavigationPage(child=sidebar_box, title="Навигация")
        content_page = Adw.NavigationPage(child=self.stack, title=APP_NAME)
        self.split_view.set_sidebar(sidebar_page)
        self.split_view.set_content(content_page)

        self.toast_overlay = Adw.ToastOverlay()
        self.toast_overlay.set_child(self.split_view)
        self.set_content(self.toast_overlay)

    def toast(self, message: str) -> None:
        self.toast_overlay.add_toast(Adw.Toast(title=message, timeout=4))

    def _on_nav_selected(self, _listbox, row) -> None:
        if row is None:
            return
        idx = row.get_index()
        if 0 <= idx < len(self._nav_names):
            self.stack.set_visible_child_name(self._nav_names[idx])

    # ------------------------------------------------------------ operations
    def ensure_ready(self, callback=None) -> None:
        """Запускает сессию Waydroid и adb-соединение в фоне."""
        def work():
            try:
                st = self.waydroid.status()
                if not st.session_running:
                    GLib.idle_add(self.toast, "Запускаю сессию Waydroid...")
                    self.waydroid.session_start()
                self.waydroid.unfreeze()
                self.adb.connect()
                if not self.adb.wait_boot(90):
                    raise AdbError("Android не загрузился за 90 секунд")
                if callback:
                    GLib.idle_add(callback)
            except AdbError as exc:
                GLib.idle_add(self.toast, str(exc))
            except Exception as exc:  # noqa: BLE001
                GLib.idle_add(self.toast, f"Ошибка: {exc}")

        threading.Thread(target=work, daemon=True).start()

    def launch_package(self, package: str, with_keymap: bool = True) -> None:
        def go():
            try:
                self.catalog.launch(package)
            except AdbError as exc:
                self.toast(f"Не удалось запустить: {exc}")
                return
            if with_keymap and self.profiles.exists(package):
                from .pages.play import PlayWindow
                win = PlayWindow(self, package, keymap=True)
                win.present()
            else:
                self.toast(f"Запускаю {package}...")

        self.ensure_ready(callback=go)

    def open_keymap_editor(self, package: str) -> None:
        from .pages.keymapper import KeymapEditorWindow
        editor = KeymapEditorWindow(self, package)
        editor.present()

    def register_play_window(self, package: str, win: Gtk.Window) -> None:
        self._play_windows[package] = win

    def unregister_play_window(self, package: str) -> None:
        self._play_windows.pop(package, None)

    def get_play_window(self, package: str):
        return self._play_windows.get(package)
