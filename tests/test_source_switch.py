"""Cambio de entrada alineado (escenario adicional S2) con dos videos sintéticos."""
import cv2
import numpy as np

from monitor.source import VideoStreamSource


def write_video(path, value, n=10):
    w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (32, 32))
    for _ in range(n):
        w.write(np.full((32, 32, 3), value, np.uint8))
    w.release()


def test_switch_takes_same_index_from_alternate_file(tmp_path):
    write_video(tmp_path / "a.avi", 0)
    write_video(tmp_path / "b.avi", 255)
    cfg = {"path": "a.avi", "playback": "fast", "sample_every": 1, "queue_maxsize": 100,
           "start_frame": 2, "end_frame": None,
           "switch": {"path": "b.avi", "from_frame": 4, "to_frame": 7}}
    src = VideoStreamSource(cfg, tmp_path).start()
    frames = list(src.frames())
    got = {f.frame_index: "b" if f.image.mean() > 128 else "a" for f in frames}
    assert got == {2: "a", 3: "a", 4: "b", 5: "b", 6: "b", 7: "a", 8: "a", 9: "a"}
    assert [(e["kind"], e["frame_index"]) for e in src.stats.events] == [("switch_on", 4), ("switch_off", 7)]
