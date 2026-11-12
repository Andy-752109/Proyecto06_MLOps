"""Verificación del escenario adicional S3 (error de inferencia con reacción y recuperación).

Comprueba cada etapa (antes, fallo, diagnóstico, reacción, recuperación, verificación
posterior) contra expectativas declaradas en config/scenarios.yaml y config/monitor.yaml,
usando solo los JSONL de la ejecución. Compara además cada frame inferido con el mismo
frame de C1 (mismo video, modelo y configuración).

Uso:  python scripts/verify_s3.py --run-id <s3> --c1 <c1>
Salida: evidencias/escenarios/s3-error-inferencia.{json,md} y capturas del portal s3-*.png. Sale con 1 si alguna expectativa falla.
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from portal_shots import shoot

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidencias/escenarios"


def jl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def ts(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--c1", required=True)
    args = ap.parse_args()
    d = ROOT / "evidencias/runs" / args.run_id
    man = json.loads((d / "manifest.json").read_text())
    snap = json.loads((d / "config.snapshot.json").read_text())
    fault = man["source"]["fault_injection"]["inference_error"]
    k = man["recovery"]["reload_after_errors"]
    rules = {r["rule_id"]: r for r in snap["alerts"]}
    need_ins = rules["evidencia-insuficiente-v1"]["persistence_windows"]
    wcfg, cap = snap["windows"], snap["capture"]
    evs, wins = jl(d / "events.jsonl"), jl(d / "windows.jsonl")
    oper, alerts, evals = jl(d / "source_events.jsonl"), jl(d / "alerts.jsonl"), jl(d / "rule_evaluations.jsonl")
    mets = jl(d / "metrics.jsonl")
    failed = next(s for s in oper if s["kind"] == "inference_failed")
    reloads = [s for s in oper if s["kind"] == "detector_reloaded"]
    recovered = next(s for s in oper if s["kind"] == "inference_recovered")
    errors = [e for e in evs if e["status"] == "error"]
    in_range = [e for e in evs if fault["from_frame"] <= e["frame_index"] < fault["to_frame"]]
    win_of = {w["window_id"]: w for w in wins}
    met = {(m["window_id"], m["metric_id"]): m for m in mets}
    checks = []

    def check(stage, what, expected, observed, ok):
        checks.append({"stage": stage, "what": what, "expected": expected, "observed": observed, "ok": bool(ok)})

    # 1 · Antes del fallo
    pre = [w for w in wins if ts(w["end_at"]) < ts(failed["ts"])]
    check("1 antes", "ventanas cerradas antes del primer error son elegibles",
          "todas eligible", [w["state"] for w in pre], pre and all(w["state"] == "eligible" for w in pre))
    check("1 antes", "sin alertas abiertas antes del primer error", 0,
          sum(ts(a["opened_at"]) < ts(failed["ts"]) for a in alerts),
          not any(ts(a["opened_at"]) < ts(failed["ts"]) for a in alerts))

    # 2 · Fallo inyectado: la fuente entrega los frames, la inferencia falla
    check("2 fallo", "los eventos con error son exactamente los frames del tramo declarado",
          f"índice en [{fault['from_frame']}, {fault['to_frame']}) ({len(in_range)} eventos)",
          f"{len(errors)} errores, frames {errors[0]['frame_index']}–{errors[-1]['frame_index']}" if errors else "ninguno",
          [e["event_id"] for e in errors] == [e["event_id"] for e in in_range] and errors)
    check("2 fallo", "la fuente no pierde frames: sin huecos ni descartes por saturación",
          "0 source_gap, 0 saturation, índices consecutivos de 2 en 2",
          [sum(e["status"] == "source_gap" for e in evs), man["summary"]["source"]["dropped"].get("saturation", 0)],
          not any(e["status"] == "source_gap" for e in evs)
          and not man["summary"]["source"]["dropped"].get("saturation")
          and all(b["frame_index"] - a["frame_index"] == man["source"]["sample_every"] for a, b in zip(evs, evs[1:])))
    check("2 fallo", "cada error conserva el frame, el modelo y el detalle, sin puntuaciones",
          "frame_id y model_sha256 presentes; error con texto; sin detecciones, inference_ms ni max_score",
          sum(1 for e in errors if e["frame_id"] and e["model_sha256"] and "InjectedInferenceError" in (e["error"] or "")
              and not e["detections"] and e["inference_ms"] is None and e["max_score"] is None),
          all(e["frame_id"] and e["model_sha256"] and "InjectedInferenceError" in (e["error"] or "")
              and not e["detections"] and e["inference_ms"] is None and e["max_score"] is None for e in errors))

    # 3 · Diagnóstico
    check("3 diagnóstico", "el primer error queda registrado en la línea de tiempo del detector",
          f"inference_failed en el frame {fault['from_frame']}", [failed["kind"], failed["detail"]["frame_index"]],
          failed["detail"]["frame_index"] == fault["from_frame"])
    shots_err = [e for e in errors if e["capture_reason"] == "error"]
    gaps = [b["seq"] - a["seq"] for a, b in zip(shots_err, shots_err[1:])]
    check("3 diagnóstico", f"se capturan frames con error (máx. 1 cada {cap['flagged_min_gap']}) y las imágenes existen",
          f"≈ {len(errors) // cap['flagged_min_gap']} capturas 'error', separación ≥ {cap['flagged_min_gap']}",
          f"{len(shots_err)} capturas, separación mínima {min(gaps) if gaps else '—'}",
          shots_err and all(g >= cap["flagged_min_gap"] for g in gaps)
          and all((ROOT / e["image_ref"]).is_file() for e in shots_err))
    err_wins = sorted({e["window_id"] for e in errors})
    check("3 diagnóstico", f"ventanas con menos de {wcfg['min_frames']} frames válidos quedan insuficientes",
          "insufficient donde n_valid < mínimo",
          {w.split("-")[-1]: f"{win_of[w]['n_valid']} válidos, {win_of[w]['state']}" for w in err_wins},
          all((win_of[w]["n_valid"] < wcfg["min_frames"]) == (win_of[w]["state"] == "insufficient") for w in err_wins))
    ins = [a for a in alerts if a["rule_id"] == "evidencia-insuficiente-v1"]
    ins_wins = [w["window_id"] for w in wins if w["state"] == "insufficient"]
    check("3 diagnóstico", f"evidencia-insuficiente-v1 se abre al cumplir {need_ins} ventanas insuficientes",
          f"1 alerta, abierta en {ins_wins[need_ins - 1].split('-')[-1] if len(ins_wins) >= need_ins else '—'}",
          [(a["alert_id"].split("-")[-1], a["window_ids"][need_ins - 1].split("-")[-1]) for a in ins],
          len(ins) == 1 and ins[0]["window_ids"][need_ins - 1] == ins_wins[need_ins - 1])
    conf_evals = [e for e in evals if e["rule_id"] != "evidencia-insuficiente-v1"
                  and win_of[e["window_id"]]["state"] == "insufficient"]
    check("3 diagnóstico", "reglas de confianza no se evalúan con evidencia insuficiente",
          "insufficient_evidence", sorted({e["outcome"] for e in conf_evals}),
          {e["outcome"] for e in conf_evals} == {"insufficient_evidence"})
    all_err = [w for w in err_wins if win_of[w]["n_errors"] == win_of[w]["n_events"]]
    check("3 diagnóstico", "ventanas solo con errores: G1 y G4 sin datos (null, no 0)",
          "no_data", sorted({met[(w, m)]["status"] for w in all_err for m in ("g1_inference_ms_p95", "g4_low_conf_prop")}),
          all_err and all(met[(w, m)]["status"] == "no_data" and met[(w, m)]["value"] is None
                          for w in all_err for m in ("g1_inference_ms_p95", "g4_low_conf_prop")))
    check("3 diagnóstico", "los errores siguen siendo trazables (G5) y la versión no cambió (G6)",
          "G5 = 1.0 y G6 = 1.0 en las ventanas con errores",
          {w.split("-")[-1]: [met[(w, "g5_trace_coverage")]["value"], met[(w, "g6_model_version_match")]["value"]]
           for w in err_wins},
          all(met[(w, "g5_trace_coverage")]["value"] == 1.0 and met[(w, "g6_model_version_match")]["value"] == 1.0
              for w in err_wins))

    # 4 · Reacción: recarga del modelo cada k errores consecutivos
    check("4 reacción", f"el modelo se recarga cada {k} errores consecutivos",
          f"{len(errors) // k} recargas, tras {[k * (i + 1) for i in range(len(errors) // k)]} errores",
          f"{len(reloads)} recargas, tras {[r['detail']['after_errors'] for r in reloads]} errores",
          [r["detail"]["after_errors"] for r in reloads] == [k * (i + 1) for i in range(len(errors) // k)])
    check("4 reacción", "cada recarga verifica el SHA-256: el artefacto es el configurado (no es cambio de versión)",
          f"sha256_match = true, {snap['model']['sha256'][:12]}",
          [(r["detail"]["sha256"], r["detail"]["sha256_match"]) for r in reloads],
          reloads and all(r["detail"]["sha256_match"] and r["detail"]["sha256"] == snap["model"]["sha256"][:12]
                          for r in reloads))

    # 5 · Recuperación
    check("5 recuperación", "la inferencia vuelve a responder en el primer frame tras el tramo",
          f"inference_recovered en el frame {fault['to_frame']} tras {len(errors)} errores",
          [recovered["detail"]["frame_index"], recovered["detail"]["consecutive_errors"], recovered["detail"]["reloads"]],
          recovered["detail"]["frame_index"] == fault["to_frame"]
          and recovered["detail"]["consecutive_errors"] == len(errors) and recovered["detail"]["reloads"] == len(reloads))
    first_ok = next((w for w in wins if ts(w["end_at"]) > ts(recovered["ts"]) and w["state"] == "eligible"), None)
    resolved_by = (ins[0]["observed"].get("resolved_by") or {}).get("window_id") if ins else None
    check("5 recuperación", "la alerta se resuelve en la primera ventana elegible tras recuperarse",
          first_ok["window_id"].split("-")[-1] if first_ok else None,
          [ins[0]["status"] if ins else None, resolved_by.split("-")[-1] if resolved_by else None],
          ins and ins[0]["status"] == "resolved" and resolved_by == (first_ok or {}).get("window_id"))

    # 6 · Verificación posterior
    after = [w for w in wins if first_ok and w["idx"] >= first_ok["idx"]]
    check("6 posterior", "todas las ventanas desde la recuperación son elegibles",
          "todas eligible", [w["state"] for w in after], after and all(w["state"] == "eligible" for w in after))
    check("6 posterior", "ninguna alerta abierta al terminar", 0,
          sum(a["status"] == "open" for a in alerts), not any(a["status"] == "open" for a in alerts))
    check("6 posterior", "low_prop tras la recuperación por debajo de 0.40 (como C1)",
          f"< {rules['baja-confianza-v1']['threshold']}", [round(w["low_prop"], 3) for w in after],
          all(w["low_prop"] < rules["baja-confianza-v1"]["threshold"] for w in after))
    c1 = {e["frame_index"]: e for e in jl(ROOT / "evidencias/runs" / args.c1 / "events.jsonl")}
    inferred = [e for e in evs if e["status"] != "error"]
    same = [e for e in inferred if e["frame_index"] in c1 and
            [x["score"] for x in e["detections"]] == [x["score"] for x in c1[e["frame_index"]]["detections"]]]
    post = [e for e in inferred if e["frame_index"] >= fault["to_frame"]]
    check("6 posterior", "cada frame inferido (antes y después de las recargas) tiene las mismas puntuaciones que en C1",
          f"{len(inferred)} de {len(inferred)} ({len(post)} después de recuperarse)", len(same), len(same) == len(inferred))
    c1_man = json.loads((ROOT / "evidencias/runs" / args.c1 / "manifest.json").read_text())
    mine, theirs = [man["config_ref"], man["model_ref"]], [c1_man["config_ref"], c1_man["model_ref"]]
    check("6 posterior", "misma configuración y modelo que C1", theirs, mine, mine == theirs)

    bad = [c for c in checks if not c["ok"]]
    OUT.mkdir(parents=True, exist_ok=True)
    alert_id = ins[0]["alert_id"] if ins else ""
    shots = shoot([
        ("s3-01-ejecucion", f"/ejecuciones/{args.run_id}", "Falla inyectada, ventanas y línea de tiempo del detector"),
        ("s3-02-errores", f"/eventos?run_id={args.run_id}&status=error", "Eventos con error de inferencia"),
        ("s3-03-error", f"/eventos/{shots_err[0]['event_id']}", "Primer error capturado: frame, detalle y sin puntuaciones"),
        ("s3-04-alerta", f"/alertas/{alert_id}", "evidencia-insuficiente-v1: ventanas, capturas de error y resolución"),
        ("s3-05-tablero", f"/tablero?run_id={args.run_id}&run_id={args.c1}",
         "S3 junto a C1: ventanas insuficientes, G1/G4 sin datos (✕) y la franja de la alerta"),
    ], OUT, port=8772)
    (OUT / "s3-error-inferencia.json").write_text(json.dumps(
        {"run_id": args.run_id, "c1": args.c1, "n_checks": len(checks), "n_failed": len(bad),
         "timeline": oper, "checks": checks}, indent=1, ensure_ascii=False))
    timeline = "\n".join(f"| {s['seq']} | `{s['ts']}` | {s['kind']} | `{json.dumps(s['detail'], ensure_ascii=False)}` |"
                         for s in oper)

    def wrow(w):
        lp = "—" if w["low_prop"] is None else f"{w['low_prop']:.3f}"
        marks = ", ".join(f"{e['rule_id']}: {e['outcome']}" for e in evals if e["window_id"] == w["window_id"]
                          and e["outcome"] in ("fired", "continuing", "resolved", "accumulating")) or "—"
        g1 = met[(w["window_id"], "g1_inference_ms_p95")]["value"]
        return (f"| `{w['window_id'].split('-')[-1]}` | {w['n_events']} | {w['n_errors']} | {w['n_valid']} | "
                f"{w['n_dets']} | {lp} | {'—' if g1 is None else f'{g1:.1f}'} | {w['state']} | {marks} |")
    wtable = "\n".join(wrow(w) for w in wins)
    shot_rows = "\n".join(f"| `{s['png']}` | `{s['url']}` | {s['status']} | {s['what']} |" for s in shots)
    rows = "\n".join(f"| {c['stage']} | {c['what']} | {c['expected']} | {c['observed']} | {'ok' if c['ok'] else '**FALLA**'} |"
                     for c in checks)
    (OUT / "s3-error-inferencia.md").write_text(f"""# S3 · Error de inferencia con reacción y recuperación

Ejecución `{args.run_id}` · commit `{(man['git_commit'] or 'sin git')[:7]}` (git_dirty={man['git_dirty']}) ·
`{man['config_ref']}` (la misma que C1/C2) · `{man['model_ref']}` · fuente `{man['source_ref']}`.

Generado con `python scripts/verify_s3.py --run-id {args.run_id} --c1 {args.c1}` a partir de los
JSONL de la ejecución. **{len(checks)} expectativas, {len(bad)} fallas.**

## Entrada y falla inyectada

Tramo de C1 (`vtest.avi`, frames 400–794, ritmo nativo 10 fps, muestreo 1/2). A diferencia de S1,
la fuente entrega todos los frames: lo que falla es la llamada al modelo para los frames
{fault['from_frame']}–{fault['to_frame'] - 1} (`InjectedInferenceError`). Cada evento queda con estado
`error`, el frame y el detalle, sin puntuaciones (no se cuenta como confianza 0).

**Reacción** (`config/monitor.yaml → recovery`): cada {k} errores consecutivos el monitor vuelve a
cargar el modelo desde disco y comprueba su SHA-256. Así distingue un artefacto cambiado o dañado
(que sería un cambio de versión, G6) de un fallo de ejecución. La causa inyectada no depende del
artefacto, por lo que las recargas confirman la identidad pero no lo resuelven; la inferencia
vuelve a responder cuando termina el tramo y se registra `inference_recovered`.

## Línea de tiempo del detector (`source_events.jsonl`)

| # | Momento (UTC) | Tipo | Detalle |
|---|---|---|---|
{timeline}

## Ventanas (`windows.jsonl`, `metrics.jsonl`, `rule_evaluations.jsonl`)

| Ventana | Eventos | Errores | Frames válidos | Detecciones | low_prop | G1 p95 (ms) | Estado | Reglas |
|---|---|---|---|---|---|---|---|---|
{wtable}

## Expectativas por etapa

| Etapa | Expectativa | Esperado | Observado | Resultado |
|---|---|---|---|---|
{rows}

## Portal

| Captura | Ruta | HTTP | Qué muestra |
|---|---|---|---|
{shot_rows}
""")
    print(f"{len(checks)} expectativas, {len(bad)} fallas")
    for c in bad:
        print("FALLA:", c["stage"], c["what"], c["expected"], c["observed"])
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
