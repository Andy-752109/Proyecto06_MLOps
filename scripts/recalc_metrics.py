"""Recalcula las métricas base, las ventanas y la regla de baja confianza desde los JSONL
primarios de una ejecución, con una implementación independiente (pandas), y compara
contra lo registrado por el monitor (metrics.jsonl, windows.jsonl, alerts.jsonl).

Uso:  python scripts/recalc_metrics.py --run-id <run_id> [--run-id <otro> ...]
Salida: evidencias/recalculo/<run_id>.json y .md ; código de salida 1 si hay diferencias.
"""
import argparse
import json
import math
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
TOL = 1e-6


def jl(path: Path) -> pd.DataFrame:
    return pd.read_json(path, lines=True, dtype=False) if path.stat().st_size else pd.DataFrame()


def nearest_rank(values, p):
    s = sorted(values)
    return s[math.ceil(p / 100 * len(s)) - 1] if s else None


def close(a, b, tol=TOL):
    if a is None or b is None or (isinstance(a, float) and math.isnan(a)):
        return (a is None or (isinstance(a, float) and math.isnan(a))) and b is None
    return abs(float(a) - float(b)) <= tol * max(1.0, abs(float(b)))


def recalc(run_id: str, cfg: dict) -> dict:
    run_dir = ROOT / cfg["storage"]["runs_dir"] / run_id
    manifest = json.loads((run_dir / "manifest.json").read_text())
    snap = json.loads((run_dir / "config.snapshot.json").read_text())
    ev = jl(run_dir / "events.jsonl")
    res = jl(run_dir / "resources.jsonl")
    mets = jl(run_dir / "metrics.jsonl")
    wins = jl(run_dir / "windows.jsonl")
    alerts = [json.loads(x) for x in (run_dir / "alerts.jsonl").read_text().splitlines() if x]
    lo = snap["policy"]["lower"]
    up = snap["policy"]["upper"]
    wc = snap["windows"]
    expected_sha = snap["model"]["sha256"]

    # Zonas recalculadas desde la puntuación cruda de cada detección.
    det_rows = [(r.event_id, d["score"], d["zone"]) for r in ev.itertuples() for d in (r.detections or [])]
    det = pd.DataFrame(det_rows, columns=["event_id", "score", "zone"])
    det["zone_recalc"] = pd.cut(det["score"], [-1, lo, up, 2], right=False,
                                labels=["low", "doubt", "accepted"]).astype(str)
    zone_mismatch = int((det["zone"] != det["zone_recalc"]).sum())

    ev["valid"] = ev["status"].isin(["ok", "no_detections"])
    ev["ts"] = (pd.to_datetime(ev["inferred_at"], utc=True) - pd.Timestamp(0, tz="UTC")).dt.total_seconds()
    low_by_event = det[det["zone_recalc"] == "low"].groupby("event_id").size()
    n_by_event = det.groupby("event_id").size()
    ev["n_low_r"] = ev["event_id"].map(low_by_event).fillna(0).astype(int)
    ev["n_det_r"] = ev["event_id"].map(n_by_event).fillna(0).astype(int)

    checks, rows = [], []
    rule_low = next(r for r in snap["alerts"] if r["rule_id"] == "baja-confianza-v1")
    for wid, g in ev.groupby("window_id", sort=True):
        v = g[g["valid"]]
        n_dets, n_low = int(v["n_det_r"].sum()), int(v["n_low_r"].sum())
        eligible = len(v) >= wc["min_frames"] and n_dets >= wc["min_detections"]
        r = {"window_id": wid, "n_events": len(g), "n_valid": len(v), "n_dets": n_dets,
             "n_low": n_low, "low_prop": n_low / n_dets if n_dets else None,
             "state": "eligible" if eligible else "insufficient"}
        inf = v["inference_ms"].dropna().tolist()
        r["g1_inference_ms_p95"] = nearest_rank(inf, 95)
        ts = sorted(v["ts"])
        span = ts[-1] - ts[0] if len(ts) >= 2 else 0
        r["g2_processing_fps"] = (len(ts) - 1) / span if span > 0 else None
        rr = res[res["event_id"].isin(g["event_id"])]["rss_mb"].dropna()
        r["g3_rss_mb_max"] = float(rr.max()) if len(rr) else None
        r["g4_low_conf_prop"] = r["low_prop"]
        traceable = 0
        for e in g.itertuples():
            fields_ok = all(pd.notna(getattr(e, f)) and getattr(e, f) != "" for f in
                            ("event_id", "run_id", "frame_id", "captured_at", "inferred_at", "source_id",
                             "task", "model_ref", "model_sha256", "config_ref", "status", "window_id"))
            img_ok = (not isinstance(e.image_ref, str)) or (ROOT / e.image_ref).is_file()
            cfg_ok = e.config_ref == manifest["config_ref"]
            st_ok = (e.status != "ok" or (e.n_det_r == e.n_detections and e.n_det_r > 0)) and \
                    (e.status != "no_detections" or e.n_det_r == 0)
            traceable += fields_ok and img_ok and cfg_ok and st_ok
        r["g5_trace_coverage"] = traceable / len(g) if len(g) else None
        rep = g["model_sha256"].dropna()
        r["g6_model_version_match"] = float((rep == expected_sha).mean()) if len(rep) else None
        # G7: alertas abiertas al cierre de esta ventana según alerts.jsonl (intervalos)
        wend = wins.set_index("window_id").loc[wid, "end_at"]
        r["g7_active_alerts"] = sum(a["opened_at"] <= wend and (a["resolved_at"] is None or a["resolved_at"] > wend)
                                    for a in alerts)
        r["rule_low_met"] = (r["low_prop"] is not None and eligible and r["low_prop"] >= rule_low["threshold"])
        rows.append(r)

    recalc_df = pd.DataFrame(rows)
    # Comparación con métricas registradas
    for m in mets.itertuples():
        mine = recalc_df.set_index("window_id").loc[m.window_id, m.metric_id]
        mine = None if (isinstance(mine, float) and math.isnan(mine)) else mine
        stored = None if (m.value is None or (isinstance(m.value, float) and math.isnan(m.value))) else m.value
        tol = 1e-3 if m.metric_id in ("g1_inference_ms_p95", "g2_processing_fps", "g3_rss_mb_max") else TOL
        checks.append({"what": f"{m.window_id} {m.metric_id}", "stored": stored, "recalc": mine,
                       "ok": close(mine, stored, tol)})
    # Comparación con ventanas registradas
    for w in wins.itertuples():
        mine = recalc_df.set_index("window_id").loc[w.window_id]
        for f in ("n_valid", "n_dets", "n_low", "state"):
            checks.append({"what": f"{w.window_id} {f}", "stored": getattr(w, f), "recalc": mine[f],
                           "ok": getattr(w, f) == mine[f]})
    # Alertas de baja confianza: abiertas exactamente donde la regla empieza a cumplirse
    if manifest["evaluate_rules"]:
        fired_expected, prev_open = [], False
        for r in rows:
            if r["state"] != "eligible":
                continue
            if r["rule_low_met"] and not prev_open:
                fired_expected.append(r["window_id"])
            prev_open = r["rule_low_met"]
        fired_stored = [a["first_window_id"] for a in alerts if a["rule_id"] == "baja-confianza-v1"]
        checks.append({"what": "baja-confianza-v1 ventanas de apertura", "stored": fired_stored,
                       "recalc": fired_expected, "ok": fired_stored == fired_expected})
    # Referencias de imágenes de alertas
    missing = [p for a in alerts for p in a["image_refs"] if not (ROOT / p).is_file()]
    checks.append({"what": "image_refs de alertas resuelven", "stored": len(missing), "recalc": 0,
                   "ok": not missing})
    checks.append({"what": "zonas por detección (recalculadas con umbrales)", "stored": zone_mismatch,
                   "recalc": 0, "ok": zone_mismatch == 0})

    run_level = {
        "events": len(ev), "valid_frames": int(ev["valid"].sum()), "detections": len(det),
        "by_zone": det["zone_recalc"].value_counts().to_dict(),
        "low_prop_run": (det["zone_recalc"] == "low").mean() if len(det) else None,
        "inference_ms_p50": nearest_rank(ev.loc[ev["valid"], "inference_ms"].dropna().tolist(), 50),
        "inference_ms_p95": nearest_rank(ev.loc[ev["valid"], "inference_ms"].dropna().tolist(), 95),
        "frames_without_detections": int((ev["status"] == "no_detections").sum()),
        "errors": int((ev["status"] == "error").sum()),
        "captures": int(ev["image_ref"].notna().sum()),
    }
    failed = [c for c in checks if not c["ok"]]
    return {"run_id": run_id, "git_commit": manifest["git_commit"], "config_ref": manifest["config_ref"],
            "n_checks": len(checks), "n_failed": len(failed), "failed": failed,
            "run_level": run_level, "windows": rows, "checks": checks}


def to_md(r: dict) -> str:
    cols = ["window_id", "state", "n_valid", "n_dets", "n_low", "g1_inference_ms_p95", "g2_processing_fps",
            "g3_rss_mb_max", "g4_low_conf_prop", "g5_trace_coverage", "g6_model_version_match", "g7_active_alerts"]
    fmt = lambda v: "—" if v is None or (isinstance(v, float) and math.isnan(v)) else (f"{v:.4f}" if isinstance(v, float) else str(v))
    head = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols)
    body = "\n".join("| " + " | ".join(fmt(w[c]) for c in cols) + " |" for w in r["windows"])
    fails = "\n".join(f"- {c['what']}: registrado {c['stored']} · recalculado {c['recalc']}" for c in r["failed"]) or "- ninguna"
    return f"""# Recálculo independiente · `{r['run_id']}`

Comando: `python scripts/recalc_metrics.py --run-id {r['run_id']}`
Commit de la ejecución: `{r['git_commit']}` · configuración `{r['config_ref']}`

Fuentes primarias: `events.jsonl` (puntuaciones crudas de cada detección, tiempos, estados),
`resources.jsonl`, `alerts.jsonl`, `config.snapshot.json`. Las zonas se recalculan desde la
puntuación con los umbrales del snapshot; no se usan los contadores guardados por el monitor.

**Comprobaciones: {r['n_checks']} · diferencias: {r['n_failed']}**

Diferencias:
{fails}

## Totales de la ejecución (recalculados)

```json
{json.dumps(r['run_level'], indent=2, ensure_ascii=False, default=float)}
```

## Métricas base por ventana (recalculadas)

{head}
{body}
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", action="append", required=True)
    args = ap.parse_args()
    cfg = yaml.safe_load((ROOT / "config/monitor.yaml").read_text())
    out_dir = ROOT / "evidencias/recalculo"
    out_dir.mkdir(parents=True, exist_ok=True)
    bad = 0
    for run_id in args.run_id:
        r = recalc(run_id, cfg)
        (out_dir / f"{run_id}.json").write_text(json.dumps(r, indent=2, ensure_ascii=False, default=float))
        (out_dir / f"{run_id}.md").write_text(to_md(r))
        print(f"{run_id}: {r['n_checks']} comprobaciones, {r['n_failed']} diferencias")
        for c in r["failed"]:
            print("   ", c)
        bad += r["n_failed"]
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
