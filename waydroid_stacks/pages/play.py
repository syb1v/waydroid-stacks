"""Окно игры: встроенный видеопоток Android + инъекция ввода (кеймаппинг)."""
from __future__ import annotations

import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk, Gdk  # noqa: E402

from ..core.gamepad import InputMapper  # noqa: E402
from ..core.keymap import Profile  # noqa: E402
from ..core.scrcpy import ScrcpySession, ScrcpyError  # noqa: E402
from ..core.video import VideoStream  # noqa: E402


class PlayWindow(Adw.Window):
    """Игровое окно: стрим из Android + маппинг клавиатуры/мыши."""

    def __init__(self, parent_window, package: str, keymap: bool = True):
        super().__init__(transient_for=parent_window)
        self.parent_window = parent_window
        self.package = package
        self.use_keymap = keymap

        profile = parent_window.profiles.load(package) if keymap else Profile(package=package)
        self.profile = profile

        title = f"Игра: {package}"
        self.set_title(title)
        self.set_default_size(1100, 700)

        self.session: ScrcpySession | None = None
        self.mapper: InputMapper | None = None
        self.video = VideoStream()
        self._last_mouse = (0.0, 0.0)
        self._ptr_buttons = set()

        self._build_ui()
        self._start()

    # --------------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        self.overlay = Gtk.Overlay()
        self.overlay.set_child(self.video.picture)

        # маркеры раскладки поверх видео
        self.marker_area = Gtk.DrawingArea()
        self.marker_area.set_can_target(False)
        self.marker_area.set_draw_func(self._draw_markers)
        self.overlay.add_overlay(self.marker_area)

        # верхняя панель с кнопками управления
        self.toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.toolbar.add_css_class("osd")
        self.toolbar.set_halign(Gtk.Align.CENTER)
        self.toolbar.set_valign(Gtk.Align.START)
        self.toolbar.set_margin_top(10)

        def tool_button(icon: str, tooltip: str, cb) -> Gtk.Button:
            btn = Gtk.Button.new_from_icon_name(icon)
            btn.add_css_class("flat")
            btn.set_tooltip_text(tooltip)
            btn.connect("clicked", lambda *_: cb())
            return btn

        self.toolbar.append(tool_button("go-previous-symbolic", "Назад (Android Back)",
                                        lambda: self._key_event(4)))
        self.toolbar.append(tool_button("go-home-symbolic", "Домой",
                                        lambda: self._home()))
        self.toolbar.append(tool_button("view-grid-symbolic", "Недавние",
                                        lambda: self._key_event(187)))
        self.marker_toggle = Gtk.ToggleButton()
        self.marker_toggle.set_icon_name("input-keyboard-symbolic")
        self.marker_toggle.set_tooltip_text("Показывать раскладку (Tab)")
        self.marker_toggle.set_active(self.use_keymap)
        self.marker_toggle.connect("toggled", lambda *_: self.marker_area.queue_draw())
        self.toolbar.append(self.marker_toggle)
        self.toolbar.append(tool_button("view-fullscreen-symbolic", "Полный экран (F11)",
                                        self._toggle_fullscreen))
        self.toolbar.append(tool_button("window-close-symbolic", "Закрыть стрим",
                                        self.close))

        self.overlay.add_overlay(self.toolbar)

        self.status = Gtk.Label(label="Подключение...")
        self.status.add_css_class("osd")
        self.status.add_css_class("dim-label")
        self.status.set_halign(Gtk.Align.CENTER)
        self.status.set_valign(Gtk.Align.END)
        self.status.set_margin_bottom(12)
        self.overlay.add_overlay(self.status)

        # события клавиатуры
        key_ctl = Gtk.EventControllerKey()
        key_ctl.connect("key-pressed", self._on_key_pressed)
        key_ctl.connect("key-released", self._on_key_released)
        self.add_controller(key_ctl)

        # мышь
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_motion)
        self.video.picture.add_controller(motion)

        click = Gtk.GestureClick()
        click.set_button(0)  # все кнопки
        click.connect("pressed", self._on_click_pressed)
        click.connect("released", self._on_click_released)
        self.video.picture.add_controller(click)

        scroll = Gtk.EventControllerScroll()
        scroll.set_flags(Gtk.EventControllerScrollFlags.BOTH_AXES)
        scroll.connect("scroll", self._on_scroll)
        self.video.picture.add_controller(scroll)

        # 60 Гц тик маппера
        GLib.timeout_add(16, self._tick)

        self.set_content(self.overlay)

    # ------------------------------------------------------------------ start
    def _start(self) -> None:
        def work():
            import time as _time
            try:
                adb = self.parent_window.adb
                adb.connect()
                if not adb.wait_boot(60):
                    raise ScrcpyError("Android не загружен")
                parent = self.parent_window
                last_exc = None
                for attempt in range(3):
                    try:
                        self.session = ScrcpySession(
                            adb,
                            max_size=int(parent.settings.get("max_size", 0) or 0),
                            max_fps=int(parent.settings.get("max_fps", 0) or 0),
                        )
                        self.session.start(video=True, control=True)
                        last_exc = None
                        break
                    except ScrcpyError as exc:
                        last_exc = exc
                        _time.sleep(2)
                if last_exc:
                    raise last_exc
                self.mapper = InputMapper(self.session, self.profile)
                GLib.idle_add(self._on_ready)
            except Exception as exc:  # noqa: BLE001
                GLib.idle_add(self._on_error, str(exc))

        import threading
        threading.Thread(target=work, daemon=True).start()

    def _on_ready(self) -> None:
        self.video.attach(self.session)
        self.status.set_text("Кеймаппинг активен" if self.use_keymap else "Клики мыши — тапы")
        self.parent_window.register_play_window(self.package, self)

    def _on_error(self, message: str) -> None:
        self.status.set_text(f"Ошибка: {message}")
        self.parent_window.toast(f"Стрим: {message}")

    # ---------------------------------------------------------------- markers
    def _draw_markers(self, area, cr, width, height) -> None:
        if not (self.marker_toggle.get_active() and self.use_keymap):
            return
        if not self.profile.widgets:
            return
        vw, vh = self.session.video_size if self.session else (1920, 1080)
        scale = min(width / vw, height / vh) if vw and vh else 1.0
        dw, dh = vw * scale, vh * scale
        off_x, off_y = (width - dw) / 2, (height - dh) / 2

        colors = {
            "tap": (0.35, 0.75, 1.0, 0.35),
            "hold": (1.0, 0.65, 0.25, 0.35),
            "dpad": (0.45, 0.95, 0.55, 0.30),
            "aim": (0.8, 0.55, 1.0, 0.25),
            "swipe": (1.0, 0.45, 0.55, 0.35),
        }
        for widget in self.profile.widgets:
            cx = off_x + widget.x * dw
            cy = off_y + widget.y * dh
            r = max(18.0, widget.size * min(dw, dh))
            cr.set_source_rgba(*colors.get(widget.type, (1, 1, 1, 0.3)))
            cr.arc(cx, cy, r, 0, 6.2832)
            cr.fill()
            cr.set_source_rgba(1, 1, 1, 0.8)
            cr.set_line_width(2)
            cr.arc(cx, cy, r, 0, 6.2832)
            cr.stroke()

            cr.set_source_rgba(1, 1, 1, 0.95)
            cr.select_font_face("Sans", 1, 1)
            cr.set_font_size(max(12, r * 0.8))
            text = "WASD" if widget.type == "dpad" else (widget.key or widget.type)
            ext = cr.text_extents(text)
            cr.move_to(cx - ext.width / 2, cy + ext.height / 2)
            cr.show_text(text)

    # -------------------------------------------------------------- keyboard
    def _on_key_pressed(self, controller, keyval, keycode, state) -> bool:
        name = (Gdk.keyval_name(keyval) or "").lower()

        if name == "f11":
            self._toggle_fullscreen()
            return True
        if name == "tab":
            self.marker_toggle.set_active(not self.marker_toggle.get_active())
            return True
        if name == "escape":
            self.close()
            return True

        if self.use_keymap and self.mapper:
            self.mapper.key_press(name)
            return True  # не даём клавишам уходить в Android напрямую

        # без кеймаппинга — печатаем в Android
        if self.session:
            self._forward_key(name, down=True)
        return True

    def _on_key_released(self, controller, keyval, keycode, state) -> bool:
        name = (Gdk.keyval_name(keyval) or "").lower()
        if self.use_keymap and self.mapper:
            self.mapper.key_release(name)
            return True
        if self.session and not self.use_keymap:
            self._forward_key(name, down=False)
        return True

    def _forward_key(self, name: str, down: bool) -> None:
        from gi.repository import Gdk as _Gdk
        keymap = {
            "escape": 111, "backspace": 67, "return": 66, "enter": 66,
            "space": 62, "tab": 61, "up": 19, "down": 20, "left": 21, "right": 22,
            "delete": 112, "home": 122, "end": 123, "page_up": 92, "page_down": 93,
        }
        code = keymap.get(name)
        if not code and len(name) == 1:
            ch = name.upper()
            if "A" <= ch <= "Z":
                code = ord(ch) - ord("A") + 29
            elif "0" <= ch <= "9":
                code = ord(ch) - ord("0") + 7
        if code:
            self.session.key(0 if down else 1, code)

    # ----------------------------------------------------------------- mouse
    def _on_motion(self, controller, x, y) -> None:
        dx = x - self._last_mouse[0]
        dy = y - self._last_mouse[1]
        self._last_mouse = (x, y)
        if self.use_keymap and self.mapper and self._ptr_buttons:
            self.mapper.mouse_move(dx, dy)

    def _on_click_pressed(self, gesture, n_press, x, y) -> None:
        button = gesture.get_current_button()
        self._ptr_buttons.add(button)
        name = {1: "mouse1", 2: "mouse2", 3: "mouse3"}.get(button, "")
        if self.use_keymap and self.mapper:
            if not self.mapper.mouse_button(name, True):
                pass
            return
        # без кеймаппинга: прямой тап
        if self.session:
            self._tap_at(x, y)

    def _on_click_released(self, gesture, n_press, x, y) -> None:
        button = gesture.get_current_button()
        self._ptr_buttons.discard(button)
        name = {1: "mouse1", 2: "mouse2", 3: "mouse3"}.get(button, "")
        if self.use_keymap and self.mapper:
            self.mapper.mouse_button(name, False)

    def _tap_at(self, x, y) -> None:
        if not self.session:
            return
        alloc = self.video.picture.get_allocation()
        vw, vh = self.session.video_size
        scale = min(alloc.width / vw, alloc.height / vh) if vw and vh else 1.0
        dw, dh = vw * scale, vh * scale
        off_x, off_y = (alloc.width - dw) / 2, (alloc.height - dh) / 2
        nx = (x - off_x) / dw
        ny = (y - off_y) / dh
        if not (0 <= nx <= 1 and 0 <= ny <= 1):
            return
        pid = 100
        self.session.touch(0, int(nx * (vw - 1)), int(ny * (vh - 1)), pid)
        self.session.touch(1, int(nx * (vw - 1)), int(ny * (vh - 1)), pid)

    def _on_scroll(self, controller, dx, dy) -> bool:
        if self.session:
            x = int(self._last_mouse[0])
            y = int(self._last_mouse[1])
            self.session.scroll(x, y, dx, -dy)
        return True

    # --------------------------------------------------------------- helpers
    def _key_event(self, code: int) -> None:
        if self.session:
            self.session.key(0, code)
            self.session.key(1, code)

    def _home(self) -> None:
        if self.session:
            self._key_event(3)

    def _toggle_fullscreen(self) -> None:
        if self.is_fullscreen():
            self.unfullscreen()
        else:
            self.fullscreen()

    def _tick(self) -> bool:
        if self.mapper:
            self.mapper.tick()
        return True

    # ------------------------------------------------------------------ stop
    def close(self) -> None:  # type: ignore[override]
        if self.mapper:
            self.mapper.reset()
        if self.session:
            self.session.stop()
        self.video.stop()
        self.parent_window.unregister_play_window(self.package)
        super().close()
