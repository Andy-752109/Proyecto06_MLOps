"""Fuente visual: reproduce un archivo de video como stream.

Un hilo de captura lee frames al ritmo nativo del archivo (playback=realtime),
aplica la política de muestreo (1 de cada `sample_every`) y entrega los frames
seleccionados a una cola acotada. Si la cola está llena el frame se descarta por
saturación. Todos los descartes se cuentan por motivo.

Opcionalmente (solo escenarios adicionales):
- `fault_injection.outage`: en `at_frame` la fuente pierde la conexión durante
  `duration_s`. Reintenta cada `reconnect_every_s`; los intentos dentro del corte fallan.
  Al reconectar continúa en la posición "en vivo": los frames emitidos durante el corte
  se pierden (descarte `outage`). Cada transición queda en `stats.events`.
- `watchdog.gap_after_s`: `frames()` entrega un `SourceGap` por cada frame esperado
  (cada sample_every/fps s) que no llegó, una vez que el silencio supera ese tiempo.
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
class SourceGap:
    """Frame esperado que no llegó (detectado por el watchdog)."""
    detected_at: str          # ISO UTC al detectarlo
    detected_mono: float
    silent_s: float           # segundos sin frames al detectarlo
    slot: int                 # número de hueco dentro del silencio actual (1, 2, ...)


@dataclass
class SourceStats:
    read: int = 0
    read_failures: int = 0
    selected: int = 0
    dropped: dict = field(default_factory=lambda: {"sampling": 0, "saturation": 0})
    gaps: int = 0
    events: list = field(default_factory=list)  # transiciones de conexión de la fuente
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

    def log(self, kind: str, **detail) -> None:
        self.stats.events.append({"ts": utc_now(), "kind": kind, **detail})

    def frames(self):
        gap_after = (self.cfg.get("watchdog") or {}).get("gap_after_s")
        if not gap_after:
            while True:
                item = self.q.get()
                if item is _END:
                    return
                yield item
        interval = max(1, int(self.cfg.get("sample_every", 1))) / (self.stats.native_fps or 10.0)
        last, emitted = time.perf_counter(), 0
        while True:
            try:
                item = self.q.get(timeout=interval)
            except queue.Empty:
                silent = time.perf_counter() - last
                if silent >= gap_after:  # incluye los huecos del periodo de gracia
                    for _ in range(int(silent / interval) - emitted):
                        emitted += 1
                        self.stats.gaps += 1
                        yield SourceGap(utc_now(), time.perf_counter(), round(silent, 3), emitted)
                continue
            if item is _END:
                return
            last, emitted = time.perf_counter(), 0
            yield item

    def _outage(self, cap, idx: int, fps: float, t0: float, start: int):
        """Simula la caída de la conexión y la reconexión. Devuelve (cap, idx)."""
        o = self.cfg["fault_injection"]["outage"]
        lost_at = time.perf_counter()
        cap.release()
        self.log("connection_lost", frame_index=idx, simulated=True)
        attempt = 0
        while not self._stop.is_set():
            time.sleep(o["reconnect_every_s"])
            attempt += 1
            if time.perf_counter() - lost_at < o["duration_s"]:
                self.log("reconnect_failed", attempt=attempt, simulated=True)
                continue
            cap = cv2.VideoCapture(str(self.path))
            # posición en vivo: lo que se emitió mientras no había conexión se perdió
            live = start + int((time.perf_counter() - t0) * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, live)
            self.stats.dropped["outage"] = self.stats.dropped.get("outage", 0) + (live - idx)
            self.log("reconnected", attempt=attempt, frame_index=live, frames_lost=live - idx,
                     outage_s=round(time.perf_counter() - lost_at, 3))
            return cap, live
        return cap, idx

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
        outage_at = ((self.cfg.get("fault_injection") or {}).get("outage") or {}).get("at_frame")
        t0 = time.perf_counter()
        try:
            while not self._stop.is_set() and (end is None or idx < end):
                if idx == outage_at:
                    outage_at = None
                    cap, idx = self._outage(cap, idx, fps, t0, start)
                    continue
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
