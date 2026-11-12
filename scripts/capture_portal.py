"""Recorrido reproducible del portal: levanta el servidor, visita las vistas de eventos y
alertas de C1/C2 y guarda capturas de pantalla + un índice del recorrido.

Uso:  python scripts/capture_portal.py --c1 <run_id> --c2 <run_id>
Salida: evidencias/portal/*.png y evidencias/portal/recorrido.md
"""
import argparse
import json
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidencias/portal"
PORT = 8765


def q(con, sql, *a):
    return con.execute(sql, a).fetchone()[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--c1", required=True)
    ap.add_argument("--c2", required=True)
    args = ap.parse_args()
    con = sqlite3.connect(ROOT / "evidencias/monitor.db")
    c1_event = q(con, "SELECT event_id FROM events WHERE run_id=? AND capture_reason='muestra_normal' "
                      "ORDER BY seq LIMIT 1 OFFSET 2", args.c1)
    c2_low = q(con, "SELECT alert_id FROM alerts WHERE run_id=? AND rule_id='baja-confianza-v1' "
                    "ORDER BY opened_at LIMIT 1", args.c2)
    c2_alert_row = con.execute("SELECT event_ids_json, first_window_id FROM alerts WHERE alert_id=?",
                               (c2_low,)).fetchone()
    c2_ids = json.loads(c2_alert_row[0])
    marks = ",".join("?" * len(c2_ids))
    c2_event = con.execute(f"SELECT event_id FROM events WHERE event_id IN ({marks}) AND image_ref IS NOT NULL "
                           f"AND frame_zone='low' ORDER BY seq LIMIT 1", c2_ids).fetchone()
    c2_event = c2_event[0] if c2_event else q(con, f"SELECT event_id FROM events WHERE event_id IN ({marks}) "
                                                   f"AND image_ref IS NOT NULL ORDER BY seq LIMIT 1", *c2_ids)
    pages = [
        ("01-inicio", "/", "Ejecuciones (reference, C1, C2) y últimas alertas"),
        ("02-c1-eventos", f"/eventos?run_id={args.c1}", "C1 · consulta de eventos"),
        ("03-c1-evento", f"/eventos/{c1_event}", "C1 · evento con captura de muestra normal, detecciones y zonas"),
        ("04-c1-ejecucion", f"/ejecuciones/{args.c1}", "C1 · ventanas, métricas base por ventana y alertas (ninguna)"),
        ("05-c1-alertas", f"/alertas?run_id={args.c1}", "C1 · consulta de alertas (vacía conforme a la regla)"),
        ("06-c2-eventos-baja", f"/eventos?run_id={args.c2}&zone=low&captured=true", "C2 · eventos de zona baja con captura"),
        ("07-c2-evento", f"/eventos/{c2_event}", "C2 · evento de baja confianza con captura y alerta vinculada"),
        ("08-c2-alertas", f"/alertas?run_id={args.c2}", "C2 · alertas: momento, motivo, severidad, acción sugerida"),
        ("09-c2-alerta", f"/alertas/{c2_low}", "C2 · alerta de baja confianza: regla, ventanas, capturas y eventos"),
        ("10-c2-ventana", f"/ventanas/{c2_alert_row[1]}", "C2 · ventana que dispara la alerta: métricas y evaluación de reglas"),
        ("11-c2-ejecucion", f"/ejecuciones/{args.c2}", "C2 · ventanas, métricas base y alertas"),
    ]
    OUT.mkdir(parents=True, exist_ok=True)
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", PORT)) == 0:
            sys.exit(f"el puerto {PORT} está ocupado")
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "monitor.portal.app:app", "--port", str(PORT)],
                           cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        lines = []
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            for name, url, what in pages:
                resp = page.goto(f"http://127.0.0.1:{PORT}{url}")
                page.wait_for_load_state("networkidle")
                page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
                lines.append(f"| `{name}.png` | `{url}` | {resp.status} | {what} |")
                print(resp.status, url)
            browser.close()
    finally:
        srv.terminate()
    (OUT / "recorrido.md").write_text(
        "# Recorrido del portal\n\n"
        f"Generado con `python scripts/capture_portal.py --c1 {args.c1} --c2 {args.c2}`.\n"
        "El script levanta `uvicorn monitor.portal.app:app`, visita cada URL con Chromium headless "
        "y guarda la página completa. Para repetirlo manualmente: `uvicorn monitor.portal.app:app "
        "--port 8000` y abrir las mismas rutas.\n\n"
        "| Captura | Ruta | HTTP | Qué acredita |\n|---|---|---|---|\n" + "\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
