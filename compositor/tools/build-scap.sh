#!/usr/bin/env bash
# Сборка waydroid-stacks-screencap — снимок кадра из wlroots-композитора
# через zwlr_screencopy (используется для отладки и будущих F8-скриншотов).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

command -v wayland-scanner >/dev/null || { echo "нужен wayland-scanner (пакет wayland)"; exit 1; }

wayland-scanner client-header wlr-screencopy-unstable-v1.xml screencopy.h
wayland-scanner private-code  wlr-screencopy-unstable-v1.xml screencopy.c
cc -O2 -o waydroid-stacks-screencap scap.c screencopy.c \
    $(pkg-config --cflags --libs wayland-client)

echo "==> Готово: $ROOT/waydroid-stacks-screencap"
