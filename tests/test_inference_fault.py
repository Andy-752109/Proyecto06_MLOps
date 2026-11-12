"""Reacción ante errores consecutivos de inferencia (escenario adicional S3), sin cargar el modelo."""
import monitor.pipeline as pl


class FakeDetector:
    loads = 0

    def __init__(self, model_cfg, root):
        FakeDetector.loads += 1
        self.sha256 = model_cfg["sha256"]


def make_monitor(reload_after):
    m = pl.Monitor.__new__(pl.Monitor)
    m.cfg = {"model": {"sha256": "a" * 64}}
    m.reload_after = reload_after
    m.consec_errors, m.first_error, m.n_reloads, m.detector_events = 0, None, 0, []
    return m


def test_reload_every_k_errors_and_single_recovery(monkeypatch):
    monkeypatch.setattr(pl, "PersonDetector", FakeDetector)
    FakeDetector.loads = 0
    m = make_monitor(reload_after=3)
    for i in range(7):
        m._track_inference("error", 500 + 2 * i, f"e{i}", "InjectedInferenceError: x")
    m._track_inference("ok", 514, "e7", None)
    m._track_inference("no_detections", 516, "e8", None)
    kinds = [(e["kind"], e.get("after_errors", e.get("consecutive_errors"))) for e in m.detector_events]
    assert kinds == [("inference_failed", None), ("detector_reloaded", 3), ("detector_reloaded", 6),
                     ("inference_recovered", 7)]
    assert FakeDetector.loads == 2 and m.n_reloads == 2 and m.consec_errors == 0
    assert all(e["sha256_match"] for e in m.detector_events if e["kind"] == "detector_reloaded")
    assert m.detector_events[-1]["frame_index"] == 514 and m.detector_events[-1]["reloads"] == 2


def test_without_errors_nothing_is_logged(monkeypatch):
    monkeypatch.setattr(pl, "PersonDetector", FakeDetector)
    m = make_monitor(reload_after=None)
    for i in range(5):
        m._track_inference("ok", i, f"e{i}", None)
    assert m.detector_events == [] and m.n_reloads == 0
