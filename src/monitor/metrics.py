"""Métricas base (una por grupo G1-G7), calculadas por ventana.

Las definiciones completas están en docs/metricas.md. Regla común: sin observaciones
elegibles el valor es None con status "no_data" (nunca 0); una ventana con datos
por debajo del mínimo declarado se marca "insufficient".
"""
import math
from datetime import datetime
from pathlib import Path

VALID = ("ok", "no_detections")  # inferencia completada (con o sin detecciones)

BASE_METRICS = {
    "g1_inference_ms_p95": ("G1", "ms"),
    "g2_processing_fps": ("G2", "frames/s"),
    "g3_rss_mb_max": ("G3", "MB"),
    "g4_low_conf_prop": ("G4", "proporción"),
    "g5_trace_coverage": ("G5", "proporción"),
    "g6_model_version_match": ("G6", "proporción"),
    "g7_active_alerts": ("G7", "alertas"),
}

REQUIRED_FIELDS = ("event_id", "run_id", "frame_id", "captured_at", "inferred_at", "source_id",
                   "task", "model_ref", "model_sha256", "config_ref", "status", "window_id")


def parse_ts(ts: str) -> float:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def percentile_nearest_rank(values: list[float], p: float) -> float | None:
    """Percentil por rango más cercano: el valor en la posición ceil(p/100 * n) (1-indexada)."""
    if not values:
        return None
    s = sorted(values)
    k = max(1, math.ceil(p / 100 * len(s)))
    return s[k - 1]


def event_is_traceable(ev: dict, known_configs: set, root: Path) -> tuple[bool, list[str]]:
    """Un evento es trazable si tiene todos los campos obligatorios, su config_ref existe,
    su contenido es coherente con su estado y su image_ref (si existe) resuelve a un archivo."""
    problems = [f for f in REQUIRED_FIELDS if ev.get(f) in (None, "")]
    if ev.get("config_ref") not in known_configs:
        problems.append("config_ref_no_resuelve")
    dets = ev.get("detections") or []
    st = ev.get("status")
    if st == "ok" and (ev.get("n_detections") != len(dets) or not dets
                       or any(d.get("score") is None or d.get("zone") is None for d in dets)):
        problems.append("detecciones_incoherentes")
    if st == "no_detections" and (dets or ev.get("max_score") is not None):
        problems.append("sin_detecciones_incoherente")
    if st == "error" and not ev.get("error"):
        problems.append("error_sin_detalle")
    if ev.get("image_ref") and not (root / ev["image_ref"]).is_file():
        problems.append("image_ref_no_resuelve")
    return (not problems), problems


def compute_window_metrics(events: list[dict], resources: list[dict], expected_sha256: str,
                           known_configs: set, active_alerts: int, windows_cfg: dict,
                           root: Path) -> dict:
    """Devuelve {metric_id: {value, unit, n_obs, status, detail}} para una ventana."""
    out = {}
    valid = [e for e in events if e["status"] in VALID]

    # G1 · p95 del tiempo de inferencia (solo la llamada al modelo) en frames válidos.
    inf = [e["inference_ms"] for e in valid if e.get("inference_ms") is not None]
    p95 = percentile_nearest_rank(inf, 95)
    out["g1_inference_ms_p95"] = dict(
        value=None if p95 is None else round(p95, 3), n_obs=len(inf),
        status="ok" if inf else "no_data",
        detail={"p50": percentile_nearest_rank(inf, 50), "method": "nearest-rank"})

    # G2 · FPS de procesamiento = (n-1) / (t_último - t_primero) sobre inferred_at válidos.
    ts = sorted(parse_ts(e["inferred_at"]) for e in valid)
    span = ts[-1] - ts[0] if len(ts) >= 2 else 0.0
    fps = (len(ts) - 1) / span if span > 0 else None
    out["g2_processing_fps"] = dict(
        value=None if fps is None else round(fps, 4), n_obs=len(ts),
        status="ok" if fps is not None else "no_data", detail={"span_s": round(span, 3)})

    # G3 · RSS máximo del proceso monitor (psutil) en la ventana.
    rss = [r["rss_mb"] for r in resources if r.get("rss_mb") is not None]
    out["g3_rss_mb_max"] = dict(
        value=round(max(rss), 3) if rss else None, n_obs=len(rss),
        status="ok" if rss else "no_data", detail={})

    # G4 · Proporción de baja confianza = detecciones low / detecciones puntuadas (frames válidos).
    n_dets = sum(e["n_detections"] for e in valid)
    n_low = sum(e["n_low"] for e in valid)
    enough = len(valid) >= windows_cfg["min_frames"] and n_dets >= windows_cfg["min_detections"]
    out["g4_low_conf_prop"] = dict(
        value=round(n_low / n_dets, 6) if n_dets else None, n_obs=n_dets,
        status="ok" if enough else ("insufficient" if n_dets else "no_data"),
        detail={"n_low": n_low, "n_dets": n_dets, "n_valid_frames": len(valid)})

    # G5 · Cobertura de trazabilidad = eventos trazables / eventos de la ventana.
    bad = {}
    for e in events:
        okk, probs = event_is_traceable(e, known_configs, root)
        if not okk:
            bad[e["event_id"]] = probs
    out["g5_trace_coverage"] = dict(
        value=round((len(events) - len(bad)) / len(events), 6) if events else None,
        n_obs=len(events), status="ok" if events else "no_data",
        detail={"untraceable": bad})

    # G6 · Versión esperada vs reportada = eventos con model_sha256 == esperado / eventos.
    reported = [e for e in events if e.get("model_sha256")]
    match = sum(e["model_sha256"] == expected_sha256 for e in reported)
    out["g6_model_version_match"] = dict(
        value=round(match / len(reported), 6) if reported else None, n_obs=len(reported),
        status="ok" if reported else "no_data",
        detail={"expected": expected_sha256[:12], "mismatch": len(reported) - match})

    # G7 · Alertas activas (abiertas) al cierre de la ventana, en esta ejecución.
    out["g7_active_alerts"] = dict(value=active_alerts, n_obs=1, status="ok", detail={})

    for mid, rec in out.items():
        rec["grp"], rec["unit"] = BASE_METRICS[mid]
    return out
