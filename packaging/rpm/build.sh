#!/usr/bin/env bash
# Сборка .rpm-пакета Waydroid Stacks.
# В CI (Ubuntu с установленным rpm) собирает нативно через rpmbuild,
# иначе использует Docker с Fedora.
# Использование: packaging/rpm/build.sh [выходной_каталог]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="${1:-$ROOT/dist}"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/waydroid_stacks/__init__.py")"
BUILD="$(mktemp -d)"

mkdir -p "$OUT"

git -C "$ROOT" archive --format=tar.gz \
    --prefix="waydroid-stacks-$VERSION/" \
    -o "$BUILD/waydroid-stacks-$VERSION.tar.gz" HEAD

sed "s/^Version:.*/Version:        $VERSION/" \
    "$ROOT/packaging/rpm/waydroid-stacks.spec" > "$BUILD/waydroid-stacks.spec"

if command -v rpmbuild >/dev/null 2>&1; then
    echo "==> Нативная сборка rpmbuild"
    mkdir -p "$BUILD"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}
    mv "$BUILD/waydroid-stacks-$VERSION.tar.gz" "$BUILD/SOURCES/"
    mv "$BUILD/waydroid-stacks.spec" "$BUILD/SPECS/"
    rpmbuild -bb "$BUILD/SPECS/waydroid-stacks.spec" --define "_topdir $BUILD" \
        --define "_rpmdir $BUILD/RPMS"
    cp "$BUILD"/RPMS/noarch/*.rpm "$OUT/"
else
    echo "==> Сборка через Docker (Fedora)"
    RPMBUILD=/tmp/opencode/rpmbuild
    rm -rf "$RPMBUILD"
    mkdir -p "$RPMBUILD"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}
    cp "$BUILD/waydroid-stacks-$VERSION.tar.gz" "$RPMBUILD/SOURCES/"
    cp "$BUILD/waydroid-stacks.spec" "$RPMBUILD/SPECS/waydroid-stacks.spec"
    docker run --rm \
        -v "$RPMBUILD:/build" \
        -v "$OUT:/out" \
        fedora:41 \
        sh -c 'dnf install -y -q rpm-build >/dev/null 2>&1; rpmbuild -bb /build/SPECS/waydroid-stacks.spec --define "_topdir /build"; cp /build/RPMS/noarch/*.rpm /out/'
fi

rm -rf "$BUILD"
echo "OK: $OUT"
ls -la "$OUT"/*.rpm
