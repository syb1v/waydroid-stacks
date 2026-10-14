/*
 * Waydroid Stacks: снимок кадра из wlroots-композитора (zwlr_screencopy).
 *
 * Подключается к текущему WAYLAND_DISPLAY, снимает первый выход и сохраняет
 * PPM (P6). Использование:
 *
 *     waydroid-stacks-screencap out.ppm
 *
 * Сборка: tools/build-scap.sh
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <wayland-client.h>
#include "screencopy.h"

static struct wl_shm *shm;
static struct wl_output *output;
static struct zwlr_screencopy_manager_v1 *scm;
static struct wl_buffer *cur_buffer;
static struct wl_shm_pool *cur_pool;
static void *cur_data;
static unsigned char *cur_pixels;
static uint32_t cur_size;
static int cur_w, cur_h, cur_stride;
static int ready = 0, failed = 0;

static void on_buffer(void *d, struct zwlr_screencopy_frame_v1 *f, uint32_t format,
                      uint32_t width, uint32_t height, uint32_t stride) {
    cur_w = width; cur_h = height; cur_stride = stride;
    cur_size = (uint32_t)stride * height;
    char tmpl[] = "/tmp/scap-XXXXXX";
    int fd = mkstemp(tmpl);
    unlink(tmpl);
    if (fd < 0 || ftruncate(fd, cur_size) < 0) { perror("mkstemp/ftruncate"); exit(1); }
    cur_data = mmap(NULL, cur_size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    cur_pool = wl_shm_create_pool(shm, fd, cur_size);
    cur_buffer = wl_shm_pool_create_buffer(cur_pool, 0, width, height, stride, format);
    close(fd);
    zwlr_screencopy_frame_v1_copy(f, cur_buffer);
}
static void on_ready(void *d, struct zwlr_screencopy_frame_v1 *f, uint32_t a, uint32_t b, uint32_t c) {
    cur_pixels = malloc(cur_size);
    memcpy(cur_pixels, cur_data, cur_size);
    ready = 1;
}
static void on_failed(void *d, struct zwlr_screencopy_frame_v1 *f) { failed = 1; }
static void on_flags(void *d, struct zwlr_screencopy_frame_v1 *f, uint32_t flags) {}
static void on_damage(void *d, struct zwlr_screencopy_frame_v1 *f, uint32_t x, uint32_t y, uint32_t w, uint32_t h) {}
static void on_linux_dmabuf(void *d, struct zwlr_screencopy_frame_v1 *f, uint32_t format, uint32_t width, uint32_t height) {}
static void on_buffer_done(void *d, struct zwlr_screencopy_frame_v1 *f) {}
static const struct zwlr_screencopy_frame_v1_listener f_listener = {
    .buffer = on_buffer, .flags = on_flags, .ready = on_ready, .failed = on_failed,
    .damage = on_damage, .linux_dmabuf = on_linux_dmabuf, .buffer_done = on_buffer_done,
};

static void reg_global(void *d, struct wl_registry *r, uint32_t name, const char *iface, uint32_t ver) {
    if (!strcmp(iface, "wl_shm")) shm = wl_registry_bind(r, name, &wl_shm_interface, 1);
    else if (!strcmp(iface, "wl_output") && !output) output = wl_registry_bind(r, name, &wl_output_interface, ver < 4 ? ver : 4);
    else if (!strcmp(iface, "zwlr_screencopy_manager_v1")) scm = wl_registry_bind(r, name, &zwlr_screencopy_manager_v1_interface, ver < 3 ? ver : 3);
}
static void reg_remove(void *d, struct wl_registry *r, uint32_t n) {}
static const struct wl_registry_listener reg_listener = { reg_global, reg_remove };

int main(int argc, char **argv) {
    const char *outpath = argc > 1 ? argv[1] : "screencap.ppm";
    struct wl_display *display = wl_display_connect(NULL);
    if (!display) { fprintf(stderr, "cannot connect (WAYLAND_DISPLAY?)\n"); return 1; }
    struct wl_registry *reg = wl_display_get_registry(display);
    wl_registry_add_listener(reg, &reg_listener, NULL);
    wl_display_roundtrip(display);
    if (!shm || !scm || !output) {
        fprintf(stderr, "missing globals shm=%p scm=%p out=%p (нужен wlroots-композитор с zwlr_screencopy)\n",
                (void *)shm, (void *)scm, (void *)output);
        return 1;
    }
    struct zwlr_screencopy_frame_v1 *frame = zwlr_screencopy_manager_v1_capture_output(scm, 0, output);
    zwlr_screencopy_frame_v1_add_listener(frame, &f_listener, NULL);
    while (!ready && !failed && wl_display_dispatch(display) != -1) {}
    if (failed || !ready) { fprintf(stderr, "capture failed\n"); return 1; }
    FILE *fp = fopen(outpath, "wb");
    if (!fp) { perror("fopen"); return 1; }
    fprintf(fp, "P6\n%d %d\n255\n", cur_w, cur_h);
    for (int i = 0; i < cur_h; i++)
        for (int j = 0; j < cur_w; j++) {
            unsigned char *p = (unsigned char *)cur_pixels + i * cur_stride + j * 4;
            unsigned char rgb[3] = { p[2], p[1], p[0] };  /* XRGB8888 -> RGB */
            fwrite(rgb, 1, 3, fp);
        }
    fclose(fp);
    printf("saved %s (%dx%d)\n", outpath, cur_w, cur_h);
    return 0;
}
