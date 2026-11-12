"""Métricas adicionales M1–M3 por ventana para las ejecuciones indicadas, más la verificación
de sus casos de cambio controlado.

Uso:  python scripts/extra_metrics.py --run-id <id> [--run-id <id> ...]
Salida: evidencias/metricas_adicionales/<run_id>.jsonl (una fila por ventana y métrica)
        y evidencias/metricas_adicionales/resumen.md. Sale con 1 si alguna expectativa falla.
"""
import argparse
import json
import sys
from pathlib import Path

from monitor.extra_metrics import EXTRA_METRICS, compute_extra

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidencias/metricas_adicionales"


def jl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def load(run_id: str) -> dict:
    d = ROOT / "evidencias/runs" / run_id
    man = json.loads((d / "manifest.json").read_text())
    ref_path = ROOT / ((man.get("reference") or {}).get("path") or "config/reference.json")
    return {"man": man, "events": jl(d / "events.jsonl"), "windows": jl(d / "windows.jsonl"),
            "reference": json.loads(ref_path.read_text()) if ref_path.exists() else None,
            "source_events": jl(d / "source_events.jsonl") if (d / "source_events.jsonl").exists() else []}


def series(rows, mid):
    return [r for r in rows if r["metric_id"] == mid]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", action="append", required=True)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    runs, checks = {}, []

    def check(metric, what, expected, observed, ok):
        checks.append({"metric": metric, "what": what, "expected": expected, "observed": observed, "ok": bool(ok)})

    for rid in args.run_id:
        r = load(rid)
        rows = compute_extra(r["events"], r["windows"], r["man"]["source"]["sample_every"], r["reference"])
        for row in rows:
            row["run_id"] = rid
        (OUT / f"{rid}.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows))
        runs[rid] = dict(r, rows=rows)

        # M1 · coherencia entre etapas: e2e = cola + inferencia + resto (resto ≥ 0)
        valid = [e for e in r["events"] if e["status"] in ("ok", "no_detections")]
        bad = [e["event_id"] for e in valid if e["e2e_ms"] + 1e-6 < e["queue_ms"] + e["inference_ms"]]
        check("m1_e2e_ms_p95", f"{rid}: e2e ≥ cola + inferencia en cada evento válido", 0, len(bad), not bad)
        # M2 · los frames perdidos por saltos de frame_index cuadran con la fuente
        lost = sum(x["detail"]["lost"] for x in series(rows, "m2_delivery_ratio"))
        gaps = sum(e["status"] == "source_gap" for e in r["events"])
        dropped = r["man"]["summary"]["source"]["dropped"]
        out_frames = dropped.get("outage", 0) + dropped.get("saturation", 0) * r["man"]["source"]["sample_every"]
        if r["source_events"] and any(s["kind"] == "connection_lost" for s in r["source_events"]):
            check("m2_delivery_ratio", f"{rid}: pérdida por saltos = huecos del watchdog (± 1)",
                  gaps, lost, abs(lost - gaps) <= 1)
            check("m2_delivery_ratio", f"{rid}: pérdida por saltos = frames del corte / muestreo (± 1)",
                  out_frames / r["man"]["source"]["sample_every"], lost,
                  abs(lost - out_frames / r["man"]["source"]["sample_every"]) <= 1)
        else:
            check("m2_delivery_ratio", f"{rid}: sin corte ni saturación → entrega 1.0 en todas las ventanas",
                  "todas 1.0", sorted({x["value"] for x in series(rows, "m2_delivery_ratio")}),
                  all(x["value"] == 1.0 for x in series(rows, "m2_delivery_ratio")) and lost == 0 and not out_frames)

    # M3 · caso controlado: en S2 las ventanas desenfocadas superan a todas las normales
    for rid, r in runs.items():
        sw = r["man"]["source"].get("switch")
        if not sw:
            continue
        idx_of = {e["seq"]: e["frame_index"] for e in r["events"]}
        blurred = {w["window_id"]: all(sw["from_frame"] <= idx_of[s] < sw["to_frame"]
                                       for s in range(w["first_seq"], w["last_seq"] + 1))
                   for w in r["windows"]}
        psi = {x["window_id"]: x["value"] for x in series(r["rows"], "m3_score_psi")}
        hi = [psi[w] for w, b in blurred.items() if b]
        lo = [psi[w] for w, b in blurred.items() if not b]
        check("m3_score_psi", f"{rid}: PSI mínimo de ventanas desenfocadas > PSI máximo de ventanas normales",
              f"> {max(lo):.3f}", round(min(hi), 3), min(hi) > max(lo))
    ref_run = next((rid for rid, r in runs.items() if r["man"]["scenario"] == "reference"), None)
    if ref_run:
        ref_psi = [x["value"] for x in series(runs[ref_run]["rows"], "m3_score_psi")]
        check("m3_score_psi", "variación propia de la referencia (sus ventanas contra su histograma agregado)",
              "documentada", f"{min(ref_psi):.3f}–{max(ref_psi):.3f}", True)

    bad = [c for c in checks if not c["ok"]]
    fmt = lambda v, n=3: "—" if v is None else (f"{v:.{n}f}" if isinstance(v, float) else str(v))
    md = ["# Métricas adicionales M1–M3", "",
          "Generado con `python scripts/extra_metrics.py " + " ".join(f"--run-id {r}" for r in args.run_id) + "`.",
          "Definiciones: [`docs/metricas-adicionales.md`](../../docs/metricas-adicionales.md). Recálculo independiente: "
          "[`recalculo.md`](recalculo.md).", "",
          f"**Expectativas: {len(checks)} · fallas: {len(bad)}**", "",
          "| Métrica | Expectativa | Esperado | Observado | Resultado |", "|---|---|---|---|---|"]
    md += [f"| {c['metric']} | {c['what']} | {c['expected']} | {c['observed']} | {'ok' if c['ok'] else '**FALLA**'} |"
           for c in checks]
    for rid, r in runs.items():
        md += ["", f"## `{rid}`", "", "| Ventana | M1 e2e p95 (ms) | cola p50 | inferencia p50 | M2 entrega | perdidos | M3 PSI | n dets |",
               "|---|---|---|---|---|---|---|---|"]
        by = {}
        for x in r["rows"]:
            by.setdefault(x["idx"], {})[x["metric_id"]] = x
        for i in sorted(by):
            m1, m2, m3 = (by[i][k] for k in EXTRA_METRICS)
            md.append(f"| w{i:03d} | {fmt(m1['value'], 1)} | {fmt(m1['detail']['queue_ms_p50'], 1)} | "
                      f"{fmt(m1['detail']['inference_ms_p50'], 1)} | {fmt(m2['value'])}"
                      f"{'' if m2['status'] == 'ok' else ' (' + m2['status'] + ')'} | {fmt(m2['detail']['lost'], 0)} | "
                      f"{fmt(m3['value'])}{'' if m3['status'] == 'ok' else ' (' + m3['status'] + ')'} | {m3['n_obs']} |")
    (OUT / "resumen.md").write_text("\n".join(md) + "\n")
    print(f"{len(checks)} expectativas, {len(bad)} fallas")
    for c in bad:
        print("FALLA:", c)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
