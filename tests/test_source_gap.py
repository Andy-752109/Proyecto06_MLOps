"""Watchdog de la fuente y eventos source_gap (escenario adicional S1), con datos sintéticos."""
import threading
import time
from pathlib import Path

from monitor.config import load_config
from monitor.metrics import compute_window_metrics, event_is_traceable
from monitor.source import _END, SourceGap, SourceStats, VideoStreamSource

CFG = load_config()
ROOT = Path(__file__).resolve().parents[1]


def fake_source(gap_after_s=1.0):
    """Fuente sin hilo de captura: la prueba alimenta la cola a mano (5 fps nominales)."""
    import queue
    s = VideoStreamSource.__new__(VideoStreamSource)
    s.cfg = {"sample_every": 2, "watchdog": {"gap_after_s": gap_after_s}}
    s.q = queue.Queue()
    s.stats = SourceStats(native_fps=10.0)
    return s


def feed(src, pattern):
    """pattern: lista de (espera_s, item) que se ponen en la cola desde otro hilo."""
    def run():
        for wait, item in pattern:
            time.sleep(wait)
            src.q.put(item)
    threading.Thread(target=run, daemon=True).start()


def test_no_gaps_while_frames_arrive_on_time():
    src = fake_source()
    feed(src, [(0.2, f"f{i}") for i in range(8)] + [(0.0, _END)])
    items = list(src.frames())
    assert items == [f"f{i}" for i in range(8)] and src.stats.gaps == 0


def test_silence_becomes_one_gap_per_expected_frame():
    src = fake_source(gap_after_s=1.0)
    feed(src, [(0.0, "f0"), (1.65, "f1"), (0.0, _END)])
    items = list(src.frames())
    gaps = [x for x in items if isinstance(x, SourceGap)]
    assert items[0] == "f0" and items[-1] == "f1"
    # 1.65 s de silencio a 0.2 s por frame esperado: 8 huecos (los del periodo de gracia incluidos)
    assert 7 <= len(gaps) <= 8 and [g.slot for g in gaps] == list(range(1, len(gaps) + 1))
    assert src.stats.gaps == len(gaps)


def test_without_watchdog_silence_is_not_reported():
    src = fake_source(gap_after_s=None)
    feed(src, [(0.0, "f0"), (0.6, "f1"), (0.0, _END)])
    assert list(src.frames()) == ["f0", "f1"]


def gap_event(i, **over):
    e = {"event_id": f"t-e{i:03d}", "run_id": "t", "frame_id": None, "frame_index": None,
         "captured_at": "2026-01-01T00:00:00.000Z", "inferred_at": "2026-01-01T00:00:00.000Z",
         "source_id": "s", "task": "detection", "model_ref": "m", "model_sha256": None,
         "config_ref": "cfg-x", "status": "source_gap", "error": "sin frames de la fuente",
         "window_id": "t-w000", "n_detections": 0, "n_low": 0, "n_doubt": 0, "n_accepted": 0,
         "max_score": None, "frame_zone": None, "inference_ms": None, "image_ref": None,
         "detections": []}
    e.update(over)
    return e


def test_gap_event_traceability():
    assert event_is_traceable(gap_event(0), {"cfg-x"}, ROOT) == (True, [])
    ok, probs = event_is_traceable(gap_event(0, error=None), {"cfg-x"}, ROOT)
    assert not ok and "error_sin_detalle" in probs
    ok, probs = event_is_traceable(gap_event(0, image_ref="x.jpg"), {"cfg-x"}, ROOT)
    assert not ok and "hueco_incoherente" in probs
    # un frame real sigue necesitando frame_id
    ok, probs = event_is_traceable(gap_event(0, status="no_detections"), {"cfg-x"}, ROOT)
    assert not ok and "frame_id" in probs


def test_window_of_gaps_has_no_data_not_zero():
    evs = [gap_event(i) for i in range(20)]
    res = [{"rss_mb": 300.0}] * 20
    m = compute_window_metrics(evs, res, "abc", {"cfg-x"}, 1, CFG["windows"], ROOT)
    for mid in ("g1_inference_ms_p95", "g2_processing_fps", "g4_low_conf_prop", "g6_model_version_match"):
        assert m[mid]["value"] is None and m[mid]["status"] == "no_data", mid
    assert m["g5_trace_coverage"]["value"] == 1.0
    assert m["g3_rss_mb_max"]["value"] == 300.0 and m["g7_active_alerts"]["value"] == 1
