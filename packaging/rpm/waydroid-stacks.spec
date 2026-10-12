%global debug_package %{nil}

Name:           waydroid-stacks
Version:        0.3.0
Release:        1%{?dist}
Summary:        BlueStacks-подобная оболочка для Waydroid
License:        GPL-3.0-or-later
URL:            https://github.com/syb1v/waydroid-stacks
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

Requires:       python3 >= 3.10
Requires:       python3-gobject
Requires:       gtk4
Requires:       libadwaita
Requires:       python3-gstreamer1
Requires:       gstreamer1-plugins-base
Requires:       gstreamer1-plugins-good
Recommends:     gstreamer1-plugins-bad-free
Recommends:     gstreamer1-libav
Recommends:     android-tools
Recommends:     python3-pyaxmlparser

%description
Библиотека приложений, встроенный игровой режим (scrcpy + GStreamer/VA-API),
кеймаппер клавиатуры/мыши и ввод текста в поля Android без экранной
клавиатуры. Требует установленных Waydroid и adb.

%prep
%autosetup -n %{name}-%{version}

%build
# нет сборки — Python-приложение

%install
install -d %{buildroot}%{_datadir}/waydroid-stacks
cp -a waydroid_stacks %{buildroot}%{_datadir}/waydroid-stacks/
cp -a third_party %{buildroot}%{_datadir}/waydroid-stacks/
find %{buildroot}%{_datadir}/waydroid-stacks -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

install -Dm755 /dev/stdin %{buildroot}%{_bindir}/waydroid-stacks <<'EOF'
#!/bin/sh
DATADIR="/usr/share/waydroid-stacks"
export PYTHONPATH="$DATADIR${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m waydroid_stacks "$@"
EOF

install -Dm644 data/io.github.syb1v.WaydroidStacks.desktop \
    %{buildroot}%{_datadir}/applications/io.github.syb1v.WaydroidStacks.desktop
install -Dm644 data/icons/io.github.syb1v.WaydroidStacks.svg \
    %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/io.github.syb1v.WaydroidStacks.svg
install -Dm644 LICENSE \
    %{buildroot}%{_datadir}/licenses/%{name}/LICENSE

%post
update-desktop-database -q %{_datadir}/applications || :
gtk-update-icon-cache -q %{_datadir}/icons/hicolor || :

%postun
update-desktop-database -q %{_datadir}/applications || :

%files
%{_datadir}/licenses/%{name}/LICENSE
%{_bindir}/waydroid-stacks
%{_datadir}/waydroid-stacks
%{_datadir}/applications/io.github.syb1v.WaydroidStacks.desktop
%{_datadir}/icons/hicolor/scalable/apps/io.github.syb1v.WaydroidStacks.svg

%changelog
* Mon Oct 12 2026 syb1v <108201690+syb1v@users.noreply.github.com> - 0.3.0-1
- Первый публичный релиз: нативная инъекция ввода, инерционный обзор,
  тихая IME, пакеты для всех дистрибутивов.
