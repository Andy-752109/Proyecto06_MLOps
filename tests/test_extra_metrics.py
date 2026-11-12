"""Métricas adicionales M1–M3 con datos sintéticos."""
import pytest

from monitor.extra_metrics import compute_extra, psi, ref_bins

REF = {"score_histogram": {"[0.1,0.5)": 20, "[0.5,0.8)": 30, "[0.8,1.0)": 50}}


def ev(seq, frame, scores=(), status="ok", e2e=50.0, win="t-w000"):
    return {"event_id": f"t-e{seq:03d}", "seq": seq, "frame_index": frame, "window_id": win,
            "status": status, "e2e_ms": None if frame is None else e2e,
            "queue_ms": None if frame is None else 5.0, "inference_ms": None if frame is None else 40.0,
            "detections": [{"score": s} for s in scores]}


def win(i=0, state="eligible"):
    return {"window_id": f"t-w{i:03d}", "idx": i, "state": state}


def by(rows, mid, i=0):
    return next(r for r in rows if r["metric_id"] == mid and r["idx"] == i)


def test_psi_is_zero_for_reference_distribution_and_grows_with_shift():
    bins = ref_bins(REF)
    same = [0.2] * 20 + [0.6] * 30 + [0.9] * 50
    assert psi(same, bins) == pytest.approx(0.0, abs=1e-12)
    shifted = [0.2] * 70 + [0.6] * 20 + [0.9] * 10
    assert psi(shifted, bins) > 0.5
    assert psi([1.0] * 40, bins) == psi([0.85] * 40, bins), "1.0 cae en el último bin"


def test_psi_needs_eligible_window_and_enough_detections():
    evs = [ev(i, 2 * i, [0.9, 0.9]) for i in range(10)]  # 20 detecciones < 30
    assert by(compute_extra(evs, [win()], 2, REF), "m3_score_psi")["status"] == "insufficient"
    evs = [ev(i, 2 * i, [0.9] * 4) for i in range(10)]
    assert by(compute_extra(evs, [win(state="insufficient")], 2, REF), "m3_score_psi")["value"] is None
    assert by(compute_extra(evs, [win()], 2, None), "m3_score_psi")["status"] == "no_reference"


def test_delivery_ratio_counts_jumps_in_frame_index():
    # muestreo 1/2: frames 0,2,4 y luego salto a 14 (se perdieron 6,8,10,12)
    evs = [ev(0, 0), ev(1, 2), ev(2, 4), ev(3, None, status="source_gap"), ev(4, 14)]
    r = by(compute_extra(evs, [win()], 2, REF), "m2_delivery_ratio")
    assert r["detail"]["lost"] == 4 and r["value"] == pytest.approx(4 / 8)
    assert r["detail"]["gap_events"] == 1


def test_window_without_frames_has_no_data():
    evs = [ev(0, 0, win="t-w000"), ev(1, None, status="source_gap", win="t-w001")]
    rows = compute_extra(evs, [win(0), win(1, "insufficient")], 2, REF)
    for mid in ("m1_e2e_ms_p95", "m2_delivery_ratio", "m3_score_psi"):
        assert by(rows, mid, 1)["value"] is None and by(rows, mid, 1)["status"] == "no_data", mid


def test_e2e_p95_uses_valid_frames_only():
    evs = [ev(i, 2 * i, e2e=10.0 * (i + 1)) for i in range(20)] + [ev(20, 40, status="error", e2e=9999.0)]
    r = by(compute_extra(evs, [win()], 2, REF), "m1_e2e_ms_p95")
    assert r["value"] == 190.0 and r["n_obs"] == 20  # rango más cercano: posición 19 de 20
