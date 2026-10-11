"""Окно игры: встроенный видеопоток Android + инъекция ввода (кеймаппинг)."""
from __future__ import annotations

import threading
import time
from datetime import datetime

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk, Gdk  # noqa: E402

from ..core import config  # noqa: E402
from ..core.gamepad import InputMapper  # noqa: E402
from ..core.gamepad_device import GamepadManager, HAS_EVDEV  # noqa: E402
from ..core.keymap import Profile  # noqa: E402
from ..core.nativeinput import WaydroidNativeInput  # noqa: E402
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
        self.native_input: WaydroidNativeInput | None = None
        self.mapper: InputMapper | None = None
        self.video = VideoStream()
        self.gamepad: GamepadManager | None = None
        self._last_mouse = (0.0, 0.0)
        self._ptr_buttons = set()
        self._starting = False
        self._stayon_prev: str | None = None
        self._last_freeze_check = 0.0

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

        self.shot_btn = tool_button("camera-photo-symbolic",
                                    "Скриншот (F8)", self.take_screenshot)
        self.toolbar.append(self.shot_btn)

        self.record_btn = Gtk.ToggleButton()
        self.record_btn.set_icon_name("media-record-symbolic")
        self.record_btn.set_tooltip_text("Запись геймплея (F9)")
        self.record_btn.add_css_class("flat")
        self.record_btn.connect("toggled", self._on_record_toggled)
        self.toolbar.append(self.record_btn)

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

        # кнопка переподключения (появляется при ошибке)
        self.reconnect_btn = Gtk.Button(label="Переподключить")
        self.reconnect_btn.add_css_class("suggested-action")
        self.reconnect_btn.set_halign(Gtk.Align.CENTER)
        self.reconnect_btn.set_valign(Gtk.Align.CENTER)
        self.reconnect_btn.set_visible(False)
        self.reconnect_btn.connect("clicked", lambda *_: self._restart_stream())
        self.overlay.add_overlay(self.reconnect_btn)

        # индикатор записи
        self.rec_indicator = Gtk.Label(label="● REC")
        self.rec_indicator.add_css_class("osd")
        self.rec_indicator.set_halign(Gtk.Align.END)
        self.rec_indicator.set_valign(Gtk.Align.START)
        self.rec_indicator.set_margin_top(14)
        self.rec_indicator.set_margin_end(14)
        self.rec_indicator.set_visible(False)
        self.overlay.add_overlay(self.rec_indicator)

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
    def _input(self):
        """Активный бэкенд ввода: нативный FIFO, иначе control-сокет scrcpy."""
        if self.native_input and self.native_input.available:
            return self.native_input
        return self.session

    def _start(self) -> None:
        if self._starting:
            return
        self._starting = True

        def work():
            import time as _time
            try:
                adb = self.parent_window.adb
                self.parent_window.waydroid.unfreeze()
                adb.connect()
                if not adb.wait_boot(60):
                    raise ScrcpyError("Android не загружен")
                parent = self.parent_window
                # не даём Android уснуть: засыпание вызывает HAL suspend →
                # контейнер замораживается (suspend_action=freeze)
                try:
                    self._stayon_prev = adb.shell_text(
                        "settings get global stay_on_while_plugged_in",
                        timeout=10).strip()
                    adb.shell(
                        "settings put global stay_on_while_plugged_in 7",
                        timeout=10)
                except Exception:  # noqa: BLE001
                    self._stayon_prev = None
                # приоритет: настройки профиля игры, затем глобальные
                # (0 = взять глобальные, -1 = без ограничения)
                psize = int(self.profile.stream_max_size or 0)
                if psize < 0:
                    max_size = 0
                elif psize > 0:
                    max_size = psize
                else:
                    max_size = int(parent.settings.get("max_size", 0) or 0)

                pfps = int(self.profile.stream_max_fps or 0)
                if pfps < 0:
                    max_fps = 0
                elif pfps > 0:
                    max_fps = pfps
                else:
                    max_fps = int(parent.settings.get("max_fps", 0) or 0)
                last_exc = None
                for attempt in range(3):
                    try:
                        self.session = ScrcpySession(
                            adb, max_size=max_size, max_fps=max_fps)
                        self.session.start(video=True, control=True)
                        last_exc = None
                        break
                    except ScrcpyError as exc:
                        last_exc = exc
                        _time.sleep(2)
                if last_exc:
                    raise last_exc
                # нативный ввод (evdev-FIFO → EventHub) без control-сокета;
                # при недоступности — прозрачный откат на scrcpy-control
                try:
                    native = WaydroidNativeInput(adb)
                    if native.start():
                        self.native_input = native
                    else:
                        native.stop()
                except Exception:  # noqa: BLE001
                    self.native_input = None
                self.mapper = InputMapper(self._input(), self.profile)
                GLib.idle_add(self._on_ready)
            except Exception as exc:  # noqa: BLE001
                GLib.idle_add(self._on_error, str(exc))

        import threading
        threading.Thread(target=work, daemon=True).start()

    def _restart_stream(self) -> None:
        """Переподключение стрима одной кнопкой."""
        self.reconnect_btn.set_visible(False)
        self.status.set_text("Переподключение...")
        if self.mapper:
            self.mapper.reset()
        if self.native_input:
            self.native_input.stop()
            self.native_input = None
        if self.session:
            self.session.stop()
            self.session = None
        self.video.stop()
        self._starting = False
        self._start()

    def _on_ready(self) -> None:
        self._starting = False
        self.video.attach(self.session)
        if self.use_keymap:
            backend = "нативный ввод (evdev-FIFO)" if self.native_input \
                else "ввод через scrcpy"
            status = f"Кеймаппинг активен · {backend}"
        else:
            status = "Клики мыши — тапы"
        if self.gamepad and self.gamepad.connected:
            status += f" · геймпад: {self.gamepad.connected[0]}"
        self.status.set_text(status)
        self.parent_window.register_play_window(self.package, self)
        self._start_gamepad()

    def _on_error(self, message: str) -> None:
        self._starting = False
        self.status.set_text(f"Ошибка: {message}")
        self.reconnect_btn.set_visible(True)
        self.parent_window.toast(f"Стрим: {message}")

    # ---------------------------------------------------------------- gamepad
    def _start_gamepad(self) -> None:
        if not self.use_keymap or not HAS_EVDEV or self.gamepad:
            return

        def on_pad_key(name: str, pressed: bool) -> None:
            if self.mapper:
                if pressed:
                    self.mapper.key_press(name)
                else:
                    self.mapper.key_release(name)

        self.gamepad = GamepadManager(on_pad_key)
        self.gamepad.start()
        if self.gamepad.connected:
            self.parent_window.toast(f"Геймпад: {self.gamepad.connected[0]}")

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
        if name == "f8":
            self.take_screenshot()
            return True
        if name == "f9":
            self.record_btn.set_active(not self.record_btn.get_active())
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
            self._input().key(0 if down else 1, code)

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

    def _normalized(self, x, y) -> tuple[float, float] | None:
        """Координаты виджета видео → нормализованные (0..1)."""
        if not self.session:
            return None
        alloc = self.video.picture.get_allocation()
        vw, vh = self.session.video_size
        scale = min(alloc.width / vw, alloc.height / vh) if vw and vh else 1.0
        dw, dh = vw * scale, vh * scale
        off_x, off_y = (alloc.width - dw) / 2, (alloc.height - dh) / 2
        nx = (x - off_x) / dw
        ny = (y - off_y) / dh
        if not (0 <= nx <= 1 and 0 <= ny <= 1):
            return None
        return nx, ny

    def _tap_at(self, x, y) -> None:
        nxny = self._normalized(x, y)
        if not nxny:
            return
        nx, ny = nxny
        backend = self._input()
        iw, ih = backend.input_size
        pid = 100
        backend.touch(0, int(nx * (iw - 1)), int(ny * (ih - 1)), pid)
        backend.touch(1, int(nx * (iw - 1)), int(ny * (ih - 1)), pid)

    def _on_scroll(self, controller, dx, dy) -> bool:
        nxny = self._normalized(*self._last_mouse)
        if nxny:
            backend = self._input()
            iw, ih = backend.input_size
            backend.scroll(int(nxny[0] * (iw - 1)), int(nxny[1] * (ih - 1)),
                           dx, -dy)
        return True

    # --------------------------------------------------------------- helpers
    def _key_event(self, code: int) -> None:
        backend = self._input()
        if backend:
            backend.key(0, code)
            backend.key(1, code)

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
        now = time.monotonic()
        if now - self._last_freeze_check >= 5.0:
            self._last_freeze_check = now
            self._check_frozen()
        return True

    def _check_frozen(self) -> None:
        """Watchdog: если Android всё же уснул и контейнер заморожен —
        размораживаем, чтобы ввод продолжал работать."""
        def work():
            try:
                st = self.parent_window.waydroid.status()
                if st.container.upper() == "FROZEN":
                    self.parent_window.waydroid.unfreeze()
                    adb = self.parent_window.adb
                    adb.connect()
                    if self.native_input:
                        self.native_input.reensure()
                    GLib.idle_add(self.parent_window.toast,
                                  "Контейнер разморожен")
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------- capture
    def take_screenshot(self) -> None:
        """F8: сохраняет текущий кадр стрима в папку изображений."""
        if not self.session:
            self.parent_window.toast("Стрим не запущен")
            return
        try:
            folder = config.pictures_dir() / "Waydroid Stacks"
            folder.mkdir(parents=True, exist_ok=True)
            name = f"{self.package.replace('.', '_')}-{datetime.now():%Y%m%d-%H%M%S}.png"
            target = folder / name
        except OSError as exc:
            self.parent_window.toast(f"Скриншот: {exc}")
            return

        def work():
            try:
                self.parent_window.adb.screencap(str(target))
                GLib.idle_add(self.parent_window.toast, f"Скриншот: {target.name}")
            except Exception as exc:  # noqa: BLE001
                GLib.idle_add(self.parent_window.toast, f"Скриншот: {exc}")

        import threading
        threading.Thread(target=work, daemon=True).start()

    def _on_record_toggled(self, btn) -> None:
        """F9: запись/остановка записи геймплея в MP4."""
        if btn.get_active():
            folder = config.videos_dir() / "Waydroid Stacks"
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                btn.set_active(False)
                self.parent_window.toast(f"Запись: {exc}")
                return
            name = f"{self.package.replace('.', '_')}-{datetime.now():%Y%m%d-%H%M%S}.mp4"
            target = folder / name
            if self.video.start_recording(target):
                self.rec_indicator.set_visible(True)
                self.parent_window.toast(f"Запись: {name}")
            else:
                btn.set_active(False)
                self.parent_window.toast("Запись недоступна (нет видеопотока)")
        else:
            path = self.video.stop_recording()
            self.rec_indicator.set_visible(False)
            if path:
                self.parent_window.toast(f"Запись сохранена: {path.name}")

    # ------------------------------------------------------------------ stop
    def close(self) -> None:  # type: ignore[override]
        if self.gamepad:
            self.gamepad.stop()
            self.gamepad = None
        if self.mapper:
            self.mapper.reset()
        if self.native_input:
            self.native_input.stop()
            self.native_input = None
        if self.session:
            self.session.stop()
        if self._stayon_prev is not None:
            def restore():
                try:
                    self.parent_window.adb.shell(
                        f"settings put global stay_on_while_plugged_in "
                        f"{self._stayon_prev}", timeout=10)
                except Exception:  # noqa: BLE001
                    pass
            threading.Thread(target=restore, daemon=True).start()
        self.video.stop(wait=True)
        self.parent_window.unregister_play_window(self.package)
        super().close()
