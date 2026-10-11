#!/usr/bin/env bash
# Установка Waydroid Stacks в ~/.local (без root) + системный ярлык.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREFIX="${PREFIX:-$HOME/.local}"
VENV="$HOME/.local/share/waydroid-stacks/venv"

echo "==> Проверка зависимостей"
missing=()
command -v python3 >/dev/null || missing+=("python3")
python3 -c "import gi; gi.require_version('Gtk','4.0'); gi.require_version('Adw','1')" 2>/dev/null \
    || missing+=("python-gobject gtk4 libadwaita (pacman -S python-gobject gtk4 libadwaita)")
python3 -c "import gi; gi.require_version('Gst','1.0')" 2>/dev/null \
    || missing+=("gstreamer gst-plugins-base gst-plugins-good gst-libav (для видеоплеера)")
command -v adb >/dev/null || missing+=("android-tools (pacman -S android-tools)")
command -v waydroid >/dev/null || missing+=("waydroid waydroid-image (pacman -S waydroid waydroid-image)")
if ((${#missing[@]})); then
    echo "Не найдено:"
    printf '  - %s\n' "${missing[@]}"
    echo "Установите их и повторите."
    exit 1
fi

echo "==> Виртуальное окружение: $VENV"
python3 -m venv --system-site-packages "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet "$ROOT"

echo "==> Обёртка запуска: $PREFIX/bin/waydroid-stacks"
mkdir -p "$PREFIX/bin"
cat > "$PREFIX/bin/waydroid-stacks" <<EOF
#!/usr/bin/env bash
exec "$VENV/bin/python3" -m waydroid_stacks "\$@"
EOF
chmod +x "$PREFIX/bin/waydroid-stacks"

echo "==> Ярлык и иконка"
ICON_DIR="$PREFIX/share/icons/hicolor/scalable/apps"
APP_DIR="$PREFIX/share/applications"
mkdir -p "$ICON_DIR" "$APP_DIR"
cp "$ROOT/data/icons/io.github.syb1v.WaydroidStacks.svg" "$ICON_DIR/"
cp "$ROOT/data/io.github.syb1v.WaydroidStacks.desktop" "$APP_DIR/"

# заменяем Exec на абсолютный путь (на случай, если ~/.local/bin не в PATH)
sed -i "s|^Exec=.*|Exec=$PREFIX/bin/waydroid-stacks|" "$APP_DIR/io.github.syb1v.WaydroidStacks.desktop"
gtk-update-icon-cache -f "$PREFIX/share/icons/hicolor" >/dev/null 2>&1 || true
update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true

echo "==> Готово! Запускайте: waydroid-stacks  (или из меню приложений)"
