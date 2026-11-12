"""Verificación del tablero histórico (adicional F1) con datos reales.

1. Pide /api/tablero para las ejecuciones indicadas y compara cada punto, estado de ventana,
   franja de alerta y conteo del resumen con los JSONL de evidencias/runs/<run_id>/
   (fuente independiente de la base SQLite que lee el portal).
2. Comprueba los estados vacío y de error sobre la base real.
3. Levanta el portal, recorre el flujo en Chromium (selección, clic en un punto, clic en una
   franja de alerta) y guarda capturas.

Uso:  python scripts/verify_dashboard.py --run-id <c2> --run-id <c1> --run-id <reference>
Salida: evidencias/tablero/verificacion.{json,md} y evidencias/tablero/*.png. Sale con 1 si hay diferencias.
"""
import argparse
import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright

from monitor.metrics import BASE_METRICS
from monitor.portal.app import app

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidencias/tablero"
PORT = 8767


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def compare(run: dict) -> list[dict]:
    """Cada comprobación: qué, esperado (JSONL), observado (API), ok."""
    d = ROOT / "evidencias/runs" / run["run_id"]
    wins = {w["window_id"]: w for w in jsonl(d / "windows.jsonl")}
    mets = {(m["window_id"], m["metric_id"]): m for m in jsonl(d / "metrics.jsonl")}
    alerts = {a["alert_id"]: a for a in jsonl(d / "alerts.jsonl")} if (d / "alerts.jsonl").exists() else {}
    checks = []

    def check(what, expected, observed):
        checks.append({"run_id": run["run_id"], "what": what, "expected": expected,
                       "observed": observed, "ok": expected == observed})

    check("ventanas (número)", len(wins), run["summary"]["n_windows"])
    check("ventanas insuficientes", sum(w["state"] == "insufficient" for w in wins.values()),
          run["summary"]["n_insufficient"])
    check("métricas sin datos", sum(m["status"] != "ok" for m in mets.values()), run["summary"]["n_no_data"])
    check("alertas", len(alerts), run["summary"]["n_alerts"])
    for mid in BASE_METRICS:
        for p in run["series"][mid]:
            src = mets[(p["window_id"], mid)]
            check(f"{mid} · ventana {p['x']}", [src["value"], src["status"]], [p["y"], p["status"]])
    for w in run["windows"]:
        check(f"estado · ventana {w['idx']}", wins[w["window_id"]]["state"], w["state"])
    for a in run["alerts"]:
        idx = sorted(wins[w]["idx"] for w in alerts[a["alert_id"]]["window_ids"])
        check(f"franja {a['alert_id']}", [idx[0], idx[-1], alerts[a["alert_id"]]["status"]],
              [a["first_idx"], a["last_idx"], a["status"]])
    return checks


def states(client: TestClient, run_ids: list[str]) -> list[dict]:
    cases = [
        ("sin selección", "/tablero?enviado=1", 200, "Selecciona al menos una ejecución"),
        ("ejecución inexistente", "/tablero?run_id=no-existe", 404, "Ejecuciones inexistentes: no-existe"),
        ("mezcla válida + inexistente", f"/tablero?run_id={run_ids[0]}&run_id=no-existe", 200,
         "Ejecuciones inexistentes: no-existe"),
        ("tres válidas + una inexistente (el tope de 3 se prueba en tests)", "/tablero?" + "&".join(f"run_id={r}" for r in run_ids) + "&run_id=extra-4", 200,
         "Ejecuciones inexistentes: extra-4"),
        ("API inexistente", "/api/tablero?run_id=no-existe", 404, "no-existe"),
    ]
    out = []
    for name, url, status, text in cases:
        r = client.get(url)
        out.append({"case": name, "url": url, "expected_status": status, "status": r.status_code,
                    "expected_text": text, "ok": r.status_code == status and text in r.text})
    return out


def browse(run_ids: list[str]) -> list[dict]:
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", PORT)) == 0:
            sys.exit(f"el puerto {PORT} está ocupado")
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "monitor.portal.app:app", "--port", str(PORT)],
                           cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{PORT}"
    steps = []
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(base + "/", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1400, "height": 900})

            def shot(name, what):
                page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
                steps.append({"png": f"{name}.png", "url": page.url.replace(base, ""), "what": what})

            page.goto(base + "/tablero?" + "&".join(f"run_id={r}" for r in run_ids))
            shot("01-tablero-comparacion", "Comparación de las ejecuciones seleccionadas (un grupo comparable)")
            # Selección interactiva: dejar solo la primera ejecución y enviar el formulario.
            for r in run_ids[1:]:
                page.uncheck(f"input[value='{r}']")
            page.click("button[type=submit]")
            page.wait_for_load_state("networkidle")
            shot("02-tablero-una-ejecucion", f"Formulario enviado con solo {run_ids[0]}")
            # Clic en una franja de alerta -> detalle de la alerta.
            page.locator(".alert-strip a").first.click()
            page.wait_for_load_state("networkidle")
            shot("03-clic-franja-alerta", "Clic en la primera franja de alerta: abre su detalle")
            page.go_back()
            # Clic en el punto de la ventana 0 de G4 -> detalle de la ventana.
            page.locator(".chart").nth(4).locator("a.pt").first.click()
            page.wait_for_load_state("networkidle")
            shot("04-clic-punto-ventana", "Clic en el punto de la ventana 0 en G4: abre la ventana con sus métricas")
            page.goto(base + "/tablero?enviado=1")
            shot("05-estado-vacio", "Formulario enviado sin ejecuciones: estado vacío")
            resp = page.goto(base + "/tablero?run_id=no-existe")
            shot("06-estado-error", f"Ejecución inexistente: mensaje de error (HTTP {resp.status})")
            browser.close()
    finally:
        srv.terminate()
    return steps


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", action="append", required=True)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    client = TestClient(app)
    data = client.get("/api/tablero", params={"run_id": args.run_id}).json()
    checks = [c for g in data["groups"] for r in g["runs"] for c in compare(r)]
    st = states(client, args.run_id)
    steps = browse(args.run_id)
    bad = [c for c in checks if not c["ok"]] + [s for s in st if not s["ok"]]
    (OUT / "verificacion.json").write_text(json.dumps(
        {"run_ids": args.run_id, "groups": [(g["config_ref"], g["model_ref"]) for g in data["groups"]],
         "n_checks": len(checks), "n_diff": len(bad), "checks": checks, "states": st, "browse": steps},
        indent=1, ensure_ascii=False))
    per_run = {}
    for c in checks:
        per_run.setdefault(c["run_id"], [0, 0])[0 if c["ok"] else 1] += 1
    md = ["# Verificación del tablero histórico (F1)", "",
          f"Generado con `python scripts/verify_dashboard.py "
          + " ".join(f"--run-id {r}" for r in args.run_id) + "`.", "",
          "## 1. Valores del tablero contra los JSONL de cada ejecución", "",
          "La API `/api/tablero` (lo mismo que dibuja `/tablero`) se compara con `windows.jsonl`, "
          "`metrics.jsonl` y `alerts.jsonl`, que se escriben aparte de SQLite.", "",
          "| Ejecución | Comprobaciones iguales | Diferencias |", "|---|---|---|"]
    md += [f"| `{r}` | {ok} | {diff} |" for r, (ok, diff) in per_run.items()]
    md += ["", f"Total: **{len(checks)} comprobaciones, {len(bad)} diferencias** "
           "(valor y estado de cada métrica base por ventana, estado de ventana, franja de cada alerta "
           "y conteos del resumen). Detalle en `verificacion.json`.", "",
           "## 2. Estados vacío y de error (base real)", "",
           "| Caso | URL | HTTP esperado | HTTP | Texto esperado | Resultado |", "|---|---|---|---|---|---|"]
    md += [f"| {s['case']} | `{s['url']}` | {s['expected_status']} | {s['status']} | {s['expected_text']} | "
           f"{'ok' if s['ok'] else 'FALLA'} |" for s in st]
    real = {r["run_id"]: r["summary"] for g in data["groups"] for r in g["runs"]}
    edge = [f"`{rid}` ({s['n_insufficient']} ventanas insuficientes, {s['n_no_data']} métricas `no_data`)"
            for rid, s in real.items() if s["n_insufficient"] or s["n_no_data"]]
    md += ["", ("Casos borde con datos reales: " + ", ".join(edge) + ". Se dibujan como puntos huecos y ✕ "
                "y están incluidos en las comprobaciones de la sección 1." if edge else
                "Ninguna ejecución seleccionada tiene ventanas insuficientes ni métricas `no_data`."),
           "", "Los casos que no ocurren en ejecuciones reales (ejecución sin ventanas, más de 3 ejecuciones "
           "comparables, configuraciones distintas separadas en grupos, base inexistente) están en "
           "`tests/test_dashboard.py` sobre una base sintética.", "",
           "## 3. Recorrido en el navegador", "", "| Captura | URL | Qué muestra |", "|---|---|---|"]
    md += [f"| `{s['png']}` | `{s['url']}` | {s['what']} |" for s in steps]
    (OUT / "verificacion.md").write_text("\n".join(md) + "\n")
    print(f"{len(checks)} comprobaciones, {len(bad)} diferencias")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
