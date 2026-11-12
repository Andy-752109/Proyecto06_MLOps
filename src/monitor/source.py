"""Fuente visual: reproduce un archivo de video como stream.

Un hilo de captura lee frames al ritmo nativo del archivo (playback=realtime),
aplica la política de muestreo (1 de cada `sample_every`) y entrega los frames
seleccionados a una cola acotada. Si la cola está llena el frame se descarta por
saturación. Todos los descartes se cuentan por motivo.
"""
import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass
class Frame:
    frame_index: int          # índice del frame en el archivo
    image: np.ndarray
    captured_at: str          # ISO UTC al leer el frame
    captured_mono: float      # time.perf_counter() al leer el frame
    pts_s: float              # posición en el video (s)


@dataclass
class SourceStats:
    read: int = 0
    read_failures: int = 0
    selected: int = 0
    dropped: dict = field(default_factory=lambda: {"sampling": 0, "saturation": 0})
    native_fps: float = 0.0
    first_read_mono: float | None = None
    last_read_mono: float | None = None


_END = object()


class VideoStreamSource:
    def __init__(self, src_cfg: dict, root: Path):
        self.cfg = src_cfg
        self.path = root / src_cfg["path"]
        if not self.path.exists():
            raise FileNotFoundError(f"fuente no encontrada: {self.path} (ejecuta scripts/prepare_inputs.py)")
        self.q: queue.Queue = queue.Queue(maxsize=src_cfg.get("queue_maxsize", 4))
        self.stats = SourceStats()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> "VideoStreamSource":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()

    def frames(self):
        while True:
            item = self.q.get()
            if item is _END:
                return
            yield item

    def _run(self) -> None:
        cap = cv2.VideoCapture(str(self.path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 10.0
        self.stats.native_fps = fps
        start = self.cfg.get("start_frame") or 0
        end = self.cfg.get("end_frame")
        every = max(1, int(self.cfg.get("sample_every", 1)))
        realtime = self.cfg.get("playback", "realtime") == "realtime"
        if start:
            cap.set(cv2.CAP_PROP_POS_FRAMES, start)
        idx = start
        t0 = time.perf_counter()
        try:
            while not self._stop.is_set() and (end is None or idx < end):
                if realtime:  # ritmo nativo: el frame k no se lee antes de t0 + k/fps
                    delay = t0 + (idx - start) / fps - time.perf_counter()
                    if delay > 0:
                        time.sleep(delay)
                ok, img = cap.read()
                now = time.perf_counter()
                if not ok:
                    # fin del archivo o fallo de lectura/decodificación
                    total = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                    if total and idx < total:
                        self.stats.read_failures += 1
                        idx += 1
                        continue
                    break
                self.stats.read += 1
                self.stats.first_read_mono = self.stats.first_read_mono or now
                self.stats.last_read_mono = now
                if (idx - start) % every != 0:
                    self.stats.dropped["sampling"] += 1
                else:
                    fr = Frame(idx, img, utc_now(), now, idx / fps)
                    try:
                        self.q.put_nowait(fr)
                        self.stats.selected += 1
                    except queue.Full:
                        self.stats.dropped["saturation"] += 1
                idx += 1
        finally:
            cap.release()
            self.q.put(_END)
