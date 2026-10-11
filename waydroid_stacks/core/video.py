"""Видеоплеер H.264 (scrcpy) на GStreamer для GTK4."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gst", "1.0")

from gi.repository import Gdk, GLib, Gst, Gtk  # noqa: E402

from .scrcpy import ScrcpySession  # noqa: E402


class VideoStream:
    """Декодирует H.264-поток scrcpy и отображает в Gtk.Picture.

    Использует gtk4paintablesink, если доступен, иначе appsink с MemoryTexture.
    Поддерживает запись геймплея без перекодирования (tee → mp4mux).
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
        self._tee: Optional[Gst.Element] = None
        self._recbin: Optional[Gst.Bin] = None
        self._rec_pad = None
        self._rec_path: Optional[Path] = None
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
                "h264parse ! tee name=t "
                "t. ! queue ! vah264dec ! videoconvert ! "
                "gtk4paintablesink name=sink sync=false"
            )
            self._using_paintable = True
        else:
            pipeline_desc = (
                "appsrc name=src is-live=true do-timestamp=true format=time ! "
                "h264parse ! tee name=t "
                "t. ! queue ! vah264dec ! videoconvert ! "
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
        self._tee = self._pipeline.get_by_name("t")
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

    # -------------------------------------------------------------- recording
    @property
    def is_recording(self) -> bool:
        return self._recbin is not None

    @property
    def recording_path(self) -> Optional[Path]:
        return self._rec_path

    def start_recording(self, path: Path) -> bool:
        """Начинает запись геймплея в MP4 без перекодирования."""
        if self._recbin or not self._pipeline or not self._tee:
            return False

        recbin = Gst.Bin.new("recbin")
        queue = Gst.ElementFactory.make("queue")
        parse = Gst.ElementFactory.make("h264parse")
        mux = Gst.ElementFactory.make("mp4mux")
        sink = Gst.ElementFactory.make("filesink")
        if not all((queue, parse, mux, sink)):
            return False
        parse.set_property("config-interval", -1)
        mux.set_property("faststart", True)
        sink.set_property("location", str(path))
        sink.set_property("sync", False)

        for element in (queue, parse, mux, sink):
            recbin.add(element)
        queue.link(parse)
        parse.link(mux)
        mux.link(sink)
        recbin.add_pad(Gst.GhostPad.new("sink", queue.get_static_pad("sink")))

        self._pipeline.add(recbin)
        recbin.sync_state_with_parent()

        rec_pad = self._tee.request_pad_simple("src_%u")
        if not rec_pad or rec_pad.link(recbin.get_static_pad("sink")) != Gst.PadLinkReturn.OK:
            recbin.set_state(Gst.State.NULL)
            self._pipeline.remove(recbin)
            return False

        self._recbin = recbin
        self._rec_pad = rec_pad
        self._rec_path = Path(path)
        return True

    def stop_recording(self, wait: bool = False) -> Optional[Path]:
        """Останавливает запись, финализирует MP4 (EOS + ожидание)."""
        if not self._recbin:
            return None
        recbin, rec_pad, path = self._recbin, self._rec_pad, self._rec_path
        self._recbin = None
        self._rec_pad = None
        self._rec_path = None

        recbin.send_event(Gst.Event.new_eos())

        def finalize():
            bus = self._pipeline.get_bus() if self._pipeline else None
            if bus:
                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline:
                    msg = bus.timed_pop_filtered(
                        200 * Gst.MSECOND,
                        Gst.MessageType.EOS | Gst.MessageType.ERROR)
                    if msg is not None:
                        break
            try:
                if self._tee and rec_pad:
                    self._tee.release_request_pad(rec_pad)
                recbin.set_state(Gst.State.NULL)
                if self._pipeline:
                    self._pipeline.remove(recbin)
            except Exception:  # noqa: BLE001
                pass

        t = threading.Thread(target=finalize, daemon=True)
        t.start()
        if wait:
            t.join(timeout=6)
        return path

    # ------------------------------------------------------------------- stop
    def stop(self, wait: bool = False) -> None:
        if self._recbin:
            self.stop_recording(wait=wait)
        if self._pipeline:
            self._pipeline.set_state(Gst.State.NULL)
            self._pipeline = None
            self._appsrc = None
            self._appsink = None
            self._tee = None
