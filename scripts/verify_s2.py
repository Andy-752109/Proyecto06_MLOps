"""Verificación del escenario adicional S2 (cambio sostenido normal -> desenfocado -> normal).

S2 recorre los mismos frames que C1 y C2; en el tramo `switch` entrega el frame desenfocado.
Por eso cada ventana de S2 debe coincidir con la ventana del mismo índice de C1 (normal) o de
C2 (desenfocada). El script:

1. Predice cada ventana de S2 a partir de C1/C2 y del tramo declarado, y la compara.
2. Deriva las alertas esperadas con una implementación propia de las reglas (no usa
   monitor.rules) sobre las ventanas predichas, y las compara con alerts.jsonl.
3. Compara cada frame inferido con el mismo frame de C1 o C2.
4. Guarda capturas del portal.

Uso:  python scripts/verify_s2.py --run-id <s2> --c1 <c1> --c2 <c2>
Salida: evidencias/escenarios/s2-cambio-sostenido.{json,md} y s2-*.png. Sale con 1 si algo falla.
"""
import argparse
import json
import sys
from pathlib import Path

from portal_shots import shoot

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidencias/escenarios"


def jl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def run_files(run_id: str) -> dict:
    d = ROOT / "evidencias/runs" / run_id
    return {"man": json.loads((d / "manifest.json").read_text()),
            "snap": json.loads((d / "config.snapshot.json").read_text()),
            "events": jl(d / "events.jsonl"), "windows": jl(d / "windows.jsonl"),
            "alerts": jl(d / "alerts.jsonl"), "evals": jl(d / "rule_evaluations.jsonl"),
            "source_events": jl(d / "source_events.jsonl") if (d / "source_events.jsonl").exists() else []}


def expected_alerts(wins: list[dict], rules: dict, ref_low: float) -> list[dict]:
    """Reglas de confianza aplicadas a mano: (regla, ventana de apertura, ventana que resuelve)."""
    out = []
    for rid, met_fn in (("baja-confianza-v1", lambda w: w["low_prop"] >= rules["baja-confianza-v1"]["threshold"]),
                        ("cambio-sostenido-v1",
                         lambda w: w["low_prop"] - ref_low >= rules["cambio-sostenido-v1"]["threshold"])):
        need, streak, cur = rules[rid]["persistence_windows"], 0, None
        for w in wins:
            if w["state"] != "eligible":
                continue  # no evalúa, no rompe la racha
            if met_fn(w):
                streak += 1
                if cur is None and streak >= need:
                    cur = {"rule_id": rid, "fired_at": w["idx"], "resolved_by": None}
                    out.append(cur)
            else:
                streak = 0
                if cur is not None:
                    cur["resolved_by"], cur = w["idx"], None
    return sorted(out, key=lambda a: (a["fired_at"], a["rule_id"]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--c1", required=True)
    ap.add_argument("--c2", required=True)
    args = ap.parse_args()
    s2, c1, c2 = run_files(args.run_id), run_files(args.c1), run_files(args.c2)
    man, src = s2["man"], s2["man"]["source"]
    sw = src["switch"]
    rules = {r["rule_id"]: r for r in s2["snap"]["alerts"]}
    ref_low = man["reference"]["low_prop"]
    checks = []

    def check(stage, what, expected, observed, ok):
        checks.append({"stage": stage, "what": what, "expected": expected, "observed": observed, "ok": bool(ok)})

    # 0 · Identidad: misma configuración, modelo y referencia que C1/C2
    ident = lambda m: [m["config_ref"], m["model_ref"], m["reference"]["sha256"]]
    check("0 identidad", "misma configuración, modelo y referencia que C1 y C2",
          ident(c1["man"]), ident(man), ident(man) == ident(c1["man"]) == ident(c2["man"]))

    # 1 · Transición declarada
    sev = [(e["kind"], e["detail"]["frame_index"]) for e in s2["source_events"]]
    check("1 transición", "la entrada cambia en los frames declarados",
          [("switch_on", sw["from_frame"]), ("switch_off", sw["to_frame"])], sev,
          sev == [("switch_on", sw["from_frame"]), ("switch_off", sw["to_frame"])])

    # 2 · Ventanas: cada una igual a la de C1 o C2 según el tramo
    c1w = {w["idx"]: w for w in c1["windows"]}
    c2w = {w["idx"]: w for w in c2["windows"]}
    ev_by_seq = {e["seq"]: e for e in s2["events"]}
    predicted, keys = [], ("n_valid", "n_dets", "n_low", "low_prop", "state")
    for w in s2["windows"]:
        idxs = [ev_by_seq[s]["frame_index"] for s in range(w["first_seq"], w["last_seq"] + 1)]
        blurred = [sw["from_frame"] <= i < sw["to_frame"] for i in idxs]
        seg = "desenfocada" if all(blurred) else ("normal" if not any(blurred) else "mixta")
        base = {"desenfocada": c2w, "normal": c1w}.get(seg, {}).get(w["idx"])
        exp = {k: base[k] for k in keys} if base else None
        predicted.append(dict(exp or {}, idx=w["idx"], seg=seg))
        check("2 ventanas", f"w{w['idx']:03d} ({seg}) igual a la ventana {w['idx']} de "
              f"{'C2' if seg == 'desenfocada' else 'C1'}", exp, {k: w[k] for k in keys}, exp == {k: w[k] for k in keys})

    # 3 · Frames: puntuaciones idénticas a C1 (normal) o C2 (desenfocado)
    c1f = {e["frame_index"]: e for e in c1["events"]}
    c2f = {e["frame_index"]: e for e in c2["events"]}
    scores = lambda e: [d["score"] for d in e["detections"]]
    same = {"normal": [0, 0], "desenfocado": [0, 0]}
    for e in s2["events"]:
        blurred = sw["from_frame"] <= e["frame_index"] < sw["to_frame"]
        other = (c2f if blurred else c1f).get(e["frame_index"])
        k = "desenfocado" if blurred else "normal"
        same[k][1] += 1
        same[k][0] += bool(other) and scores(other) == scores(e)
    for k, (eq, n) in same.items():
        check("3 frames", f"frames {k}s con las mismas puntuaciones que en {'C2' if k == 'desenfocado' else 'C1'}",
              f"{n} de {n}", eq, eq == n)

    # 4 · Alertas: derivadas a mano sobre las ventanas predichas
    exp = expected_alerts([p for p in predicted if "state" in p], rules, ref_low)
    widx = {w["window_id"]: w["idx"] for w in s2["windows"]}
    resolved_idx = lambda a: widx.get((a["observed"].get("resolved_by") or {}).get("window_id"))
    # window_ids empieza con la racha que abrió la alerta: se abre en su ventana número `persistence`
    obs = sorted(({"rule_id": a["rule_id"],
                   "fired_at": widx[a["window_ids"][rules[a["rule_id"]]["persistence_windows"] - 1]],
                   "resolved_by": resolved_idx(a)} for a in s2["alerts"]),
                 key=lambda a: (a["fired_at"], a["rule_id"]))
    check("4 alertas", "alertas abiertas y resueltas en las ventanas que predicen las reglas", exp, obs, exp == obs)
    pre = [a for a in s2["alerts"] if widx[a["first_window_id"]] < min(p["idx"] for p in predicted if p["seg"] == "desenfocada")]
    check("4 alertas", "ninguna alerta antes del cambio de entrada", 0, len(pre), not pre)
    sust = [a for a in s2["alerts"] if a["rule_id"] == "cambio-sostenido-v1"]
    acc = [(widx[e["window_id"]], e["outcome"]) for e in s2["evals"] if e["rule_id"] == "cambio-sostenido-v1"
           and e["outcome"] in ("accumulating", "fired", "continuing", "resolved")]
    outs = [o for _, o in acc]
    before_fire = outs[max(0, outs.index("fired") - 2):outs.index("fired") + 1] if "fired" in outs else outs
    check("4 alertas", "la regla sostenida acumula 1/3 y 2/3 justo antes de abrirse",
          ["accumulating", "accumulating", "fired"], before_fire,
          before_fire == ["accumulating", "accumulating", "fired"])

    # 5 · Recuperación y verificación posterior
    back = next(p["idx"] for p in predicted if p["idx"] > 0 and p["seg"] == "normal"
                and predicted[p["idx"] - 1]["seg"] == "desenfocada")
    open_at_back = [a for a in s2["alerts"] if resolved_idx(a) is None or resolved_idx(a) >= back]
    check("5 recuperación", "las alertas abiertas al volver la entrada normal se resuelven en la primera ventana normal",
          {a["alert_id"].split("-")[-1]: back for a in open_at_back},
          {a["alert_id"].split("-")[-1]: resolved_idx(a) for a in open_at_back},
          open_at_back and all(resolved_idx(a) == back for a in open_at_back))
    check("5 recuperación", "ninguna alerta abierta al terminar", 0,
          sum(a["status"] == "open" for a in s2["alerts"]), not any(a["status"] == "open" for a in s2["alerts"]))
    post = [w for w in s2["windows"] if w["idx"] >= back]
    check("5 recuperación", "ventanas posteriores elegibles y por debajo del umbral",
          f"eligible y low_prop < {rules['baja-confianza-v1']['threshold']}",
          [(w["state"], round(w["low_prop"], 3)) for w in post],
          all(w["state"] == "eligible" and w["low_prop"] < rules["baja-confianza-v1"]["threshold"] for w in post))
    imgs = [p for a in s2["alerts"] for p in a["image_refs"]]
    check("5 recuperación", "las capturas vinculadas a las alertas existen", len(imgs),
          sum((ROOT / p).is_file() for p in imgs), all((ROOT / p).is_file() for p in imgs))

    bad = [c for c in checks if not c["ok"]]
    OUT.mkdir(parents=True, exist_ok=True)
    sust_id = sust[0]["alert_id"] if sust else ""
    shots = shoot([
        ("s2-01-ejecucion", f"/ejecuciones/{args.run_id}", "Ventanas, cambios de entrada y alertas de S2"),
        ("s2-02-alertas", f"/alertas?run_id={args.run_id}", "Alertas de S2: todas resueltas"),
        ("s2-03-alerta-sostenida", f"/alertas/{sust_id}", "cambio-sostenido-v1: ventanas, delta contra la referencia, capturas y resolución"),
        ("s2-04-tablero", f"/tablero?run_id={args.run_id}&run_id={args.c1}&run_id={args.c2}",
         "S2 entre C1 y C2: sube con el desenfoque y vuelve a C1"),
    ], OUT)
    (OUT / "s2-cambio-sostenido.json").write_text(json.dumps(
        {"run_id": args.run_id, "c1": args.c1, "c2": args.c2, "n_checks": len(checks), "n_failed": len(bad),
         "predicted_windows": predicted, "expected_alerts": exp, "checks": checks}, indent=1, ensure_ascii=False))

    def wrow(w):
        p = predicted[w["idx"]]
        marks = ", ".join(f"{e['rule_id']}: {e['outcome']}" for e in s2["evals"] if e["window_id"] == w["window_id"]
                          and e["outcome"] in ("fired", "continuing", "resolved", "accumulating")) or "—"
        delta = w["low_prop"] - ref_low
        return (f"| `w{w['idx']:03d}` | {p['seg']} | {w['n_low']}/{w['n_dets']} | {w['low_prop']:.3f} | "
                f"{delta:+.3f} | {w['state']} | {marks} |")
    alert_rows = "\n".join(
        f"| `{a['alert_id'].split('-')[-1]}` | {a['rule_id']} | {a['severity']} | "
        f"{', '.join('w' + w.split('-w')[-1] for w in a['window_ids'])} | "
        f"{'w' + a['observed']['resolved_by']['window_id'].split('-w')[-1] if a.get('observed', {}).get('resolved_by') else '—'} | "
        f"{a['status']} | {len(a['image_refs'])} |" for a in s2["alerts"])
    rows = "\n".join(f"| {c['stage']} | {c['what']} | {c['expected']} | {c['observed']} | {'ok' if c['ok'] else '**FALLA**'} |"
                     for c in checks)
    shot_rows = "\n".join(f"| `{s['png']}` | `{s['url']}` | {s['status']} | {s['what']} |" for s in shots)
    (OUT / "s2-cambio-sostenido.md").write_text(f"""# S2 · Cambio sostenido de confianza: normal → desenfocado → normal

Ejecución `{args.run_id}` · commit `{(man['git_commit'] or 'sin git')[:7]}` (git_dirty={man['git_dirty']}) ·
`{man['config_ref']}` (la misma que C1/C2) · `{man['model_ref']}` · fuente `{man['source_ref']}` ·
referencia `low_prop` = {ref_low}.

Generado con `python scripts/verify_s2.py --run-id {args.run_id} --c1 {args.c1} --c2 {args.c2}`.
**{len(checks)} expectativas, {len(bad)} fallas.**

## Entrada

Tramo de C1 (`vtest.avi`, frames 400–794, 10 fps, muestreo 1/2). Entre los frames
{sw['from_frame']} y {sw['to_frame'] - 1} la fuente entrega el frame del mismo índice de
`{sw['path']}` (el video de C2). Con 20 frames procesados por ventana (40 frames del archivo),
ese tramo son exactamente las ventanas 2–7: ninguna ventana mezcla entradas.

## Esperado (antes de ejecutar)

Como C1 y C2 ya observaron esos mismos frames, cada ventana de S2 debe repetir la ventana del
mismo índice de C1 (normal) o C2 (desenfocada). Aplicando las reglas a esas ventanas
predichas (implementación propia de este script, no `monitor.rules`):

| Regla | Abre en | Se resuelve en |
|---|---|---|
""" + "\n".join(f"| {a['rule_id']} | w{a['fired_at']:03d} | {'w%03d' % a['resolved_by'] if a['resolved_by'] is not None else 'sigue abierta'} |" for a in exp) + f"""

## Observado: ventanas

| Ventana | Entrada | low/dets | low_prop | Δ vs. referencia | Estado | Reglas |
|---|---|---|---|---|---|---|
""" + "\n".join(wrow(w) for w in s2["windows"]) + f"""

## Observado: alertas

| Alerta | Regla | Severidad | Ventanas | Resuelta en | Estado | Capturas |
|---|---|---|---|---|---|---|
{alert_rows}

## Expectativas

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
