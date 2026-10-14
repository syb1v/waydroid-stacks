#!/usr/bin/env bash
# Сборка waydroid-stacks-session (форк cage) для игрового сеанса Waydroid.
#
# Обычная сборка (wlroots установлен в систему):
#     compositor/build.sh
# Локальная сборка с распакованным префиксом зависимостей (без установки):
#     WDS_DEPS_PREFIX=/path/to/prefix compositor/build.sh
#
# Результат: compositor/build/waydroid-stacks-session
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${BUILD_DIR:-$ROOT/build}"

if [ -n "${WDS_DEPS_PREFIX:-}" ]; then
    export PKG_CONFIG_PATH="$WDS_DEPS_PREFIX/lib/pkgconfig:$WDS_DEPS_PREFIX/share/pkgconfig:${PKG_CONFIG_PATH:-}"
    export LDFLAGS="-Wl,-rpath,$WDS_DEPS_PREFIX/lib ${LDFLAGS:-}"
fi

command -v meson >/dev/null || { echo "нужен meson (pacman -S meson)"; exit 1; }
command -v ninja >/dev/null || { echo "нужен ninja (pacman -S ninja)"; exit 1; }

if [ ! -d "$BUILD_DIR" ]; then
    meson setup "$BUILD_DIR" "$ROOT" "$@"
fi
ninja -C "$BUILD_DIR"
echo "==> Готово: $BUILD_DIR/waydroid-stacks-session"
