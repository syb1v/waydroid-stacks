# Waydroid Stacks

**BlueStacks для Linux, которого раньше не существовало.** Единственная в мире
интегрированная оболочка для Waydroid: библиотека приложений, встроенный
экран Android в окне приложения и кеймаппер клавиатуры/мыши — в одном нативном
GTK4-приложении.

![Version](https://img.shields.io/badge/version-0.2.0-blue)
![License](https://img.shields.io/badge/license-GPL--3.0--or--later-green)
![Platform](https://img.shields.io/badge/platform-Linux-lightgrey)
![GTK4](https://img.shields.io/badge/GTK4-libadwaita-purple)

## Почему такого решения больше нигде нет

**На момент версии 0.1.0 аналогов Waydroid Stacks не существует.** До этого
проекта на Linux не было ни одного готового решения уровня BlueStacks:

- BlueStacks, MuMu, LDPlayer, MEmu — **только Windows/macOS**, на Linux не
  устанавливаются ни напрямую, ни через Wine.
- На Linux приходилось вручную собирать зоопарк из `waydroid` + `adb` + `scrcpy` +
  `waydroid-helper` + XtMapper + собственных shell-скриптов, и ни один из этих
  инструментов не давал единого интерфейса «библиотека → игра → клавиши».
- Существующие утилиты (Waydroid Helper, XtMapper, qemu-эмуляторы Android Studio)
  решают каждый по одной задаче и не связаны между собой.

Waydroid Stacks — **первое и единственное** приложение, которое объединяет всё
это в единый продукт:

| | Windows-эмуляторы<br>(BlueStacks и др.) | Waydroid Helper /<br>XtMapper / scrcpy | **Waydroid Stacks** |
|---|:---:|:---:|:---:|
| Работает на Linux | ✗ | ✓ (по отдельности) | **✓** |
| Библиотека игр с иконками и запуском | ✓ | ✗ | **✓** |
| Экран Android внутри окна приложения | ✓ | ✗ | **✓** |
| Кеймаппер с визуальным редактором | ✓ | частично | **✓** |
| Единая установка «под ключ» | ✓ | ✗ | **✓** |
| Открытый исходный код | ✗ | ✓ | **✓** |

## Возможности

- **Библиотека приложений («Мои игры»)** — сетка установленных Android-приложений
  с настоящими иконками и названиями из APK, поиск, установка APK, удаление, запуск.
- **Встроенный игровой режим** — экран Android транслируется прямо в окно
  приложения (scrcpy-server + GStreamer/VA-API, аппаратное декодирование H.264).
  Не нужно второе окно или отдельный эмулятор.
- **Кеймаппер как в BlueStacks**:
  - виджеты: **Тап**, **Удержание**, **Джойстик (WASD)**, **Обзор мышью**, **Свайп**;
  - визуальный редактор: фон — скриншот игры, виджеты перетаскиваются мышью;
  - профиль привязывается к пакету приложения и хранится в
    `~/.config/waydroid-stacks/keymaps`;
  - мультитач: джойстик + кнопки работают одновременно.
- **Мультитач-инъекция** через протокол scrcpy-server 3.x
  (`INJECT_TOUCH_EVENT`/`INJECT_KEYCODE`) — низкая задержка.
- **Ввод текста в поля игры без экранной клавиатуры** — собственная тихая
  IME: при фокусе на текстовом поле текст и спецклавиши идут напрямую в поле
  (Unicode, кириллица, Backspace/Enter/стрелки), экранная клавиатура Android
  не перекрывает игру. Работает автоматически; при закрытии игры возвращается
  прежняя клавиатура.
- **Ярлыки на рабочем столе** для любого Android-приложения в один клик.
- **Настройки**: запуск/остановка сессии, разрешение и FPS стрима,
  сетевые правила ufw, установка расширений (libndk/GApps).

## Требования

- Waydroid (рабочая сессия) + Android-образ (протестировано на LineageOS 20)
- `python-gobject`, `gtk4`, `libadwaita`
- GStreamer: `gstreamer gst-plugins-base gst-plugins-good gst-libav`
  (для аппаратного декодирования — `gst-plugin-va`)
- `android-tools` (adb)
- Рекомендуется: `gst-plugin-gtk4` (быстрый вывод видео), `waydroid-helper`
  (установка libndk/GApps), libndk для ARM-игр

## Установка

### Универсально, одной командой (без root)

```bash
curl -fsSL https://raw.githubusercontent.com/syb1v/waydroid-stacks/master/scripts/install.sh | bash
```

Скрипт сам скачает свежий релиз, создаст окружение в `~/.local` и добавит
ярлык в меню приложений. Ярлык на рабочем столе:

```bash
curl -fsSL https://raw.githubusercontent.com/syb1v/waydroid-stacks/master/scripts/install.sh | bash -s -- --desktop-shortcut
```

### Arch Linux / Manjaro (AUR)

```bash
yay -S waydroid-stacks      # или paru
```

### Debian / Ubuntu / Mint (.deb)

1. Скачайте `waydroid-stacks_X.Y.Z_all.deb` со страницы
   [Releases](https://github.com/syb1v/waydroid-stacks/releases).
2. Установите:

```bash
sudo apt install ./waydroid-stacks_*.deb
```

### Fedora / openSUSE (.rpm)

1. Скачайте `waydroid-stacks-X.Y.Z-1.*.noarch.rpm` со страницы Releases.
2. Установите:

```bash
sudo dnf install ./waydroid-stacks-*.noarch.rpm   # Fedora
sudo zypper install ./waydroid-stacks-*.noarch.rpm # openSUSE
```

### AppImage (любой дистрибутив, без установки)

```bash
chmod +x waydroid-stacks-*.AppImage
./waydroid-stacks-*.AppImage
```

AppImage содержит Python, GTK4 и GStreamer внутри; системными должны быть
только `waydroid` и `adb`.

### Из исходников

```bash
git clone https://github.com/syb1v/waydroid-stacks.git
cd waydroid-stacks
./scripts/install.sh
```

## Быстрый старт

1. Запустите Waydroid Stacks — приложение само поднимет сессию Waydroid и adb.
2. На странице **«Мои игры»** нажмите на игру — она запустится в Android.
3. Для управления с клавиатуры: откройте **«Клавиатура» → Создать профиль**,
   укажите пакет игры (например `com.launcher.brgame`), расставьте на скриншоте
   виджеты (джойстик, кнопки, обзор) и назначьте клавиши.
4. Нажмите **«Играть»** — откроется окно со стримом Android и активным маппингом.

## Горячие клавиши в игре

| Клавиша | Действие |
|---|---|
| `Tab` | показать/скрыть визуальную раскладку |
| `F8` | скриншот (в «Изображения/Waydroid Stacks») |
| `F9` | начать/остановить запись геймплея (MP4, «Видео/Waydroid Stacks») |
| `F11` | полный экран |
| `Esc` | закрыть игровое окно |
| мышь | в режиме маппинга — обзор/прицеливание (виджет «Обзор») |
| ЛКМ/ПКМ | назначаются как клавиши `mouse1`, `mouse2` |
| геймпад | кнопки и стики как `pad:a`, `pad:up`, `pad:ls_right` и т.д. |

Когда в игре активно текстовое поле (ввод имени, чат), клавиатура автоматически
переключается в текстовый режим: печатайте прямо с физической клавиатуры —
экранная клавиатура Android при этом не появляется.

## Геймпады

Подключённый геймпад (XInput/DualShock/DualSense и др.) определяется
автоматически. В редакторе раскладки назначьте на виджеты клавиши вида:

- кнопки: `pad:a`, `pad:b`, `pad:x`, `pad:y`, `pad:lb`, `pad:rb`,
  `pad:lt`, `pad:rt`, `pad:start`, `pad:select`, `pad:l3`, `pad:r3`, `pad:guide`
- крестовина: `pad:up`, `pad:down`, `pad:left`, `pad:right`
- левый стик: `pad:ls_up`, `pad:ls_down`, `pad:ls_left`, `pad:ls_right`
- правый стик: `pad:rs_up`, `pad:rs_down`, `pad:rs_left`, `pad:rs_right`

## Обмен раскладками (.wsk)

Профиль кеймаппинга экспортируется в файл `.wsk`
(«Клавиатура» → значок сохранения рядом с профилем) и импортируется на любой
другой машине («Клавиатура» → «Импорт .wsk»). Формат — JSON.

## Версионирование

Проект следует [Semantic Versioning 2.0.0](https://semver.org/lang/ru/):
`MAJOR.MINOR.PATCH`.

- **MAJOR** — несовместимые изменения: формат профилей кеймаппинга, CLI, API модулей;
- **MINOR** — новая функциональность с обратной совместимостью;
- **PATCH** — исправления ошибок без изменения поведения.

Единственный источник версии — `waydroid_stacks/__init__.py` (файл `pyproject.toml`
читает её оттуда). До версии `1.0.0` формат профилей может меняться в
MINOR-релизах с автоматической миграцией.

Выпуск новой версии:

```bash
./scripts/release.sh 0.2.0
```

Скрипт обновит версию, подготовит запись в `CHANGELOG.md`, создаст commit и tag.

История изменений — [CHANGELOG.md](CHANGELOG.md).
Планы развития — [ROADMAP.md](ROADMAP.md).

## Коммерческое использование

Проект распространяется под **GPL-3.0-or-later** и использует двойное
лицензирование (dual licensing):

- **Бесплатно** — использование, изучение, изменение и распространение, в том
  числе **в коммерческих целях** (на работе, в компании, для клиентов), при
  соблюдении условий GPL-3.0: производные работы тоже должны быть открыты
  под GPL-3.0 и сохранять авторство.
- **Коммерческая лицензия** — если вы хотите встроить Waydroid Stacks в
  проприетарный (закрытый) продукт, продавать его как часть платного решения
  или использовать без обязательств GPL — требуется отдельная коммерческая
  лицензия. Связь: **[github.com/syb1v](https://github.com/syb1v)** (issues или личное сообщение).

Это значит: код открыт и свободен для сообщества, но его нельзя присвоить и
закрыть без договорённости с автором — по вопросам коммерческой интеграции
пишите по указанному контакту.

## Дорожная карта

Куда проект движется дальше (подробно — в [ROADMAP.md](ROADMAP.md)):

- **v0.2** — мультиинстанс (несколько Android-контейнеров одновременно),
  геймпады, запись геймплея, профили производительности на игру;
- **v0.3** — сверхнизкая задержка: прямой захват поверхности Android без
  H.264-кодирования (DMA-BUF/screencopy), инъекция через uinput без adb,
  инерционный мышиный обзор;
- **v0.4** — экосистема: магазин готовых раскладок, интеграция с магазинами
  APK, резервные копии игровых данных;
- **v1.0** — стабильный формат профилей, пакеты (AUR/Flatpak), интеграция
  со Steam/GameMode, автотесты и CI.

## Архитектура

```
waydroid_stacks/
├── core/
│   ├── adb.py        # обёртка adb (shell, пакеты, скриншоты, install)
│   ├── waydroid.py   # управление сессией/контейнером Waydroid
│   ├── scrcpy.py     # scrcpy-server: управляющий сокет (touch/key), видеосокет
│   ├── nativeinput.py# нативная инъекция ввода через evdev-FIFO EventHub
│   ├── imebridge.py  # тихий IME-мост: текст в поля Android без клавиатуры
│   ├── video.py      # декодирование H.264 (GStreamer) → GTK4 Picture
│   ├── gamepad.py    # движок: клавиатура/мышь → мультитач Android
│   ├── keymap.py     # профили кеймаппинга (JSON)
│   └── packages.py   # каталог приложений, иконки, ярлыки
├── pages/            # library / keymapper / play / settings
├── app.py            # Adw.Application
└── window.py         # главное окно
ime/                        # исходники тихой IME (Android, Java)
third_party/scrcpy-server   # сервер scrcpy v3.x (Apache-2.0), запускается на Android
third_party/wdsime.apk      # собранная тихая IME (см. scripts/build_ime.sh)
```

Ввод передаётся на устройство через **control-сокет scrcpy-server**
(big-endian протокол `INJECT_TOUCH_EVENT`/`INJECT_KEYCODE`), что даёт
мультитач и низкую задержку. Видео идёт по отдельному сокету и декодируется
аппаратно (VA-API) прямо в GTK-виджет.

## Решение проблем

- **Нет интернета в Android**: выполните «Настройки → Сетевые правила» (ufw).
- **Игра не запускается / вылетает**: установите libndk (ARM-трансляция) через
  «Настройки → ARM-трансляция».
- **Нет видеопотока**: установите `gst-plugin-va` (аппаратный декодер) —
  иначе используется программный `avdec_h264`.
- **Чёрный экран в игровом режиме**: убедитесь, что сессия Waydroid запущена
  (`waydroid status`), и обновите Android до свежего состояния.

## Релизы и CI

Все пакеты собираются и публикуются автоматически в **GitHub Actions**
(`.github/workflows/release.yml`) при пуше тега `vX.Y.Z`:

| Артефакт | Как собирается |
|---|---|
| `waydroid-stacks-X.Y.Z.tar.gz` | исходники (git archive) |
| `waydroid-stacks_X.Y.Z_all.deb` | нативный `dpkg-deb` на Ubuntu 24.04 |
| `waydroid-stacks-X.Y.Z-1.noarch.rpm` | `rpmbuild` на Ubuntu 24.04 |
| `waydroid-stacks-X.Y.Z-x86_64.AppImage` | `appimage-builder` (Ubuntu 24.04) |
| AUR `waydroid-stacks` | PKGBUILD + `.SRCINFO`, push в AUR |

Проверить сборку без публикации: **Actions → Release → Run workflow**
с `tag: master` и включённым `dry_run`. После успешной проверки выпуск:

```bash
./scripts/release.sh 0.3.1 "краткое описание"
git push --follow-tags
```

### Публикация в AUR (одноразовая настройка)

1. Создайте SSH-ключ и добавьте **публичный** ключ в профиль
   [aur.archlinux.org](https://aur.archlinux.org/account/):
   ```bash
   ssh-keygen -f ~/.ssh/aur -N ""
   cat ~/.ssh/aur.pub   # вставить на сайте AUR
   ```
2. Добавьте **приватный** ключ в секреты GitHub-репозитория
   (Settings → Secrets and variables → Actions):
   - `AUR_SSH_PRIVATE_KEY` — содержимое `~/.ssh/aur` (обязательно);
   - `AUR_USERNAME`, `AUR_EMAIL` — для коммитов AUR (опционально).
3. При первом пуше CI создаст AUR-пакет (пустой репозиторий создаётся
   автоматически при клонировании по SSH).

Пока секрет не задан, шаг AUR пропускается с предупреждением — остальные
пакеты публикуются как обычно.

## Лицензия

GPL-3.0-or-later. `third_party/scrcpy-server` — компонент
[scrcpy](https://github.com/Genymobile/scrcpy) (Genymobile, Apache License 2.0).
