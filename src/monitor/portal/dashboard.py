"""Tablero histórico: series por ventana de las métricas base, con estado de la ventana,
alertas y referencia, para hasta MAX_RUNS ejecuciones comparables.

`build()` solo lee la base y devuelve datos (lo usa también /api/tablero). `layout()` convierte
esos datos en geometría SVG para la plantilla. Las ejecuciones con distinto config_ref o
model_ref nunca comparten gráfica: se separan en grupos.
"""
import sqlite3

from ..metrics import BASE_METRICS
from ..store import row_to_dict

MAX_RUNS = 3
SERIES_COLORS = ("#2a78d6", "#eb6834", "#1baf7a")  # categóricos 1–3, validados en todos los pares
METRIC_LABELS = {
    "g1_inference_ms_p95": "G1 · Inferencia p95",
    "g2_processing_fps": "G2 · Frames procesados por segundo",
    "g3_rss_mb_max": "G3 · Memoria RSS máxima",
    "g4_low_conf_prop": "G4 · Proporción de detecciones de baja confianza",
    "g5_trace_coverage": "G5 · Cobertura de trazabilidad",
    "g6_model_version_match": "G6 · Coincidencia de versión del modelo",
    "g7_active_alerts": "G7 · Alertas activas al cierre",
}
COUNTS = {"g7_active_alerts"}
PROPORTIONS = {"g4_low_conf_prop", "g5_trace_coverage", "g6_model_version_match"}


def _rows(con: sqlite3.Connection, sql: str, args=()) -> list[dict]:
    return [row_to_dict(r) for r in con.execute(sql, args)]


def _guides(metric_id: str, cfg: dict, reference: dict | None, group: dict) -> list[dict]:
    """Líneas horizontales de contexto. La referencia solo se dibuja si es comparable."""
    if metric_id != "g4_low_conf_prop":
        return []
    rules = {r["rule_id"]: r for r in cfg["alerts"]}
    out = [{"label": f"baja-confianza-v1 ≥ {rules['baja-confianza-v1']['threshold']:.2f}",
            "y": rules["baja-confianza-v1"]["threshold"], "kind": "rule"}]
    if reference and reference.get("config_ref") == group["config_ref"] \
            and reference.get("model_ref") == group["model_ref"]:
        ref = reference["low_prop"]
        delta = rules["cambio-sostenido-v1"]["threshold"]
        out.append({"label": f"referencia {ref:.3f}", "y": ref, "kind": "ref"})
        out.append({"label": f"referencia + {delta:.2f} (cambio sostenido)", "y": ref + delta,
                    "kind": "rule"})
    return out


def build(con: sqlite3.Connection, run_ids: list[str], cfg: dict, reference: dict | None) -> dict:
    all_runs = _rows(con, "SELECT run_id, scenario, started_at, config_ref, model_ref, git_commit "
                          "FROM runs ORDER BY started_at DESC")
    known = {r["run_id"]: r for r in all_runs}
    result = {"available": all_runs, "requested": run_ids, "errors": [], "notes": [], "groups": []}
    if not all_runs:
        result["empty"] = "No hay ejecuciones en la base. Ejecuta un escenario primero."
        return result
    if not run_ids:
        result["empty"] = "Selecciona al menos una ejecución."
        return result

    unknown = [r for r in run_ids if r not in known]
    if unknown:
        result["errors"].append("Ejecuciones inexistentes: " + ", ".join(unknown))
    selected = list(dict.fromkeys(r for r in run_ids if r in known))
    if len(selected) > MAX_RUNS:
        result["errors"].append(f"Se compara un máximo de {MAX_RUNS} ejecuciones; "
                                f"se omitieron: {', '.join(selected[MAX_RUNS:])}")
        selected = selected[:MAX_RUNS]
    if not selected:
        result["empty"] = "Ninguna de las ejecuciones solicitadas existe."
        return result

    groups: dict[tuple, dict] = {}
    for i, rid in enumerate(selected):
        run = dict(known[rid], color=SERIES_COLORS[i], slot=i + 1)
        wins = _rows(con, "SELECT window_id, idx, state, start_at, end_at, n_valid, n_dets, low_prop "
                          "FROM windows WHERE run_id=? ORDER BY idx", (rid,))
        mets = _rows(con, "SELECT window_id, metric_id, value, unit, n_obs, status "
                          "FROM metric_values WHERE run_id=?", (rid,))
        by_win = {(m["window_id"], m["metric_id"]): m for m in mets}
        idx_of = {w["window_id"]: w["idx"] for w in wins}
        alerts = _rows(con, "SELECT alert_id, rule_id, severity, status, opened_at, resolved_at, "
                            "window_ids_json FROM alerts WHERE run_id=? ORDER BY opened_at", (rid,))
        for a in alerts:
            idxs = [idx_of[w] for w in a.pop("window_ids") if w in idx_of]
            a["first_idx"], a["last_idx"] = (min(idxs), max(idxs)) if idxs else (None, None)
        run["windows"] = wins
        run["alerts"] = alerts
        run["series"] = {
            mid: [{"window_id": w["window_id"], "x": w["idx"], "state": w["state"],
                   "y": by_win.get((w["window_id"], mid), {}).get("value"),
                   "status": by_win.get((w["window_id"], mid), {}).get("status", "missing"),
                   "n_obs": by_win.get((w["window_id"], mid), {}).get("n_obs")}
                  for w in wins]
            for mid in BASE_METRICS}
        run["summary"] = {
            "n_windows": len(wins),
            "n_eligible": sum(w["state"] == "eligible" for w in wins),
            "n_insufficient": sum(w["state"] == "insufficient" for w in wins),
            "n_no_data": sum(m["status"] != "ok" for m in mets),
            "n_alerts": len(alerts),
            "n_alerts_open": sum(a["status"] == "open" for a in alerts),
        }
        if not wins:
            result["notes"].append(f"{rid}: la ejecución no cerró ninguna ventana; no hay puntos.")
        key = (run["config_ref"], run["model_ref"])
        groups.setdefault(key, {"config_ref": key[0], "model_ref": key[1], "runs": []})["runs"].append(run)

    if len(groups) > 1:
        result["notes"].append("Las ejecuciones usan configuraciones o modelos distintos; "
                               "se muestran en grupos separados y sus series no se mezclan.")
    for g in groups.values():
        g["charts"] = [{"metric_id": mid, "label": METRIC_LABELS[mid], "unit": unit,
                        "guides": _guides(mid, cfg, reference, g)}
                       for mid, (_, unit) in BASE_METRICS.items()]
        g["reference_comparable"] = any(gd["kind"] == "ref"
                                        for c in g["charts"] for gd in c["guides"])
        result["groups"].append(g)
    return result


# ------------------------------------------------------------------ geometría SVG
W, H = 620, 210
ML, MR, MT, MB = 52, 16, 14, 30


def _nice_max(v: float) -> float:
    if v <= 0:
        return 1.0
    mag = 10 ** (len(str(int(v))) - 1) if v >= 1 else 0.1
    for step in (1, 2, 2.5, 5, 10):
        if v <= step * mag * 1.0001:
            return step * mag
    return 10 * mag


def _fmt_tick(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".") if v < 10 else f"{v:.0f}"


def layout(group: dict) -> list[dict]:
    """Para cada gráfica del grupo: escala, ticks, trazos por ejecución y puntos enlazables."""
    n_x = max((len(r["windows"]) for r in group["runs"]), default=0)
    x_max = max(n_x - 1, 1)
    sx = lambda x: ML + (W - ML - MR) * x / x_max
    out = []
    for chart in group["charts"]:
        mid = chart["metric_id"]
        values = [p["y"] for r in group["runs"] for p in r["series"][mid] if p["y"] is not None]
        values += [g["y"] for g in chart["guides"]]
        if mid in PROPORTIONS:
            y_max = 1.0
        elif mid in COUNTS:  # conteos enteros: ticks enteros
            y_max = 4.0 * max(1, -(-int(max(values, default=0)) // 4))
        else:
            y_max = _nice_max(max(values, default=0) * 1.1)
        sy = lambda y: MT + (H - MT - MB) * (1 - y / y_max)
        ticks = [{"v": _fmt_tick(y_max * k / 4), "y": sy(y_max * k / 4)} for k in range(5)]
        step = max(1, -(-n_x // 10))
        xticks = [{"v": i, "x": sx(i)} for i in range(0, n_x, step)]
        series = []
        for r in group["runs"]:
            pts, segs, cur = [], [], []
            for p in r["series"][mid]:
                px = sx(p["x"])
                if p["y"] is None:
                    if cur:
                        segs.append(cur); cur = []
                    pts.append(dict(p, px=px, py=sy(0), missing=True))
                    continue
                py = sy(p["y"])
                cur.append(f"{px:.1f},{py:.1f}")
                pts.append(dict(p, px=px, py=py, missing=False))
            if cur:
                segs.append(cur)
            series.append({"run": r, "paths": ["M" + " L".join(s) for s in segs], "points": pts})
        out.append(dict(chart, W=W, H=H, ML=ML, MR=MR, MT=MT, MB=MB, y_max=y_max, ticks=ticks,
                        xticks=xticks, n_x=n_x, series=series,
                        guide_lines=[dict(g, py=sy(g["y"])) for g in chart["guides"]]))
    return out


def alert_bars(group: dict) -> list[dict]:
    """Franjas de alertas por ejecución sobre el mismo eje de ventanas que las gráficas."""
    n_x = max((len(r["windows"]) for r in group["runs"]), default=0)
    x_max = max(n_x - 1, 1)
    half = (W - ML - MR) / x_max / 2
    sx = lambda x: ML + (W - ML - MR) * x / x_max
    rows = []
    for r in group["runs"]:
        lanes: dict[str, list] = {}
        for a in r["alerts"]:
            if a["first_idx"] is None:
                continue
            x0 = max(ML, sx(a["first_idx"]) - half)
            x1 = min(W - MR, sx(a["last_idx"]) + half)
            lanes.setdefault(a["rule_id"], []).append(dict(a, x=x0, w=max(x1 - x0, 4)))
        rows.append({"run": r, "lanes": sorted(lanes.items())})
    return rows
