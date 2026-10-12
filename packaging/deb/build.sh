#!/usr/bin/env bash
# Сборка .deb-пакета Waydroid Stacks.
# Требуется dpkg-deb (Debian/Ubuntu или пакет dpkg в любом дистрибутиве).
# Использование: packaging/deb/build.sh [выходной_каталог]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="${1:-$ROOT/dist}"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/waydroid_stacks/__init__.py")"
DATADIR="/usr/share/waydroid-stacks"

command -v dpkg-deb >/dev/null || { echo "Нужен dpkg-deb (пакет dpkg)." >&2; exit 1; }

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$OUT"

appdir="$STAGE$DATADIR"
mkdir -p "$appdir"
cp -a "$ROOT/waydroid_stacks" "$appdir/"
cp -a "$ROOT/third_party" "$appdir/"
find "$appdir" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

install -Dm755 "$ROOT/packaging/launcher.sh.in" "$STAGE/usr/bin/waydroid-stacks"
sed -i "s|@DATADIR@|$DATADIR|" "$STAGE/usr/bin/waydroid-stacks"
install -Dm644 "$ROOT/data/io.github.syb1v.WaydroidStacks.desktop" \
    "$STAGE/usr/share/applications/io.github.syb1v.WaydroidStacks.desktop"
install -Dm644 "$ROOT/data/icons/io.github.syb1v.WaydroidStacks.svg" \
    "$STAGE/usr/share/icons/hicolor/scalable/apps/io.github.syb1v.WaydroidStacks.svg"
install -Dm644 "$ROOT/LICENSE" \
    "$STAGE/usr/share/doc/waydroid-stacks/copyright"

mkdir -p "$STAGE/DEBIAN"
cat > "$STAGE/DEBIAN/control" <<EOF
Package: waydroid-stacks
Version: $VERSION
Architecture: all
Maintainer: syb1v <108201690+syb1v@users.noreply.github.com>
Section: games
Priority: optional
Homepage: https://github.com/syb1v/waydroid-stacks
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-4.0 (>= 4.10),
 gir1.2-adw-1, python3-gst-1.0, gstreamer1.0-plugins-base,
 gstreamer1.0-plugins-good
Recommends: gstreamer1.0-libav, gstreamer1.0-plugins-bad, adb, waydroid,
 python3-pyaxmlparser
Description: BlueStacks-like shell for Waydroid (Android games on Linux)
 Библиотека приложений, встроенный игровой режим (scrcpy + GStreamer/VA-API),
 кеймаппер клавиатуры/мыши и ввод текста в поля Android без экранной
 клавиатуры. Требует установленных Waydroid и adb.
EOF
cat > "$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q /usr/share/icons/hicolor || true
fi
exit 0
EOF
cat > "$STAGE/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
exit 0
EOF
chmod 755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/postrm"

TARGET="$OUT/waydroid-stacks_${VERSION}_all.deb"
dpkg-deb --root-owner-group --build "$STAGE" "$TARGET"
echo "OK: $TARGET"
