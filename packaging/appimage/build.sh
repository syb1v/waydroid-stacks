#!/usr/bin/env bash
# Сборка автономного AppImage (Python + GTK4 + GStreamer внутри).
# Если appimage-builder доступен нативно (CI) — собирает им, иначе через Docker.
# Использование: packaging/appimage/build.sh [выходной_каталог]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="${1:-$ROOT/dist}"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/waydroid_stacks/__init__.py")"

mkdir -p "$OUT"
BUILD="${TMPDIR:-/tmp}/waydroid-stacks-appimage-build"
rm -rf "$BUILD"
mkdir -p "$BUILD"

tar -C "$ROOT" \
    --exclude=.git --exclude=dist --exclude=ime/build \
    --exclude=__pycache__ --exclude='*.pyc' --exclude=.venv \
    -cf - . | tar -x -C "$BUILD"

sed "s/@VERSION@/$VERSION/g" \
    "$BUILD/packaging/appimage/AppImageBuilder.yml" > "$BUILD/AppImageBuilder.yml"

if command -v appimage-builder >/dev/null 2>&1; then
    echo "==> Нативная сборка appimage-builder"
    # gdk-pixbuf-query-loaders в Ubuntu лежит вне PATH
    if ! command -v gdk-pixbuf-query-loaders >/dev/null 2>&1; then
        for cand in /usr/lib/x86_64-linux-gnu/gdk-pixbuf-2.0/gdk-pixbuf-query-loaders \
                    /usr/lib/x86_64-linux-gnu/gdk-pixbuf-2.0/gdk-pixbuf-query-loaders-64; do
            [ -x "$cand" ] && ln -sf "$cand" /usr/local/bin/gdk-pixbuf-query-loaders 2>/dev/null || true
        done
    fi
    (cd "$BUILD" && SOURCE_DIR="$BUILD" appimage-builder \
        --recipe AppImageBuilder.yml --skip-tests)
    cp "$BUILD"/*.AppImage "$OUT/" 2>/dev/null || \
        find "$BUILD" -maxdepth 1 -name "*.AppImage" -exec cp {} "$OUT/" \;
else
    echo "==> Сборка через Docker"
    if ! docker image inspect waydroid-stacks-appimage-builder >/dev/null 2>&1; then
        docker build -t waydroid-stacks-appimage-builder "$ROOT/packaging/appimage"
    fi
    docker run --rm --privileged \
        -v "$BUILD:/build" \
        -v "$OUT:/out" \
        -w /build \
        -e SOURCE_DIR=/build \
        waydroid-stacks-appimage-builder \
        sh -c 'appimage-builder --recipe AppImageBuilder.yml --skip-tests && \
               cp /build/*.AppImage /out/ 2>/dev/null || \
               find /build -maxdepth 2 -name "*.AppImage" -exec cp {} /out/ \;'
fi

echo "OK: $OUT"
ls -la "$OUT"/*.AppImage
