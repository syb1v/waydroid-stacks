"""Видеоплеер H.264 (scrcpy) на GStreamer для GTK4."""
from __future__ import annotations

import threading
from typing import Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gst", "1.0")

from gi.repository import Gdk, GLib, Gst, Gtk  # noqa: E402

from .scrcpy import ScrcpySession  # noqa: E402


class VideoStream:
    """Декодирует H.264-поток scrcpy и отображает в Gtk.Picture.

    Использует gtk4paintablesink, если доступен, иначе appsink с MemoryTexture.
    """

    def __init__(self):
        if not Gst.is_initialized():
            Gst.init(None)
        self.picture = Gtk.Picture()
        self.picture.set_can_shrink(True)
        self.picture.set_hexpand(True)
        self.picture.set_vexpand(True)
        self.picture.set_content_fit(Gtk.ContentFit.CONTAIN)

        self._pipeline: Optional[Gst.Pipeline] = None
        self._appsrc: Optional[Gst.Element] = None
        self._appsink: Optional[Gst.Element] = None
        self._paintable_sink = None
        self._using_paintable = False
        self._last_texture = None
        self._painted = False
        self._video_size = (0, 0)

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        if Gst.ElementFactory.find("gtk4paintablesink"):
            pipeline_desc = (
                "appsrc name=src is-live=true do-timestamp=true format=time ! "
                "h264parse ! vah264dec ! videoconvert ! "
                "gtk4paintablesink name=sink sync=false"
            )
            self._using_paintable = True
        else:
            pipeline_desc = (
                "appsrc name=src is-live=true do-timestamp=true format=time ! "
                "h264parse ! vah264dec ! videoconvert ! "
                "video/x-raw,format=RGBA ! "
                "appsink name=sink max-buffers=2 drop=true sync=false emit-signals=true"
            )
            self._using_paintable = False

        try:
            self._pipeline = Gst.parse_launch(pipeline_desc)
        except GLib.Error:
            # fallback на программный декодер
            pipeline_desc = pipeline_desc.replace("vah264dec", "avdec_h264")
            self._pipeline = Gst.parse_launch(pipeline_desc)

        self._appsrc = self._pipeline.get_by_name("src")
        sink = self._pipeline.get_by_name("sink")
        self._appsink = sink

        if self._using_paintable:
            paintable = sink.get_property("paintable")
            self.picture.set_paintable(paintable)
        else:
            sink.connect("new-sample", self._on_sample)
        self._pipeline.set_state(Gst.State.PLAYING)

    # ------------------------------------------------------------------ video
    def attach(self, session: ScrcpySession) -> None:
        self._build()
        self._video_size = session.video_size
        session.stream_video(self.push_packet)

    def push_packet(self, data: bytes) -> None:
        if not self._appsrc:
            return
        buf = Gst.Buffer.new_allocate(None, len(data), None)
        buf.fill(0, data)
        self._appsrc.emit("push-buffer", buf)

    def _on_sample(self, sink) -> Gst.FlowReturn:
        sample = sink.emit("pull-sample")
        if not sample:
            return Gst.FlowReturn.OK
        buf = sample.get_buffer()
        caps = sample.get_caps()
        if not caps or caps.get_size() == 0:
            return Gst.FlowReturn.OK
        s = caps.get_structure(0)
        width = s.get_value("width")
        height = s.get_value("height")
        ok, mapinfo = buf.map(Gst.MapFlags.READ)
        if ok:
            data = bytes(mapinfo.data)
            buf.unmap(mapinfo)
            GLib.idle_add(self._set_texture, data, width, height)
        return Gst.FlowReturn.OK

    def _set_texture(self, data: bytes, width: int, height: int) -> bool:
        b = GLib.Bytes.new(data)
        texture = Gdk.MemoryTexture.new(width, height, Gdk.MemoryFormat.R8G8B8A8,
                                        b, width * 4)
        self.picture.set_paintable(texture)
        return False

    # ------------------------------------------------------------------- stop
    def stop(self) -> None:
        if self._pipeline:
            self._pipeline.set_state(Gst.State.NULL)
            self._pipeline = None
            self._appsrc = None
            self._appsink = None
