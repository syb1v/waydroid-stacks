"""GTK4/Adw-приложение Waydroid Stacks."""
from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from . import APP_ID, APP_NAME, __version__  # noqa: E402
from .core import config  # noqa: E402


def _load_css() -> None:
    from gi.repository import Gdk
    provider = Gtk.CssProvider()
    style = config.PROJECT_ROOT / "waydroid_stacks" / "style.css"
    if not style.exists():
        return
    provider.load_from_path(str(style))
    display = Gdk.Display.get_default()
    if display:
        Gtk.StyleContext.add_provider_for_display(
            display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


class WaydroidStacksApp(Adw.Application):
    def __init__(self, start_package: str = "", play_no_keymap: bool = False):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.settings = config.load_settings()
        self.start_package = start_package
        self.play_no_keymap = play_no_keymap
        self.connect("shutdown", self._on_shutdown)

    def do_activate(self) -> None:  # noqa: N802
        _load_css()
        if self.settings.get("theme") == "dark":
            Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.PREFER_DARK)
        win = self.get_active_window()
        if not win:
            from .window import MainWindow
            win = MainWindow(application=self, settings=self.settings)
        win.present()

        if self.start_package:
            pkg = self.start_package
            self.start_package = ""
            GLib.idle_add(win.launch_package, pkg, not self.play_no_keymap)

    def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:  # noqa: N802
        args = command_line.get_arguments()[1:]
        pkg = ""
        no_keymap = False
        i = 0
        while i < len(args):
            a = args[i]
            if a == "--launch" and i + 1 < len(args):
                pkg = args[i + 1]
                i += 2
            elif a == "--play" and i + 1 < len(args):
                pkg = args[i + 1]
                no_keymap = True
                i += 2
            elif a in ("-v", "--version"):
                print(f"{APP_NAME} {__version__}")
                return 0
            elif a in ("-h", "--help"):
                print(f"{APP_NAME}: --launch <package> — запустить приложение "
                      f"с кеймаппингом, --play <package> — без кеймаппинга")
                return 0
            else:
                i += 1
        self.start_package = pkg
        self.play_no_keymap = no_keymap
        self.activate()
        return 0

    def _on_shutdown(self, _app) -> None:
        config.save_settings(self.settings)


def run(argv: list[str] | None = None) -> int:
    config.ensure_dirs()
    app = WaydroidStacksApp()
    return app.run(argv if argv is not None else sys.argv)
