"""Pruebas de lógica con datos sintéticos. Complementan, no sustituyen, C1/C2 (inferencia real)."""
from pathlib import Path

import pytest

from monitor.config import load_config
from monitor.metrics import compute_window_metrics, percentile_nearest_rank
from monitor.policy import frame_summary, zone_for
from monitor.rules import RuleEngine, window_state

CFG = load_config()
REF = {"low_prop": 0.18}
WCFG = CFG["windows"]


@pytest.mark.parametrize("score,zone", [
    (0.0, "low"), (0.3999, "low"), (0.40, "doubt"), (0.6999, "doubt"), (0.70, "accepted"),
    (1.0, "accepted"), (None, None)])
def test_zone_boundaries(score, zone):
    assert zone_for(score, 0.40, 0.70) == zone


def test_frame_without_detections_has_no_score():
    s = frame_summary([], 0.40, 0.70)
    assert s["n_detections"] == 0 and s["max_score"] is None and s["frame_zone"] is None


def test_config_rejects_bad_thresholds(tmp_path):
    bad = Path("config/monitor.yaml").read_text().replace("lower: 0.40", "lower: 0.80")
    p = tmp_path / "m.yaml"
    p.write_text(bad)
    with pytest.raises(ValueError):
        load_config(p)


def win(i, n_valid=20, n_dets=60, n_low=10, run="t"):
    w = {"window_id": f"{run}-w{i:03d}", "run_id": run, "n_valid": n_valid, "n_dets": n_dets,
         "n_low": n_low, "low_prop": n_low / n_dets if n_dets else None, "end_at": f"T{i:03d}",
         "config_ref": "cfg-x", "event_ids": [f"{run}-e{i:03d}"]}
    w["state"] = window_state(w, WCFG)
    return w


def outcomes(engine, w):
    evals, _, _ = engine.evaluate(w)
    return {e["rule_id"]: e["outcome"] for e in evals}


def test_insufficient_window_is_not_normal():
    w = win(0, n_valid=20, n_dets=5, n_low=5)  # 100 % bajas, pero solo 5 detecciones
    assert w["state"] == "insufficient"
    o = outcomes(RuleEngine(CFG["alerts"], REF), w)
    assert o["baja-confianza-v1"] == "insufficient_evidence"
    assert o["cambio-sostenido-v1"] == "insufficient_evidence"


def test_low_confidence_fires_then_resolves():
    e = RuleEngine(CFG["alerts"], REF)
    assert outcomes(e, win(0, n_low=30))["baja-confianza-v1"] == "fired"         # 0.50
    assert outcomes(e, win(1, n_low=30))["baja-confianza-v1"] == "continuing"
    assert outcomes(e, win(2, n_dets=5, n_low=0))["baja-confianza-v1"] == "insufficient_evidence"
    assert e.active_count >= 1  # una ventana insuficiente no resuelve
    assert outcomes(e, win(3, n_low=6))["baja-confianza-v1"] == "resolved"        # 0.10


def test_sustained_rule_needs_three_consecutive_eligible_windows():
    e = RuleEngine(CFG["alerts"], REF)
    # delta = 0.35 - 0.18 = 0.17 >= 0.15, low_prop < 0.40 para aislar la regla sostenida
    seq = [win(0, n_low=21), win(1, n_low=21), win(2, n_dets=5, n_low=0), win(3, n_low=21)]
    res = [outcomes(e, w)["cambio-sostenido-v1"] for w in seq]
    assert res == ["accumulating", "accumulating", "insufficient_evidence", "fired"]
    e2 = RuleEngine(CFG["alerts"], REF)
    res2 = [outcomes(e2, w)["cambio-sostenido-v1"] for w in [win(0, n_low=21), win(1, n_low=6), win(2, n_low=21)]]
    assert res2 == ["accumulating", "not_met", "accumulating"]  # una ventana normal reinicia la racha


def test_sustained_rule_without_reference_is_not_evaluated():
    o = outcomes(RuleEngine(CFG["alerts"], None), win(0, n_low=40))
    assert o["cambio-sostenido-v1"] == "no_reference"


def test_insufficient_evidence_rule():
    e = RuleEngine(CFG["alerts"], REF)
    res = [outcomes(e, win(i, n_valid=3, n_dets=0, n_low=0))["evidencia-insuficiente-v1"] for i in range(3)]
    assert res == ["accumulating", "accumulating", "fired"]


def ev(i, status="ok", dets=None, inf=40.0):
    dets = dets if dets is not None else [{"score": 0.8, "zone": "accepted"}]
    return {"event_id": f"t-e{i}", "run_id": "t", "frame_id": f"f{i}", "captured_at": "2026-01-01T00:00:00Z",
            "inferred_at": f"2026-01-01T00:00:{i:02d}Z", "source_id": "s", "task": "detection",
            "model_ref": "m", "model_sha256": CFG["model"]["sha256"], "config_ref": "cfg-x",
            "status": status, "error": "boom" if status == "error" else None, "window_id": "t-w0",
            "n_detections": len(dets), "n_low": sum(d["zone"] == "low" for d in dets),
            "max_score": max((d["score"] for d in dets), default=None), "inference_ms": inf if status != "error" else None,
            "image_ref": None, "detections": dets}


def test_metrics_zero_observations_are_null_not_zero():
    m = compute_window_metrics([], [], CFG["model"]["sha256"], {"cfg-x"}, 0, WCFG, Path("."))
    for mid in ("g1_inference_ms_p95", "g2_processing_fps", "g3_rss_mb_max", "g4_low_conf_prop",
                "g5_trace_coverage", "g6_model_version_match"):
        assert m[mid]["value"] is None and m[mid]["status"] == "no_data", mid


def test_metrics_exclude_errors_and_count_no_detections():
    evs = [ev(0), ev(1, "no_detections", []), ev(2, "error", [])]
    m = compute_window_metrics(evs, [{"rss_mb": 300.0}], CFG["model"]["sha256"], {"cfg-x"}, 1, WCFG, Path("."))
    assert m["g1_inference_ms_p95"]["n_obs"] == 2          # el error no aporta tiempo
    assert m["g4_low_conf_prop"]["status"] == "insufficient"
    assert m["g5_trace_coverage"]["value"] == 1.0
    assert m["g7_active_alerts"]["value"] == 1


def test_trace_coverage_detects_missing_image():
    e = ev(0)
    e["image_ref"] = "evidencias/no-existe.jpg"
    m = compute_window_metrics([e], [], CFG["model"]["sha256"], {"cfg-x"}, 0, WCFG, Path("."))
    assert m["g5_trace_coverage"]["value"] == 0.0


def test_nearest_rank_percentile():
    assert percentile_nearest_rank(list(range(1, 21)), 95) == 19
    assert percentile_nearest_rank([5.0], 95) == 5.0
    assert percentile_nearest_rank([], 95) is None
