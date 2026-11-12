"""Recorrido de la vista en vivo (adicional F4) durante una ejecución real.

Levanta el portal, ejecuta `monitor.pipeline --scenario <escenario> --live`, consulta
/api/en-vivo cada 0.25 s, guarda una captura de /en-vivo la primera vez que aparece cada
estado (y con la primera alerta abierta) y, al terminar, contrasta el último estado
publicado con lo que la ejecución guardó (manifest.json y alerts.jsonl).

Uso:  python scripts/demo_live.py --scenario s1-interrupcion
Salida: evidencias/en_vivo/{recorrido.md,linea_de_tiempo.json,*.png}. Sale con 1 si algo falla.
"""
import argparse
import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidencias/en_vivo"
PORT = 8769


def get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=2) as r:
        return json.loads(r.read())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="s1-interrupcion")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    live = ROOT / "evidencias/live"
    for f in ("status.json", "frame.jpg"):  # empezar sin estado previo
        (live / f).unlink(missing_ok=True)
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", PORT)) == 0:
            sys.exit(f"el puerto {PORT} está ocupado")
    base = f"http://127.0.0.1:{PORT}"
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "monitor.portal.app:app", "--port", str(PORT)],
                           cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    timeline, shots, checks = [], [], []
    try:
        for _ in range(50):
            try:
                get(base + "/api/en-vivo")
                break
            except Exception:
                time.sleep(0.2)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            page.goto(base + "/en-vivo")
            page.wait_for_timeout(700)

            def shot(name, what):
                page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
                shots.append({"png": f"{name}.png", "what": what})

            shot("00-sin-ejecucion", "Antes de iniciar: no hay estado publicado")
            first = get(base + "/api/en-vivo")["health"]
            pipe = subprocess.Popen([sys.executable, "-m", "monitor.pipeline", "--scenario", args.scenario, "--live"],
                                    cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            seen, prev, alert_shot, recovered = set(), first, False, False
            timeline.append({"t": 0.0, "health": first, "seq": None})
            t0 = time.time()
            while True:
                st = get(base + "/api/en-vivo")
                h = st["health"]
                if h != prev:
                    timeline.append({"t": round(time.time() - t0, 2), "health": h, "seq": (st.get("last_event") or {}).get("seq"),
                                     "alerts_open": [a["alert_id"].split("-")[-1] for a in st.get("alerts_open", [])]})
                    page.wait_for_timeout(700)  # la página consulta cada 0.5 s
                    if h == "en_curso" and "hueco_fuente" in seen and not recovered:
                        recovered = True
                        shot("04-recuperado", "La fuente vuelve a entregar frames tras la reconexión")
                    elif h not in seen:
                        seen.add(h)
                        names = {"en_curso": ("01-en-curso", "Recibiendo frames: cajas por zona, ventana en curso"),
                                 "hueco_fuente": ("02-hueco-fuente", "Corte: el watchdog registra huecos; se conserva el último frame velado"),
                                 "terminada": ("06-terminada", "Fin de la ejecución: último estado publicado")}
                        if h in names:
                            shot(*names[h])
                    prev = h
                if h == "hueco_fuente" and st.get("alerts_open") and not alert_shot:
                    alert_shot = True
                    page.wait_for_timeout(700)
                    shot("03-alerta-abierta", "Durante el corte se abre evidencia-insuficiente-v1 y aparece en la vista")
                if recovered and not st.get("alerts_open") and "05" not in {s["png"][:2] for s in shots}:
                    page.wait_for_timeout(700)
                    shot("05-alerta-resuelta", "Tras la recuperación la alerta se resuelve y sale de la lista")
                if h == "terminada":
                    break
                if pipe.poll() is not None and time.time() - t0 > 120:
                    break  # el pipeline terminó sin publicar "finished": lo registra la comprobación
                time.sleep(0.25)
            out = pipe.communicate()[0]
            browser.close()
    finally:
        srv.terminate()

    final = json.loads((live / "status.json").read_text())
    run_dir = ROOT / "evidencias/runs" / final["run_id"]
    man = json.loads((run_dir / "manifest.json").read_text())
    alerts = [json.loads(x) for x in (run_dir / "alerts.jsonl").read_text().splitlines() if x]

    def check(what, expected, observed):
        checks.append({"what": what, "expected": expected, "observed": observed, "ok": expected == observed})

    by_status = man["summary"]["by_status"]
    check("eventos publicados en vivo = eventos guardados", man["summary"]["events"], final["counts"]["events"])
    check("huecos publicados = huecos guardados", by_status.get("source_gap", 0), final["counts"]["source_gap"])
    check("frames ok publicados = guardados", by_status["ok"], final["counts"]["ok"])
    check("alertas de la ejecución = alerts.jsonl", len(alerts), final["alerts_total"])
    check("alertas abiertas al final = abiertas en alerts.jsonl", sum(a["status"] == "open" for a in alerts),
          len(final["alerts_open"]))
    order = [x["health"] for x in timeline]
    has_outage = bool(man["source"].get("fault_injection"))
    expected_order = ["sin_ejecucion", "en_curso"] + (["hueco_fuente", "en_curso"] if has_outage else []) + ["terminada"]
    check("secuencia de estados de la vista", expected_order, order)
    (OUT / "linea_de_tiempo.json").write_text(json.dumps({"run_id": final["run_id"], "timeline": timeline,
                                                          "final_status": final, "checks": checks},
                                                         indent=1, ensure_ascii=False))
    bad = [c for c in checks if not c["ok"]]
    md = ["# Vista en vivo (F4) · recorrido durante una ejecución real", "",
          f"Generado con `python scripts/demo_live.py --scenario {args.scenario}`. Ejecución "
          f"`{final['run_id']}` (commit `{(man['git_commit'] or '')[:7]}`, git_dirty={man['git_dirty']}), "
          f"lanzada con `--live`.", "",
          f"**{len(checks)} comprobaciones, {len(bad)} fallas.**", "",
          "## Estados observados en `/api/en-vivo` (consulta cada 0.25 s)", "",
          "| t (s) | Estado | Último evento (seq) | Alertas abiertas |", "|---|---|---|---|"]
    md += [f"| {x['t']} | {x['health']} | {x['seq'] if x['seq'] is not None else '—'} | {', '.join(x.get('alerts_open') or []) or '—'} |"
           for x in timeline]
    md += ["", "## Último estado publicado contra lo guardado por la ejecución", "",
           "| Comprobación | Guardado | Publicado en vivo | Resultado |", "|---|---|---|---|"]
    md += [f"| {c['what']} | {c['expected']} | {c['observed']} | {'ok' if c['ok'] else '**FALLA**'} |" for c in checks]
    md += ["", "## Capturas de `/en-vivo`", "", "| Captura | Qué muestra |", "|---|---|"]
    md += [f"| `{s['png']}` | {s['what']} |" for s in shots]
    md += ["", "Los estados `detenido` (sin actualizaciones por más de 3 s sin terminar) y `error` "
           "(estado ilegible) se prueban en `tests/test_live.py` con estados sintéticos."]
    (OUT / "recorrido.md").write_text("\n".join(md) + "\n")
    print(out.splitlines()[-1] if out else "")
    print(f"{len(checks)} comprobaciones, {len(bad)} fallas; estados: {order}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
