#!/usr/bin/env bash
# Выпуск новой версии: обновляет версию в коде, CHANGELOG, коммит и тег.
# Использование: ./scripts/release.sh 0.2.0 ["описание"]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${1:?Использование: scripts/release.sh X.Y.Z [описание]}"
DESC="${2:-}"

if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Ошибка: версия должна быть в формате X.Y.Z (semver)." >&2
    exit 1
fi

echo "==> Обновляю версию до $VERSION"
python3 - "$ROOT/waydroid_stacks/__init__.py" "$VERSION" <<'PY'
import re, sys
path, version = sys.argv[1], sys.argv[2]
text = open(path, encoding="utf-8").read()
text = re.sub(r'__version__ = "[^"]*"', f'__version__ = "{version}"', text)
open(path, "w", encoding="utf-8").write(text)
PY

echo "==> Обновляю CHANGELOG.md"
python3 - "$ROOT/CHANGELOG.md" "$VERSION" "$DESC" <<'PY'
import datetime, sys
path, version, desc = sys.argv[1], sys.argv[2], sys.argv[3]
text = open(path, encoding="utf-8").read()
date = datetime.date.today().isoformat()
header = f"## [{version}] - {date}\n\n### Добавлено\n\n" + (f"- {desc}\n" if desc else "- (заполните перед публикацией)\n")
text = text.replace("## [Unreleased]\n", f"## [Unreleased]\n\n{header}\n", 1)
open(path, "w", encoding="utf-8").write(text)
PY

cd "$ROOT"
git add -A
git -c user.name="$(git config user.name || echo syb1v)" \
    -c user.email="$(git config user.email || echo Sokolovsky08@gmail.com)" \
    commit -m "release: v$VERSION"
git tag -a "v$VERSION" -m "Waydroid Stacks v$VERSION"

echo "==> Готово: создан commit и тег v$VERSION. Отправка: git push --follow-tags"
