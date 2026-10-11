"""Страница «Клавиатура» и визуальный редактор раскладки."""
from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk, Gdk, Gio  # noqa: E402

from ..core.keymap import (Profile, Widget, ProfileStore, W_TAP, W_HOLD,  # noqa: E402
                           W_DPAD, W_AIM, W_SWIPE)

WIDGET_TITLES = {
    W_TAP: "Тап",
    W_HOLD: "Удержание",
    W_DPAD: "Джойстик",
    W_AIM: "Обзор (мышь)",
    W_SWIPE: "Свайп",
}


class KeymapperPage(Adw.Bin):
    """Список профилей кеймаппинга."""

    def __init__(self, parent_window):
        super().__init__()
        self.parent_window = parent_window
        self.catalog = parent_window.catalog
        self.profiles = parent_window.profiles

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)

        title = Gtk.Label(label="Профили кеймаппинга", xalign=0)
        title.add_css_class("title-2")

        desc = Gtk.Label(
            label="Профиль привязывается к приложению. В режиме игры клавиши "
                  "клавиатуры и мышь превращаются в касания на экране Android.",
            xalign=0, wrap=True)
        desc.add_css_class("dim-label")

        self.listbox = Gtk.ListBox()
        self.listbox.add_css_class("boxed-list")
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)

        new_btn = Gtk.Button(label="Создать профиль")
        new_btn.set_halign(Gtk.Align.START)
        new_btn.connect("clicked", lambda *_: self._new_profile())

        import_btn = Gtk.Button(label="Импорт .wsk")
        import_btn.set_halign(Gtk.Align.START)
        import_btn.set_tooltip_text("Импортировать раскладку из файла .wsk")
        import_btn.connect("clicked", lambda *_: self._import_wsk())

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_row.append(new_btn)
        btn_row.append(import_btn)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_child(self.listbox)

        box.append(title)
        box.append(desc)
        box.append(btn_row)
        box.append(scrolled)
        self.set_child(box)

        self.refresh()

    def refresh(self) -> None:
        child = self.listbox.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.listbox.remove(child)
            child = nxt

        packages = self.profiles.list_packages()
        if not packages:
            row = Adw.ActionRow(title="Профилей пока нет",
                                subtitle="Нажмите «Создать профиль», чтобы назначить клавиши")
            self.listbox.append(row)
            return

        for pkg in packages:
            profile = self.profiles.load(pkg)
            row = Adw.ActionRow(
                title=pkg,
                subtitle=f"Виджетов: {len(profile.widgets)}")
            edit_btn = Gtk.Button.new_from_icon_name("document-edit-symbolic")
            edit_btn.add_css_class("flat")
            edit_btn.set_valign(Gtk.Align.CENTER)
            edit_btn.set_tooltip_text("Редактировать")
            edit_btn.connect("clicked", lambda _b, p=pkg: self.parent_window.open_keymap_editor(p))

            play_btn = Gtk.Button.new_from_icon_name("media-playback-start-symbolic")
            play_btn.add_css_class("flat")
            play_btn.set_valign(Gtk.Align.CENTER)
            play_btn.set_tooltip_text("Запустить с кеймаппингом")
            play_btn.connect("clicked", lambda _b, p=pkg: self.parent_window.launch_package(
                p, with_keymap=True))

            export_btn = Gtk.Button.new_from_icon_name("document-save-symbolic")
            export_btn.add_css_class("flat")
            export_btn.set_valign(Gtk.Align.CENTER)
            export_btn.set_tooltip_text("Экспорт раскладки (.wsk)")
            export_btn.connect("clicked", lambda _b, p=pkg: self._export_wsk(p))

            del_btn = Gtk.Button.new_from_icon_name("user-trash-symbolic")
            del_btn.add_css_class("flat")
            del_btn.set_valign(Gtk.Align.CENTER)
            del_btn.set_tooltip_text("Удалить профиль")
            del_btn.connect("clicked", lambda _b, p=pkg: self._delete(p))

            row.add_suffix(edit_btn)
            row.add_suffix(play_btn)
            row.add_suffix(export_btn)
            row.add_suffix(del_btn)
            self.listbox.append(row)

    # --------------------------------------------------------- export/import
    def _export_wsk(self, package: str) -> None:
        dialog = Gtk.FileDialog()
        dialog.set_title("Экспорт раскладки")
        dialog.set_initial_name(f"{package}.wsk")

        def on_finish(dlg, result):
            try:
                file = dlg.save_finish(result)
            except GLib.Error:
                return
            path = file.get_path()
            if not path:
                return
            try:
                target = self.profiles.export_wsk(
                    package, __import__("pathlib").Path(path))
                self.parent_window.toast(f"Экспортировано: {target.name}")
            except Exception as exc:  # noqa: BLE001
                self.parent_window.toast(f"Экспорт: {exc}")

        dialog.save(self.parent_window, None, on_finish)

    def _import_wsk(self) -> None:
        dialog = Gtk.FileDialog()
        dialog.set_title("Импорт раскладки (.wsk)")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filter_wsk = Gtk.FileFilter()
        filter_wsk.set_name("Раскладки Waydroid Stacks (*.wsk)")
        filter_wsk.add_pattern("*.wsk")
        filters.append(filter_wsk)
        dialog.set_filters(filters)

        def on_finish(dlg, result):
            try:
                file = dlg.open_finish(result)
            except GLib.Error:
                return
            path = file.get_path()
            if not path:
                return
            try:
                profile = self.profiles.import_wsk(__import__("pathlib").Path(path))
                self.refresh()
                self.parent_window.toast(
                    f"Импортирована раскладка: {profile.package}")
            except Exception as exc:  # noqa: BLE001
                self.parent_window.toast(f"Импорт: {exc}")

        dialog.open(self.parent_window, None, on_finish)

    def _delete(self, package: str) -> None:
        self.profiles.delete(package)
        self.refresh()

    def _new_profile(self) -> None:
        """Выбор приложения для нового профиля."""
        dialog = Adw.MessageDialog(
            transient_for=self.parent_window,
            heading="Новый профиль",
            body="Введите имя пакета Android, например com.launcher.brgame",
        )
        entry = Gtk.Entry()
        entry.set_placeholder_text("com.example.game")
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", "Отмена")
        dialog.add_response("create", "Создать")
        dialog.set_response_appearance("create", Adw.ResponseAppearance.SUGGESTED)

        def on_response(dlg, response):
            if response == "create":
                pkg = entry.get_text().strip()
                if pkg:
                    self.profiles.save(Profile(package=pkg))
                    self.refresh()
                    self.parent_window.open_keymap_editor(pkg)

        dialog.connect("response", on_response)
        dialog.present()


class KeymapEditorWindow(Adw.Window):
    """Визуальный редактор: фон-скриншот + перетаскиваемые виджеты."""

    def __init__(self, parent_window, package: str):
        super().__init__(transient_for=parent_window)
        self.parent_window = parent_window
        self.package = package
        self.store: ProfileStore = parent_window.profiles
        self.profile = self.store.load(package)

        self.set_title(f"Клавиши — {package}")
        self.set_default_size(1100, 760)

        self._selected: Widget | None = None
        self._drag_offset = (0.0, 0.0)

        self._build_ui()
        self._capture_screenshot()

    # -------------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)

        # левый тулбар
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        left.set_size_request(210, -1)
        left.set_margin_top(12)
        left.set_margin_bottom(12)
        left.set_margin_start(12)
        left.set_margin_end(8)

        left_title = Gtk.Label(label="Добавить виджет", xalign=0)
        left_title.add_css_class("heading")

        left.append(left_title)
        for wtype, title in WIDGET_TITLES.items():
            btn = Gtk.Button(label=title)
            btn.connect("clicked", lambda _b, t=wtype: self._add_widget(t))
            left.append(btn)

        sep = Gtk.Separator()
        left.append(sep)

        shot_btn = Gtk.Button(label="Обновить скриншот")
        shot_btn.connect("clicked", lambda *_: self._capture_screenshot())
        left.append(shot_btn)

        save_btn = Gtk.Button(label="Сохранить")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", lambda *_: self._save())
        left.append(save_btn)

        play_btn = Gtk.Button(label="Играть")
        play_btn.connect("clicked", lambda *_: self._play())
        left.append(play_btn)

        clear_btn = Gtk.Button(label="Очистить всё")
        clear_btn.add_css_class("destructive-action")
        clear_btn.connect("clicked", lambda *_: self._clear())
        left.append(clear_btn)

        sep2 = Gtk.Separator()
        left.append(sep2)

        # настройки производительности на игру
        perf_title = Gtk.Label(label="Стрим этой игры", xalign=0)
        perf_title.add_css_class("heading")
        left.append(perf_title)

        size_label = Gtk.Label(label="Разрешение видео", xalign=0)
        size_label.add_css_class("dim-label")
        left.append(size_label)
        self.stream_size_row = Gtk.DropDown.new_from_strings(
            ["Как в настройках", "720p (960)", "HD (1280)", "Full HD (1920)", "Нативное"])
        size_values = [0, 960, 1280, 1920, -1]
        current = self.profile.stream_max_size
        self.stream_size_row.set_selected(
            size_values.index(current) if current in size_values else 0)
        self.stream_size_row.connect(
            "notify::selected",
            lambda r, p: setattr(self.profile, "stream_max_size",
                                 size_values[r.get_selected()]))
        left.append(self.stream_size_row)

        fps_label = Gtk.Label(label="Лимит FPS", xalign=0)
        fps_label.add_css_class("dim-label")
        left.append(fps_label)
        self.stream_fps_row = Gtk.DropDown.new_from_strings(
            ["Как в настройках", "30", "60", "120", "Без лимита"])
        fps_values = [0, 30, 60, 120, -1]
        current_fps = self.profile.stream_max_fps
        self.stream_fps_row.set_selected(
            fps_values.index(current_fps) if current_fps in fps_values else 0)
        self.stream_fps_row.connect(
            "notify::selected",
            lambda r, p: setattr(self.profile, "stream_max_fps",
                                 fps_values[r.get_selected()]))
        left.append(self.stream_fps_row)

        self.hint = Gtk.Label(
            label="ЛКМ — перетащить виджет.\nПКМ по виджету — свойства/удаление.",
            xalign=0, wrap=True)
        self.hint.add_css_class("dim-label")
        self.hint.set_margin_top(12)
        left.append(self.hint)

        # центр: холст
        self.canvas = Gtk.DrawingArea()
        self.canvas.set_hexpand(True)
        self.canvas.set_vexpand(True)
        self.canvas.set_draw_func(self._draw_canvas)

        click = Gtk.GestureClick()
        click.connect("pressed", self._on_canvas_press)
        self.canvas.add_controller(click)

        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        drag.connect("drag-end", self._on_drag_end)
        self.canvas.add_controller(drag)

        self._background_texture: Gdk.Texture | None = None
        self.canvas.set_content_width(16)
        self.canvas.set_content_height(9)

        canvas_frame = Gtk.Frame()
        canvas_frame.set_hexpand(True)
        canvas_frame.set_vexpand(True)
        canvas_frame.set_child(self.canvas)
        canvas_frame.add_css_class("card")

        center = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        center.set_hexpand(True)
        center.set_vexpand(True)
        center.set_margin_top(12)
        center.set_margin_bottom(12)
        center.set_margin_end(12)
        center.append(canvas_frame)

        root.append(left)
        root.append(center)

        header = Adw.HeaderBar()
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(root)
        self.set_content(toolbar)

    # ------------------------------------------------------------ screenshot
    def _capture_screenshot(self) -> None:
        def work():
            try:
                shot = str(self.parent_window.catalog.__class__ and
                           __import__("waydroid_stacks.core.config", fromlist=["x"]).SHOT_DIR /
                           f"{self.package.replace('.', '_')}.png")
                self.parent_window.adb.connect()
                self.parent_window.adb.screencap(shot)
                GLib.idle_add(self._set_background, shot)
            except Exception as exc:  # noqa: BLE001
                GLib.idle_add(self.parent_window.toast, f"Скриншот: {exc}")

        # запускаем приложение, чтобы фон был осмысленным
        try:
            self.parent_window.catalog.launch(self.package)
        except Exception:  # noqa: BLE001
            pass
        threading.Thread(target=work, daemon=True).start()

    def _set_background(self, path: str) -> None:
        try:
            self._background_texture = Gdk.Texture.new_from_filename(path)
            w, h = self._background_texture.get_width(), self._background_texture.get_height()
            self.canvas.set_content_width(w)
            self.canvas.set_content_height(h)
            self.canvas.queue_draw()
        except GLib.Error as exc:
            self.parent_window.toast(f"Фон: {exc}")

    # -------------------------------------------------------------- canvas
    def _canvas_geometry(self) -> tuple[float, float, float, float]:
        """Возвращает смещение и масштаб фона внутри холста."""
        alloc = self.canvas.get_allocation()
        cw, ch = alloc.width, alloc.height
        if not self._background_texture:
            return 0.0, 0.0, float(cw), float(ch)
        iw, ih = self._background_texture.get_width(), self._background_texture.get_height()
        scale = min(cw / iw, ch / ih) if iw and ih else 1.0
        dw, dh = iw * scale, ih * scale
        return (cw - dw) / 2, (ch - dh) / 2, dw, dh

    def _draw_canvas(self, area, cr, width, height) -> None:
        off_x, off_y, dw, dh = self._canvas_geometry()

        if self._background_texture:
            self._background_texture.download(cr.get_target(), 0, 0)
            cr.save()
            cr.translate(off_x, off_y)
            cr.scale(dw / self._background_texture.get_width(),
                     dh / self._background_texture.get_height())
            cr.set_source(self._background_texture)
            cr.paint()
            cr.restore()
        else:
            cr.set_source_rgb(0.13, 0.14, 0.17)
            cr.paint()

        colors = {
            W_TAP: (0.35, 0.75, 1.0, 0.55),
            W_HOLD: (1.0, 0.65, 0.25, 0.55),
            W_DPAD: (0.45, 0.95, 0.55, 0.55),
            W_AIM: (0.8, 0.55, 1.0, 0.45),
            W_SWIPE: (1.0, 0.45, 0.55, 0.55),
        }
        for widget in self.profile.widgets:
            cx = off_x + widget.x * dw
            cy = off_y + widget.y * dh
            r = widget.size * min(dw, dh)
            color = colors.get(widget.type, (1, 1, 1, 0.5))
            cr.set_source_rgba(*color)
            if widget.type == W_DPAD:
                cr.arc(cx, cy, widget.radius * min(dw, dh), 0, 6.2832)
                cr.fill()
            elif widget.type == W_AIM:
                cr.rectangle(cx - r * 2, cy - r * 1.2, r * 4, r * 2.4)
                cr.fill()
            else:
                cr.arc(cx, cy, r, 0, 6.2832)
                cr.fill()

            cr.set_source_rgba(1, 1, 1, 0.95)
            cr.set_line_width(2)
            cr.arc(cx, cy, r + 2, 0, 6.2832)
            cr.stroke()

            cr.set_source_rgba(0, 0, 0, 0.85)
            cr.select_font_face("Sans", 1, 1)
            cr.set_font_size(max(11, r * 0.9))
            text = self._widget_caption_brief(widget)
            ext = cr.text_extents(text)
            cr.move_to(cx - ext.width / 2, cy - r - 6)
            cr.show_text(text)

            if widget is self._selected:
                cr.set_source_rgba(1.0, 0.9, 0.2, 1.0)
                cr.set_line_width(3)
                cr.arc(cx, cy, r + 6, 0, 6.2832)
                cr.stroke()

    def _widget_caption_brief(self, w: Widget) -> str:
        if w.type == W_DPAD:
            return "WASD"
        if w.type == W_AIM:
            return "обзор"
        if w.type == W_SWIPE:
            return f"свайп {w.key}".strip()
        return w.key or "?"

    # ----------------------------------------------------------- interactions
    def _hit_test(self, px: float, py: float) -> Widget | None:
        off_x, off_y, dw, dh = self._canvas_geometry()
        for widget in reversed(self.profile.widgets):
            cx = off_x + widget.x * dw
            cy = off_y + widget.y * dh
            r = max(widget.size, 0.02) * min(dw, dh) + 8
            if (px - cx) ** 2 + (py - cy) ** 2 <= r * r:
                return widget
        return None

    def _on_canvas_press(self, gesture, n_press, x, y) -> None:
        widget = self._hit_test(x, y)
        self._selected = widget
        if gesture.get_current_button() == 3 and widget:
            self._widget_menu(widget)
        self.canvas.queue_draw()

    def _on_drag_begin(self, gesture, x, y) -> None:
        widget = self._hit_test(x, y)
        if widget:
            self._selected = widget
            off_x, off_y, dw, dh = self._canvas_geometry()
            self._drag_offset = (widget.x - (x - off_x) / dw,
                                 widget.y - (y - off_y) / dh)
        self.canvas.queue_draw()

    def _on_drag_update(self, gesture, dx, dy) -> None:
        if not self._selected:
            return
        _, _, _, _ = gesture.get_offset()
        start_x, start_y = gesture.get_start_point()
        off_x, off_y, dw, dh = self._canvas_geometry()
        nx = (start_x + dx - off_x) / dw + self._drag_offset[0]
        ny = (start_y + dy - off_y) / dh + self._drag_offset[1]
        self._selected.x = min(max(0.0, nx), 1.0)
        self._selected.y = min(max(0.0, ny), 1.0)
        self.canvas.queue_draw()

    def _on_drag_end(self, gesture, dx, dy) -> None:
        self.canvas.queue_draw()

    # --------------------------------------------------------------- actions
    def _add_widget(self, wtype: str) -> None:
        widget = Widget(type=wtype, x=0.5, y=0.5)
        if wtype == W_TAP:
            widget.label = "тап"
        elif wtype == W_HOLD:
            widget.label = "огонь"
        widget.key = "space" if wtype in (W_TAP, W_HOLD, W_SWIPE) else ""
        self.profile.widgets.append(widget)
        self._selected = widget
        self.canvas.queue_draw()
        self._edit_widget(widget)

    def _clear(self) -> None:
        self.profile.widgets.clear()
        self._selected = None
        self.canvas.queue_draw()

    def _widget_menu(self, widget: Widget) -> None:
        menu = Gio.Menu()
        menu.append("Настроить", "w.edit")
        menu.append("Удалить", "w.delete")

        groups = Gio.SimpleActionGroup()
        edit = Gio.SimpleAction.new("edit", None)
        edit.connect("activate", lambda *_: self._edit_widget(widget))
        delete = Gio.SimpleAction.new("delete", None)
        delete.connect("activate", lambda *_: self._delete_widget(widget))
        groups.add_action(edit)
        groups.add_action(delete)
        self.insert_action_group("w", groups)

        popover = Gtk.PopoverMenu.new_from_model(menu)
        popover.set_parent(self.canvas)
        popover.popup()

    def _delete_widget(self, widget: Widget) -> None:
        self.profile.widgets.remove(widget)
        if self._selected is widget:
            self._selected = None
        self.canvas.queue_draw()

    def _first_free_key(self) -> str:
        used = {w.key.lower() for w in self.profile.widgets if w.key}
        for k in ("space", "j", "k", "l", "u", "i", "o", "p",
                  "1", "2", "3", "4", "q", "e", "r", "f", "shift", "ctrl"):
            if k not in used:
                return k
        return ""

    def _edit_widget(self, widget: Widget) -> None:
        dialog = Adw.Window(transient_for=self, modal=True)
        dialog.set_title("Настройка виджета")
        dialog.set_default_size(430, 560)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(16)
        box.set_margin_end(16)

        title = Gtk.Label(label=WIDGET_TITLES.get(widget.type, widget.type), xalign=0)
        title.add_css_class("title-3")
        box.append(title)

        def add_row(name: str, child: Gtk.Widget) -> None:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            lbl = Gtk.Label(label=name, xalign=0)
            lbl.set_size_request(130, -1)
            row.append(lbl)
            child.set_hexpand(True)
            row.append(child)
            box.append(row)

        # --- клавиши
        if widget.type == W_DPAD:
            self._dpad_entries = {}
            for direction, name in (("up", "Вверх"), ("down", "Вниз"),
                                    ("left", "Влево"), ("right", "Вправо")):
                entry = Gtk.Entry()
                entry.set_text(widget.keys.get(direction, ""))
                cap = KeyCaptureButton(entry)
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                row.append(entry)
                row.append(cap)
                add_row(name, row)
                self._dpad_entries[direction] = entry

            radius_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,
                                                    0.04, 0.3, 0.005)
            radius_scale.set_value(widget.radius)
            radius_scale.connect("value-changed",
                                 lambda s: (setattr(widget, "radius", s.get_value()),
                                            self.canvas.queue_draw()))
            add_row("Радиус", radius_scale)
        else:
            key_entry = Gtk.Entry()
            key_entry.set_text(widget.key)
            cap_btn = KeyCaptureButton(key_entry)
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            row.append(key_entry)
            row.append(cap_btn)
            add_row("Клавиша", row)

            if widget.type == W_AIM:
                sens = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.2, 4.0, 0.1)
                sens.set_value(widget.sensitivity)
                sens.connect("value-changed",
                             lambda s: setattr(widget, "sensitivity", s.get_value()))
                add_row("Чувствительность", sens)

                smooth = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 0.9, 0.05)
                smooth.set_value(widget.smoothing)
                smooth.connect("value-changed",
                               lambda s: setattr(widget, "smoothing", s.get_value()))
                add_row("Сглаживание", smooth)

                inertia = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 0.9, 0.05)
                inertia.set_value(widget.inertia)
                inertia.connect("value-changed",
                                lambda s: setattr(widget, "inertia", s.get_value()))
                add_row("Инерция", inertia)

            if widget.type == W_SWIPE:
                dx = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -0.5, 0.5, 0.01)
                dx.set_value(widget.dx)
                dx.connect("value-changed",
                           lambda s: setattr(widget, "dx", s.get_value()))
                add_row("Смещение X", dx)

                dy = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -0.5, 0.5, 0.01)
                dy.set_value(widget.dy)
                dy.connect("value-changed",
                           lambda s: setattr(widget, "dy", s.get_value()))
                add_row("Смещение Y", dy)

        # --- подпись и размер
        label_entry = Gtk.Entry()
        label_entry.set_text(widget.label)
        label_entry.connect("changed", lambda e: setattr(widget, "label", e.get_text()))
        add_row("Подпись", label_entry)

        size = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.02, 0.15, 0.005)
        size.set_value(widget.size)
        size.connect("value-changed",
                     lambda s: (setattr(widget, "size", s.get_value()),
                                self.canvas.queue_draw()))
        add_row("Размер", size)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_row.set_margin_top(10)
        apply_btn = Gtk.Button(label="Готово")
        apply_btn.add_css_class("suggested-action")
        delete_btn = Gtk.Button(label="Удалить")
        delete_btn.add_css_class("destructive-action")

        def apply(_b):
            if widget.type == W_DPAD:
                widget.keys = {d: e.get_text().strip().lower()
                               for d, e in self._dpad_entries.items()}
            else:
                widget.key = key_entry.get_text().strip().lower()
            widget.label = label_entry.get_text()
            self.canvas.queue_draw()
            dialog.close()

        def delete(_b):
            self._delete_widget(widget)
            dialog.close()

        apply_btn.connect("clicked", apply)
        delete_btn.connect("clicked", delete)
        btn_row.append(delete_btn)
        btn_row.append(apply_btn)
        box.append(btn_row)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(box)
        dialog.set_content(scrolled)
        dialog.present()

    def _save(self) -> None:
        self.store.save(self.profile)
        self.parent_window.toast(f"Профиль сохранён: {self.package}")
        try:
            self.parent_window.keymapper_page.refresh()
        except AttributeError:
            pass

    def _play(self) -> None:
        self._save()
        self.parent_window.launch_package(self.package, with_keymap=True)


class KeyCaptureButton(Gtk.Button):
    """Кнопка «Записать клавишу»: ловит следующее нажатие клавиатуры."""

    def __init__(self, entry: Gtk.Entry):
        super().__init__(label="⏺ Записать")
        self.entry = entry
        self.set_tooltip_text("Нажмите и введите нужную клавишу")
        self.connect("clicked", self._start_capture)
        self._controller = None

    def _start_capture(self, _btn) -> None:
        self.set_label("Нажмите клавишу...")
        controller = Gtk.EventControllerKey()
        controller.connect("key-pressed", self._on_key)
        self.add_controller(controller)
        self._controller = controller
        self.grab_focus()

    def _on_key(self, controller, keyval, keycode, state) -> bool:
        name = Gdk.keyval_name(keyval) or ""
        name = name.lower()
        if name in ("escape", "esc"):
            name = ""
        self.entry.set_text(name)
        self.set_label("⏺ Записать")
        if self._controller:
            self.remove_controller(self._controller)
            self._controller = None
        return True
