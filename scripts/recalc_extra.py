"""Recálculo independiente de M1–M3 con pandas/numpy (no importa monitor.extra_metrics).

Lee events.jsonl, windows.jsonl y la referencia de cada ejecución, recalcula y compara con
evidencias/metricas_adicionales/<run_id>.jsonl.

Uso:  python scripts/recalc_extra.py --run-id <id> [--run-id <id> ...]
Salida: evidencias/metricas_adicionales/recalculo.{json,md}. Sale con 1 si hay diferencias.
"""
import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidencias/metricas_adicionales"
EPS = 1e-4


def nearest_rank(values, p):
    v = np.sort(np.asarray(values, dtype=float))
    return float(v[max(1, math.ceil(p / 100 * len(v))) - 1]) if len(v) else None


def recalc(run_id: str) -> dict:
    d = ROOT / "evidencias/runs" / run_id
    man = json.loads((d / "manifest.json").read_text())
    every = man["source"]["sample_every"]
    ev = pd.read_json(d / "events.jsonl", lines=True).sort_values("seq")
    wins = pd.read_json(d / "windows.jsonl", lines=True)
    ref = json.loads((ROOT / ((man.get("reference") or {}).get("path") or "config/reference.json")).read_text())
    edges = sorted({float(x) for k in ref["score_histogram"] for x in k.strip("[)").split(",")})
    q = np.array(list(ref["score_histogram"].values()), dtype=float)
    q = np.clip(q / q.sum(), EPS, None)

    ev["valid"] = ev["status"].isin(["ok", "no_detections"])
    fr = ev[ev["frame_index"].notna()].copy()
    fr["expected"] = fr["frame_index"].diff().fillna(every) / every
    stored = {(r["window_id"], r["metric_id"]): r for r in
              (json.loads(x) for x in (OUT / f"{run_id}.jsonl").read_text().splitlines() if x)}
    checks = []
    for w in wins.itertuples():
        g = ev[ev["window_id"] == w.window_id]
        v = g[g["valid"]]
        m1 = nearest_rank(v["e2e_ms"].dropna(), 95)
        f = fr[fr["window_id"] == w.window_id]
        m2 = len(f) / f["expected"].sum() if f["expected"].sum() else None
        scores = np.array([d["score"] for dets in v["detections"] for d in dets], dtype=float)
        if len(scores) >= 30 and w.state != "insufficient":
            p = np.clip(np.histogram(scores, bins=edges)[0] / len(scores), EPS, None)
            m3 = float(np.sum((p - q) * np.log(p / q)))
        else:
            m3 = None
        for mid, mine in (("m1_e2e_ms_p95", m1), ("m2_delivery_ratio", m2), ("m3_score_psi", m3)):
            st = stored[(w.window_id, mid)]["value"]
            ok = (mine is None and st is None) or (mine is not None and st is not None and abs(mine - st) <= 1e-3)
            checks.append({"window_id": w.window_id, "metric_id": mid, "stored": st,
                           "recalc": None if mine is None else round(mine, 6), "ok": bool(ok)})
    return {"run_id": run_id, "n_checks": len(checks), "n_diff": sum(not c["ok"] for c in checks), "checks": checks}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", action="append", required=True)
    args = ap.parse_args()
    res = [recalc(r) for r in args.run_id]
    (OUT / "recalculo.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    md = ["# Recálculo independiente de M1–M3", "",
          "Generado con `python scripts/recalc_extra.py " + " ".join(f"--run-id {r}" for r in args.run_id) + "`.",
          "Implementación aparte con pandas/numpy (`np.histogram` para M3, `diff` de `frame_index` para M2); "
          "tolerancia 1e-3 (los valores guardados están redondeados).", "",
          "| Ejecución | Comprobaciones | Diferencias |", "|---|---|---|"]
    md += [f"| `{r['run_id']}` | {r['n_checks']} | {r['n_diff']} |" for r in res]
    bad = [c for r in res for c in r["checks"] if not c["ok"]]
    md += ["", f"**Total: {sum(r['n_checks'] for r in res)} comprobaciones, {len(bad)} diferencias.**"]
    md += [f"- {c['window_id']} {c['metric_id']}: guardado {c['stored']} · recalculado {c['recalc']}" for c in bad]
    (OUT / "recalculo.md").write_text("\n".join(md) + "\n")
    print(f"{sum(r['n_checks'] for r in res)} comprobaciones, {len(bad)} diferencias")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
