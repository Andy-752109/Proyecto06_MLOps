"""Verificación del escenario adicional S1 (interrupción y recuperación del stream).

Comprueba cada etapa (antes, fallo, diagnóstico, reacción, recuperación, verificación
posterior) contra expectativas declaradas en config/scenarios.yaml y config/monitor.yaml,
usando solo los JSONL de la ejecución. Compara además cada frame inferido con el mismo
frame de C1 (mismo video, modelo y configuración).

Uso:  python scripts/verify_s1.py --run-id <s1> --c1 <c1>
Salida: evidencias/escenarios/s1-interrupcion.{json,md} y capturas del portal s1-*.png. Sale con 1 si alguna expectativa falla.
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
    src = man["source"]
    outage, wd = src["fault_injection"]["outage"], src["watchdog"]["gap_after_s"]
    interval = src["sample_every"] / man["summary"]["source"]["native_fps"]
    rules = {r["rule_id"]: r for r in snap["alerts"]}
    need_ins = rules["evidencia-insuficiente-v1"]["persistence_windows"]
    evs, wins = jl(d / "events.jsonl"), jl(d / "windows.jsonl")
    sev, alerts, evals = jl(d / "source_events.jsonl"), jl(d / "alerts.jsonl"), jl(d / "rule_evaluations.jsonl")
    lost = next(s for s in sev if s["kind"] == "connection_lost")
    back = next(s for s in sev if s["kind"] == "reconnected")
    fails = [s for s in sev if s["kind"] == "reconnect_failed"]
    gaps = [e for e in evs if e["status"] == "source_gap"]
    win_of = {w["window_id"]: w for w in wins}
    checks = []

    def check(stage, what, expected, observed, ok):
        checks.append({"stage": stage, "what": what, "expected": expected, "observed": observed, "ok": bool(ok)})

    # 1 · Antes del fallo
    pre = [w for w in wins if ts(w["end_at"]) < ts(lost["ts"])]
    check("1 antes", "ventanas cerradas antes del corte son elegibles",
          "todas eligible", [w["state"] for w in pre], pre and all(w["state"] == "eligible" for w in pre))
    check("1 antes", "sin alertas abiertas antes del corte", 0,
          sum(ts(a["opened_at"]) < ts(lost["ts"]) for a in alerts),
          not any(ts(a["opened_at"]) < ts(lost["ts"]) for a in alerts))

    # 2 · Fallo inyectado
    check("2 fallo", "la conexión se pierde en el frame declarado", outage["at_frame"],
          lost["detail"]["frame_index"], lost["detail"]["frame_index"] == outage["at_frame"])
    last_before = max((e for e in evs if e["status"] != "source_gap" and ts(e["captured_at"]) <= ts(lost["ts"])),
                      key=lambda e: e["seq"])
    check("2 fallo", "ningún frame inferido con índice entre el corte y la reconexión",
          f"ninguno en [{outage['at_frame']}, {back['detail']['frame_index']})",
          [e["frame_index"] for e in evs if e["frame_index"] is not None
           and outage["at_frame"] <= e["frame_index"] < back["detail"]["frame_index"]],
          not any(e["frame_index"] is not None and outage["at_frame"] <= e["frame_index"] < back["detail"]["frame_index"]
                  for e in evs))

    # 3 · Diagnóstico: el watchdog convierte el silencio en huecos trazables
    first_gap = min(gaps, key=lambda e: e["seq"])
    delay = ts(first_gap["captured_at"]) - ts(last_before["captured_at"])
    check("3 diagnóstico", "primer hueco detectado tras el periodo de gracia del watchdog",
          f"{wd} s ≤ retraso ≤ {wd + 2 * interval:.1f} s desde el último frame", round(delay, 3),
          wd <= delay <= wd + 2 * interval)
    expected_gaps = back["detail"]["outage_s"] / interval
    check("3 diagnóstico", "un hueco por frame esperado durante el silencio",
          f"≈ {expected_gaps:.0f} (± 3)", len(gaps), abs(len(gaps) - expected_gaps) <= 3)
    check("3 diagnóstico", "huecos sin frame, sin inferencia, sin imagen y con detalle",
          "frame_id/inference_ms/image_ref nulos, error con texto",
          sum(1 for g in gaps if g["frame_id"] is None and g["inference_ms"] is None
              and g["image_ref"] is None and g["error"]), all(g["frame_id"] is None and g["inference_ms"] is None
                                                              and g["image_ref"] is None and g["error"] for g in gaps))
    gap_wins = sorted({g["window_id"] for g in gaps})
    check("3 diagnóstico", "ventanas con huecos quedan insuficientes (no normales)", "todas insufficient",
          {w: win_of[w]["state"] for w in gap_wins}, all(win_of[w]["state"] == "insufficient" for w in gap_wins))
    ins = [a for a in alerts if a["rule_id"] == "evidencia-insuficiente-v1"]
    ins_wins = [w["window_id"] for w in wins if w["state"] == "insufficient"]
    check("3 diagnóstico", f"evidencia-insuficiente-v1 se abre al cumplir {need_ins} ventanas insuficientes",
          f"1 alerta, abierta en {ins_wins[need_ins - 1] if len(ins_wins) >= need_ins else '—'}",
          [(a["alert_id"], a["window_ids"][need_ins - 1]) for a in ins],
          len(ins) == 1 and ins[0]["window_ids"][need_ins - 1] == ins_wins[need_ins - 1])
    conf_evals = [e for e in evals if e["rule_id"] != "evidencia-insuficiente-v1" and win_of[e["window_id"]]["state"] == "insufficient"]
    check("3 diagnóstico", "reglas de confianza no se evalúan con evidencia insuficiente",
          "insufficient_evidence", sorted({e["outcome"] for e in conf_evals}),
          {e["outcome"] for e in conf_evals} == {"insufficient_evidence"})

    # 4 · Reacción: reintentos de conexión
    gaps_between = [ts(b["ts"]) - ts(a["ts"]) for a, b in zip([lost] + fails, fails + [back])]
    check("4 reacción", f"reintentos cada {outage['reconnect_every_s']} s hasta superar {outage['duration_s']} s",
          f"{int(outage['duration_s'] // outage['reconnect_every_s'])} reintentos fallidos + 1 exitoso",
          f"{len(fails)} fallidos, intervalo {min(gaps_between):.2f}–{max(gaps_between):.2f} s",
          len(fails) == int(outage["duration_s"] // outage["reconnect_every_s"])
          and all(abs(x - outage["reconnect_every_s"]) < 0.3 for x in gaps_between))
    check("4 reacción", "frames perdidos = posición en vivo − frame del corte = descarte 'outage'",
          back["detail"]["frame_index"] - outage["at_frame"],
          [back["detail"]["frames_lost"], man["summary"]["source"]["dropped"].get("outage")],
          back["detail"]["frames_lost"] == man["summary"]["source"]["dropped"].get("outage")
          == back["detail"]["frame_index"] - outage["at_frame"])

    # 5 · Recuperación
    first_ok = next((w for w in wins if ts(w["end_at"]) > ts(back["ts"]) and w["state"] == "eligible"), None)
    resolved_by = (ins[0]["observed"].get("resolved_by") or {}).get("window_id") if ins else None
    check("5 recuperación", "la alerta se resuelve en la primera ventana elegible tras reconectar",
          first_ok["window_id"] if first_ok else None, [ins[0]["status"] if ins else None, resolved_by],
          ins and ins[0]["status"] == "resolved" and resolved_by == (first_ok or {}).get("window_id"))
    check("5 recuperación", "resolución posterior a la reconexión",
          f"> {back['ts']}", ins[0]["resolved_at"] if ins else None,
          ins and ins[0]["resolved_at"] and ts(ins[0]["resolved_at"]) > ts(back["ts"]))

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
    inferred = [e for e in evs if e["frame_index"] is not None]
    same = [e for e in inferred if e["frame_index"] in c1 and
            [x["score"] for x in e["detections"]] == [x["score"] for x in c1[e["frame_index"]]["detections"]]]
    check("6 posterior", "cada frame inferido tiene las mismas puntuaciones que en C1",
          f"{len(inferred)} de {len(inferred)}", len(same), len(same) == len(inferred))
    c1_man = json.loads((ROOT / "evidencias/runs" / args.c1 / "manifest.json").read_text())
    mine, theirs = [man["config_ref"], man["model_ref"]], [c1_man["config_ref"], c1_man["model_ref"]]
    check("6 posterior", "misma configuración y modelo que C1", theirs, mine, mine == theirs)

    bad = [c for c in checks if not c["ok"]]
    OUT.mkdir(parents=True, exist_ok=True)
    alert_id = ins[0]["alert_id"] if ins else ""
    gap_id = first_gap["event_id"]
    shots = shoot([
        ("s1-01-ejecucion", f"/ejecuciones/{args.run_id}", "Falla inyectada, ventanas, eventos de conexión y huecos"),
        ("s1-02-huecos", f"/eventos?run_id={args.run_id}&status=source_gap", "Eventos source_gap del watchdog"),
        ("s1-03-hueco", f"/eventos/{gap_id}", "Primer hueco: sin frame, sin inferencia, con detalle"),
        ("s1-04-alerta", f"/alertas/{alert_id}", "evidencia-insuficiente-v1: ventanas, eventos y resolución"),
        ("s1-05-tablero", f"/tablero?run_id={args.run_id}&run_id={args.c1}",
         "S1 junto a C1: ventanas insuficientes (huecas), métricas sin datos (✕) y la franja de la alerta"),
    ], OUT)
    (OUT / "s1-interrupcion.json").write_text(json.dumps(
        {"run_id": args.run_id, "c1": args.c1, "n_checks": len(checks), "n_failed": len(bad),
         "source_events": sev, "checks": checks}, indent=1, ensure_ascii=False))
    timeline = "\n".join(f"| {s['seq']} | `{s['ts']}` | {s['kind']} | `{json.dumps(s['detail'], ensure_ascii=False)}` |" for s in sev)
    def wrow(w):
        lp = "—" if w["low_prop"] is None else f"{w['low_prop']:.3f}"
        n_gaps = w["n_events"] - w["n_ok"] - w["n_no_detections"] - w["n_errors"]
        marks = ", ".join(f"{e['rule_id']}: {e['outcome']}" for e in evals if e["window_id"] == w["window_id"]
                          and e["outcome"] in ("fired", "continuing", "resolved", "accumulating")) or "—"
        return (f"| `{w['window_id'].split('-')[-1]}` | `{w['start_at'][11:23]}`–`{w['end_at'][11:23]}` | "
                f"{w['n_events']} | {w['n_valid']} | {n_gaps} | {w['n_dets']} | {lp} | {w['state']} | {marks} |")
    wtable = "\n".join(wrow(w) for w in wins)
    shot_rows = "\n".join(f"| `{s['png']}` | `{s['url']}` | {s['status']} | {s['what']} |" for s in shots)
    rows = "\n".join(f"| {c['stage']} | {c['what']} | {c['expected']} | {c['observed']} | {'ok' if c['ok'] else '**FALLA**'} |"
                     for c in checks)
    (OUT / "s1-interrupcion.md").write_text(f"""# S1 · Interrupción y recuperación del stream

Ejecución `{args.run_id}` · commit `{(man['git_commit'] or 'sin git')[:7]}` (git_dirty={man['git_dirty']}) ·
`{man['config_ref']}` (la misma que C1/C2) · `{man['model_ref']}` · fuente `{man['source_ref']}`.

Generado con `python scripts/verify_s1.py --run-id {args.run_id} --c1 {args.c1}` a partir de los
JSONL de la ejecución. **{len(checks)} expectativas, {len(bad)} fallas.**

## Entrada y falla inyectada

Tramo de C1 (`vtest.avi`, frames 400–794, ritmo nativo 10 fps, muestreo 1/2). La fuente pierde la
conexión en el frame {outage['at_frame']} durante {outage['duration_s']} s y reintenta cada
{outage['reconnect_every_s']} s; al reconectar retoma en la posición en vivo. El watchdog del
pipeline registra un evento `source_gap` por cada frame esperado ({interval:.1f} s) que no llega
tras {wd} s de silencio.

## Línea de tiempo de la fuente (`source_events.jsonl`)

| # | Momento (UTC) | Tipo | Detalle |
|---|---|---|---|
{timeline}

## Ventanas (`windows.jsonl`, `rule_evaluations.jsonl`)

| Ventana | Inicio–fin | Eventos | Frames válidos | Huecos | Detecciones | low_prop | Estado | Reglas |
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
