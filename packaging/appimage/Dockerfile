# Образ для сборки AppImage: appimage-builder на Ubuntu 24.04
# (совпадает с целевым дистрибутивом рецепта — noble)
FROM ubuntu:24.04

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv \
        patchelf desktop-file-utils zsync file e2fsprogs \
        libfuse2 squashfs-tools fakeroot binutils \
        libgdk-pixbuf2.0-bin libglib2.0-bin gtk-update-icon-cache \
        git ca-certificates wget \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --break-system-packages --no-cache-dir appimage-builder && \
    ln -s /usr/lib/x86_64-linux-gnu/gdk-pixbuf-2.0/gdk-pixbuf-query-loaders /usr/local/bin/gdk-pixbuf-query-loaders

WORKDIR /build
ENTRYPOINT []
CMD ["appimage-builder", "--help"]
