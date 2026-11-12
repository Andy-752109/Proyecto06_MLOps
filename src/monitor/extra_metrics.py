"""Métricas adicionales (no base), calculadas por ventana a partir de registros ya persistidos.

M1 · m1_e2e_ms_p95     latencia extremo a extremo p95 (lectura del frame -> fin de inferencia)
M2 · m2_delivery_ratio frames inferidos / frames muestreados esperados según frame_index
M3 · m3_score_psi      PSI de la distribución de puntuaciones de la ventana vs. la referencia

Definiciones completas en docs/metricas-adicionales.md. Se calculan después de la ejecución
(scripts/extra_metrics.py) con los mismos events.jsonl y windows.jsonl que usa el resto del
proyecto; no cambian el pipeline ni las métricas base. Regla común: sin observaciones el
valor es None con status "no_data"; con menos observaciones que el mínimo declarado, None
con status "insufficient".
"""
import math

from .metrics import VALID, percentile_nearest_rank

EXTRA_METRICS = {
    "m1_e2e_ms_p95": "ms",
    "m2_delivery_ratio": "proporción",
    "m3_score_psi": "PSI",
}
PSI_EPS = 1e-4          # piso de proporción por bin (evita log(0) en bins vacíos)
PSI_MIN_DETS = 30       # igual que windows.min_detections


def ref_bins(reference: dict) -> list[tuple[float, float, float]]:
    """[(desde, hasta, proporción de referencia)] a partir de reference.score_histogram."""
    hist = reference["score_histogram"]
    total = sum(hist.values())
    out = []
    for label, n in hist.items():
        lo, hi = (float(x) for x in label.strip("[)").split(","))
        out.append((lo, hi, n / total))
    return out


def psi(scores: list[float], bins: list[tuple[float, float, float]]) -> float:
    n = len(scores)
    total = 0.0
    for i, (lo, hi, p_ref) in enumerate(bins):
        last = i == len(bins) - 1  # el último bin incluye 1.0
        k = sum(1 for s in scores if lo <= s < hi or (last and s == hi))
        p = max(k / n, PSI_EPS)
        q = max(p_ref, PSI_EPS)
        total += (p - q) * math.log(p / q)
    return total


def compute_extra(events: list[dict], windows: list[dict], sample_every: int,
                  reference: dict | None) -> list[dict]:
    """Una fila por (ventana, métrica). `events` de toda la ejecución, ordenables por seq."""
    events = sorted(events, key=lambda e: e["seq"])
    by_win: dict[str, list[dict]] = {}
    for e in events:
        by_win.setdefault(e["window_id"], []).append(e)
    bins = ref_bins(reference) if reference else None

    # M2: frames esperados por cada frame entregado = salto de frame_index / sample_every,
    # medido contra el frame entregado anterior (aunque esté en la ventana previa).
    expected_for: dict[str, float] = {}
    prev = None
    for e in events:
        if e["frame_index"] is None:   # hueco de la fuente: no hay frame
            continue
        jump = sample_every if prev is None else e["frame_index"] - prev
        expected_for[e["event_id"]] = jump / sample_every
        prev = e["frame_index"]

    rows = []
    for w in sorted(windows, key=lambda w: w["idx"]):
        evs = by_win.get(w["window_id"], [])
        valid = [e for e in evs if e["status"] in VALID]

        e2e = [e["e2e_ms"] for e in valid if e.get("e2e_ms") is not None]
        p95 = percentile_nearest_rank(e2e, 95)
        parts = {k: percentile_nearest_rank([e[k] for e in valid if e.get(k) is not None], 50)
                 for k in ("queue_ms", "inference_ms", "e2e_ms")}
        rows.append({"metric_id": "m1_e2e_ms_p95", "value": None if p95 is None else round(p95, 3),
                     "n_obs": len(e2e), "status": "ok" if e2e else "no_data",
                     "detail": {"p50": parts["e2e_ms"], "queue_ms_p50": parts["queue_ms"],
                                "inference_ms_p50": parts["inference_ms"]}})

        delivered = [e for e in evs if e["frame_index"] is not None]
        expected = sum(expected_for[e["event_id"]] for e in delivered)
        rows.append({"metric_id": "m2_delivery_ratio",
                     "value": round(len(delivered) / expected, 6) if expected else None,
                     "n_obs": len(delivered), "status": "ok" if expected else "no_data",
                     "detail": {"delivered": len(delivered), "expected": round(expected, 3),
                                "lost": round(expected - len(delivered), 3),
                                "gap_events": sum(e["status"] == "source_gap" for e in evs)}})

        scores = [d["score"] for e in valid for d in e["detections"]]
        if bins is None or not scores:
            val, st = None, ("no_reference" if bins is None else "no_data")
        elif len(scores) < PSI_MIN_DETS or w["state"] == "insufficient":
            val, st = None, "insufficient"  # misma política que las reglas: no se interpreta
        else:
            val, st = round(psi(scores, bins), 6), "ok"
        rows.append({"metric_id": "m3_score_psi", "value": val, "n_obs": len(scores), "status": st,
                     "detail": {"bins": len(bins) if bins else 0, "eps": PSI_EPS}})

        for r in rows[-3:]:
            r.update(window_id=w["window_id"], idx=w["idx"], unit=EXTRA_METRICS[r["metric_id"]])
    return rows
