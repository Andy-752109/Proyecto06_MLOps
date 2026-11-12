"""Recorrido de la revisión manual de capturas (adicional F3) en el navegador.

Usa una base de revisiones de demostración (evidencias/revisiones/demo.db), separada de la
real. Las revisiones se firman como "demo-automatizada" y solo usan etiquetas verdaderas por
construcción: las capturas de C2 vienen de la entrada desenfocada (sigma=7), así que son
"imagen_degradada". No sustituyen una revisión humana.

Uso:  python scripts/demo_reviews.py --c2 <id-c2>
Salida: evidencias/revisiones/{demo.db,recorrido.md,recorrido.json,*.png}. Sale con 1 si algo falla.
"""
import argparse
import json
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

from portal_shots import portal

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidencias/revisiones"
DB = OUT / "demo.db"
REVIEWER = "demo-automatizada"
NOTE = "Demostración automatizada del flujo: C2 usa la entrada desenfocada (sigma=7) por construcción; no es una revisión humana."


def api(base, path, body=None):
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="GET" if body is None else "POST")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--c2", required=True)
    ap.add_argument("--n", type=int, default=4, help="capturas a etiquetar con 'Guardar y siguiente'")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    DB.unlink(missing_ok=True)
    mon = sqlite3.connect(ROOT / "evidencias/monitor.db")
    alert_id, ev_json = mon.execute("SELECT alert_id, event_ids_json FROM alerts WHERE run_id=? AND "
                                    "rule_id='baja-confianza-v1' ORDER BY opened_at LIMIT 1", (args.c2,)).fetchone()
    alert_events = json.loads(ev_json)
    first = mon.execute(f"SELECT event_id FROM events WHERE event_id IN ({','.join('?' * len(alert_events))}) "
                        f"AND image_ref IS NOT NULL ORDER BY seq LIMIT 1", alert_events).fetchone()[0]
    no_image = mon.execute("SELECT event_id FROM events WHERE run_id=? AND image_ref IS NULL LIMIT 1",
                           (args.c2,)).fetchone()[0]
    steps, checks, submitted = [], [], []

    def check(what, expected, observed):
        checks.append({"what": what, "expected": expected, "observed": observed, "ok": expected == observed})

    with portal(8771, {"REVIEW_DB": str(DB)}) as base, sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900})

        def shot(name, what):
            page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
            steps.append({"png": f"{name}.png", "url": page.url.replace(base, ""), "what": what})

        page.goto(f"{base}/capturas?run_id={args.c2}&review=sin_revisar")
        shot("01-galeria-sin-revisar", "Galería de capturas de C2 sin revisar")
        page.goto(f"{base}/capturas/{first}")
        page.fill("input[name=reviewer]", REVIEWER)
        page.click("button[value='']")  # guardar sin elegir etiqueta
        check("guardar sin etiqueta se rechaza y no se guarda", "No se guardó", page.locator(".flash.err").inner_text()[:12])
        shot("02-error-sin-etiqueta", "Intento sin etiqueta: se rechaza (HTTP 422) y no se guarda nada")
        current = first
        for i in range(args.n):
            page.check("input[value=imagen_degradada]")
            page.fill("input[name=reviewer]", REVIEWER)
            page.fill("textarea[name=note]", NOTE)
            page.click("button[value='1']")  # guardar y siguiente sin revisar
            page.wait_for_load_state("networkidle")
            submitted.append((current, "imagen_degradada"))
            if i == 0:
                shot("03-guardado-y-siguiente", "Tras guardar, el portal abre la siguiente captura sin revisar")
            current = page.url.split("/capturas/")[1].split("?")[0]
        page.goto(f"{base}/capturas/{first}")
        page.check("input[value=dudosa]")
        page.fill("input[name=reviewer]", REVIEWER)
        page.fill("textarea[name=note]", "Re-etiquetado para demostrar el historial; la etiqueta vigente es la última.")
        page.click("button[value='']")
        page.wait_for_load_state("networkidle")
        submitted.append((first, "dudosa"))
        shot("04-historial", "La misma captura re-etiquetada: historial con 2 revisiones; vigente la última")
        page.goto(f"{base}/alertas/{alert_id}")
        summary_text = page.locator("text=Revisión manual").inner_text()
        shot("05-alerta-con-revisiones", "La alerta resume cuántas de sus capturas están revisadas y con qué etiqueta")
        page.goto(f"{base}/capturas?run_id={args.c2}&review=imagen_degradada")
        shot("06-galeria-filtrada", "Galería filtrada por etiqueta vigente imagen_degradada")
        browser.close()
        st_no_img, body_no_img = api(base, f"/api/capturas/{no_image}/revision",
                                     {"label": "dudosa", "reviewer": REVIEWER})
        st_bad, body_bad = api(base, f"/api/capturas/{first}/revision", {"label": "excelente", "reviewer": REVIEWER})
        st_404, _ = api(base, "/api/capturas/no-existe/revision", {"label": "dudosa", "reviewer": REVIEWER})
        _, all_reviews = api(base, f"/api/revisiones?run_id={args.c2}")

    rows = all_reviews["items"]
    check("revisiones guardadas = envíos aceptados", len(submitted), len(rows))
    check("orden y etiquetas guardadas = enviadas", [list(s) for s in submitted], [[r["event_id"], r["label"]] for r in rows])
    current = {}
    for r in rows:
        current[r["event_id"]] = r["label"]
    reviewed_in_alert = {e: l for e, l in current.items() if e in alert_events}
    with_image = [e for (e,) in mon.execute(f"SELECT event_id FROM events WHERE event_id IN ({','.join('?' * len(alert_events))}) "
                                            f"AND image_ref IS NOT NULL", alert_events)]
    check("resumen de la alerta = revisiones vigentes de sus capturas",
          f"{len(reviewed_in_alert)} de {len(with_image)}", summary_text.split("revisadas")[0].split(":")[1].strip())
    check("cada revisión conserva image_ref y las alertas del evento",
          True, all(r["image_ref"] and isinstance(r["alert_ids"], list) for r in rows))
    check("evento sin captura → 409", 409, st_no_img)
    check("etiqueta desconocida → 422", 422, st_bad)
    check("evento inexistente → 404", 404, st_404)
    check("la base de monitoreo no cambia (solo lectura)", 0,
          mon.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='reviews'").fetchone()[0])
    bad = [c for c in checks if not c["ok"]]
    (OUT / "recorrido.json").write_text(json.dumps({"alert_id": alert_id, "submitted": submitted, "reviews": rows,
                                                    "checks": checks, "steps": steps}, indent=1, ensure_ascii=False))
    md = ["# Revisión manual de capturas (F3) · recorrido", "",
          f"Generado con `python scripts/demo_reviews.py --c2 {args.c2}`. Base de revisiones de demostración "
          "`evidencias/revisiones/demo.db` (la real, `evidencias/revisiones.db`, no se toca).", "",
          f"> {NOTE}", "",
          f"**{len(checks)} comprobaciones, {len(bad)} fallas.**", "",
          "| Comprobación | Esperado | Observado | Resultado |", "|---|---|---|---|"]
    md += [f"| {c['what']} | {c['expected']} | {c['observed']} | {'ok' if c['ok'] else '**FALLA**'} |" for c in checks]
    md += ["", "## Revisiones guardadas (`/api/revisiones`)", "",
           "| # | Evento | Etiqueta | Revisa | Alertas del evento |", "|---|---|---|---|---|"]
    md += [f"| {r['review_id']} | `{r['event_id'].split('-')[-1]}` | {r['label']} | {r['reviewer']} | "
           f"{', '.join(a.split('-')[-1] for a in r['alert_ids']) or '—'} |" for r in rows]
    md += ["", "## Capturas", "", "| Captura | Ruta | Qué muestra |", "|---|---|---|"]
    md += [f"| `{s['png']}` | `{s['url']}` | {s['what']} |" for s in steps]
    (OUT / "recorrido.md").write_text("\n".join(md) + "\n")
    print(f"{len(checks)} comprobaciones, {len(bad)} fallas")
    for c in bad:
        print("FALLA:", c)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
