#!/usr/bin/env bash
# Установка Waydroid Stacks в ~/.local (без root) + ярлыки.
#
# Варианты запуска:
#   1) из клонированного репозитория:  ./scripts/install.sh
#   2) одной командой:
#      curl -fsSL https://raw.githubusercontent.com/syb1v/waydroid-stacks/master/scripts/install.sh | bash
#   3) с параметрами:
#      curl -fsSL .../install.sh | bash -s -- --version v0.3.0 --desktop-shortcut
#
# Параметры:
#   --version vX.Y.Z     установить конкретный релиз (по умолчанию — последний)
#   --desktop-shortcut   положить ярлык Waydroid Stacks на рабочий стол
#   --no-deps-check      пропустить проверку системных зависимостей
set -euo pipefail

REPO="syb1v/waydroid-stacks"
PREFIX="${PREFIX:-$HOME/.local}"
VENV="$HOME/.local/share/waydroid-stacks/venv"
SRC_DIR="$HOME/.local/share/waydroid-stacks/src"
DESKTOP_SHORTCUT=0
DEPS_CHECK=1
VERSION=""

while [ $# -gt 0 ]; do
    case "$1" in
        --version) VERSION="${2:?--version требует значения}"; shift 2 ;;
        --desktop-shortcut) DESKTOP_SHORTCUT=1; shift ;;
        --no-deps-check) DEPS_CHECK=0; shift ;;
        -h|--help) sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Неизвестный параметр: $1" >&2; exit 2 ;;
    esac
done

msg() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31mОшибка:\033[0m %s\n' "$*" >&2; exit 1; }

# --- откуда берём исходники -------------------------------------------------
SELF="${BASH_SOURCE[0]:-}"
if [ -n "$SELF" ] && [ -f "$SELF" ]; then
    LOCAL_ROOT="$(cd "$(dirname "$SELF")/.." && pwd)"
else
    LOCAL_ROOT=""
fi

# --- проверка зависимостей ---------------------------------------------------
if [ "$DEPS_CHECK" = 1 ]; then
    msg "Проверка зависимостей"
    missing=()
    command -v python3 >/dev/null || missing+=("python3")
    python3 -c "import gi; gi.require_version('Gtk','4.0'); gi.require_version('Adw','1')" 2>/dev/null \
        || missing+=("python-gobject + gtk4 + libadwaita")
    python3 -c "import gi; gi.require_version('Gst','1.0')" 2>/dev/null \
        || missing+=("gstreamer и python-биндинги (gst-python / python3-gst-1.0 / python3-gstreamer1)")
    command -v adb >/dev/null || missing+=("adb (android-tools)")
    command -v waydroid >/dev/null || missing+=("waydroid")
    if ((${#missing[@]})); then
        echo "Не найдено:"
        printf '  - %s\n' "${missing[@]}"
        case "$(uname -s)" in
            Linux)
                if [ -f /etc/arch-release ]; then
                    echo "Arch:  sudo pacman -S python-gobject gtk4 libadwaita gst-python gst-plugins-base gst-plugins-good android-tools && yay -S waydroid waydroid-image"
                elif [ -f /etc/debian_version ]; then
                    echo "Debian/Ubuntu: sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 python3-gst-1.0 gstreamer1.0-plugins-base gstreamer1.0-plugins-good adb waydroid"
                elif [ -f /etc/fedora-release ]; then
                    echo "Fedora: sudo dnf install python3-gobject gtk4 libadwaita python3-gstreamer1 gstreamer1-plugins-base gstreamer1-plugins-good android-tools"
                fi
                ;;
        esac
        echo "Установите их и повторите (или запустите с --no-deps-check)."
        exit 1
    fi
fi

# --- получение исходников ----------------------------------------------------
if [ -n "$LOCAL_ROOT" ] && [ -f "$LOCAL_ROOT/pyproject.toml" ]; then
    ROOT="$LOCAL_ROOT"
    msg "Установка из локального репозитория: $ROOT"
else
    command -v curl >/dev/null || fail "нужен curl для загрузки исходников"
    if [ -z "$VERSION" ]; then
        msg "Определяю последний релиз"
        VERSION="$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" 2>/dev/null \
            | sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' | head -1)"
        [ -n "$VERSION" ] || VERSION="master"
    fi
    msg "Загрузка исходников $VERSION"
    mkdir -p "$SRC_DIR"
    TARBALL="$(mktemp /tmp/waydroid-stacks-XXXXXX.tar.gz)"
    if [ "$VERSION" = "master" ]; then
        URL="https://github.com/$REPO/archive/refs/heads/master.tar.gz"
    else
        URL="https://github.com/$REPO/archive/refs/tags/$VERSION.tar.gz"
    fi
    curl -fsSL "$URL" -o "$TARBALL" || fail "не удалось скачать $URL"
    rm -rf "$SRC_DIR"/*
    tar -xzf "$TARBALL" -C "$SRC_DIR" --strip-components=1
    rm -f "$TARBALL"
    ROOT="$SRC_DIR"
fi

# --- виртуальное окружение ---------------------------------------------------
msg "Виртуальное окружение: $VENV"
python3 -m venv --system-site-packages "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet "$ROOT"

# --- обёртка запуска ---------------------------------------------------------
msg "Обёртка запуска: $PREFIX/bin/waydroid-stacks"
mkdir -p "$PREFIX/bin"
cat > "$PREFIX/bin/waydroid-stacks" <<EOF
#!/usr/bin/env bash
exec "$VENV/bin/python3" -m waydroid_stacks "\$@"
EOF
chmod +x "$PREFIX/bin/waydroid-stacks"

# --- ярлык и иконка ----------------------------------------------------------
msg "Ярлык в меню приложений"
ICON_DIR="$PREFIX/share/icons/hicolor/scalable/apps"
APP_DIR="$PREFIX/share/applications"
mkdir -p "$ICON_DIR" "$APP_DIR"
cp "$ROOT/data/icons/io.github.syb1v.WaydroidStacks.svg" "$ICON_DIR/"
cp "$ROOT/data/io.github.syb1v.WaydroidStacks.desktop" "$APP_DIR/"
sed -i "s|^Exec=.*|Exec=$PREFIX/bin/waydroid-stacks|" "$APP_DIR/io.github.syb1v.WaydroidStacks.desktop"
gtk-update-icon-cache -f "$PREFIX/share/icons/hicolor" >/dev/null 2>&1 || true
update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true

# --- ярлык на рабочем столе (опционально) ------------------------------------
if [ "$DESKTOP_SHORTCUT" = 1 ]; then
    DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
    if [ -d "$DESKTOP_DIR" ]; then
        msg "Ярлык на рабочем столе: $DESKTOP_DIR"
        cp "$APP_DIR/io.github.syb1v.WaydroidStacks.desktop" "$DESKTOP_DIR/"
        chmod +x "$DESKTOP_DIR/io.github.syb1v.WaydroidStacks.desktop"
        if command -v gio >/dev/null 2>&1; then
            gio set "$DESKTOP_DIR/io.github.syb1v.WaydroidStacks.desktop" \
                metadata::trusted true >/dev/null 2>&1 || true
        fi
    else
        echo "Каталог рабочего стола не найден — пропускаю."
    fi
fi

msg "Готово! Запускайте: waydroid-stacks (или из меню приложений)"
if [ "$DESKTOP_SHORTCUT" != 1 ]; then
    echo "Подсказка: ярлык на рабочий стол — добавьте флаг --desktop-shortcut."
fi
