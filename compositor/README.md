# Waydroid Stacks session (форк cage)

Собственный Wayland-композитор игрового сеанса Waydroid Stacks: kiosk-сессия,
в которой Android рендерится напрямую (без H.264-стрима и внешнего окна),
а ввод идёт через композитор.

Основано на [Cage](https://www.hjdskes.nl/projects/cage/) 0.3.1 (MIT,
© Jente Hidskes) — минимальном kiosk-композиторе на wlroots. Исходники и
лицензия сохранены; ниже — только наши отличия.

## Отличия от upstream

- бинарник называется `waydroid-stacks-session`;
- создаётся менеджер `zwp_pointer_constraints_v1` — Waydroid HWC
  (`WaydroidWindow::setPointerCapture`) лочит указатель в играх через этот
  протокол; без него мышь уезжает за пределы экрана Android;
- man-страницы upstream исключены из сборки.

План дальнейших правок (v0.4, игровой сеанс):

- хоткеи сеанса: выход (Ctrl+Alt+Q), скриншот (F8) через встроенный
  screencopy, индикатор записи (F9);
- интеграция с запуском из приложения: `scripts/game-session.sh`
  (остановка сеанса Waydroid в рабочем столе → запуск Android внутри
  `waydroid-stacks-session` → возврат в рабочий стол по выходу);
- режим DRM/VT (без внешнего окна): требует `seatd`
  (`sudo pacman -S seatd && sudo systemctl enable --now seatd`), без него
  используется вложенный полноэкранный режим.

## Сборка

Системные зависимости: `meson`, `ninja`, `wlroots0.20`, `wayland`,
`wayland-protocols`, `libxkbcommon` (в CachyOS/Arch).

    compositor/build.sh

Локальная сборка без установки wlroots (префикс с распакованными `.pc`):

    WDS_DEPS_PREFIX=/path/to/prefix compositor/build.sh

Результат: `compositor/build/waydroid-stacks-session`.

## Запуск

Вложенно, окном в текущем рабочем столе (для отладки):

    WLR_BACKENDS=wayland WLR_RENDERER=gles2 \
        compositor/build/waydroid-stacks-session -- waydroid session start

Полноэкранная DRM/VT-сессия (нужен seatd):

    compositor/build/waydroid-stacks-session -- waydroid session start

## Утилита скриншота

`tools/` — `waydroid-stacks-screencap`: снимок кадра из любого
wlroots-композитора через `zwlr_screencopy` (используется для отладки и
будущих F8-скриншотов в сеансе).

    compositor/tools/build-scap.sh
    WAYLAND_DISPLAY=wayland-1 compositor/tools/waydroid-stacks-screencap out.ppm
