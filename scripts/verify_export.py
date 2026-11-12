"""Verificación de la exportación de eventos (adicional F2) contra los JSONL de las ejecuciones.

Para varias combinaciones de filtros descarga /exportar/eventos.{csv,jsonl}, recalcula qué
eventos deberían salir leyendo evidencias/runs/*/events.jsonl (no SQLite) y compara ids,
conteos y campos. Prueba también los estados vacío y de error y guarda capturas y ejemplos.

Uso:  python scripts/verify_export.py --run-id <c2> --run-id <s1>
Salida: evidencias/exportacion/{verificacion.md,verificacion.json,ejemplo-*.csv|jsonl,*.png}.
"""
import argparse
import csv
import io
import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright

from monitor.portal.app import EXPORT_COLUMNS, app
from portal_shots import portal

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidencias/exportacion"


def jsonl_events() -> list[dict]:
    evs = []
    for f in sorted((ROOT / "evidencias/runs").glob("*/events.jsonl")):
        evs += [json.loads(x) for x in f.read_text().splitlines() if x.strip()]
    return evs


def expected(evs, run_id="", status="", zone="", captured=False):
    sel = [e for e in evs if (not run_id or e["run_id"] == run_id) and (not status or e["status"] == status)
           and (not zone or e["frame_zone"] == zone) and (not captured or e["image_ref"])]
    return sorted(sel, key=lambda e: (e["run_id"], e["seq"]))


def norm(v):
    return "" if v is None else str(v)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", action="append", required=True)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    client, evs, checks = TestClient(app), jsonl_events(), []
    cases = [{}] + [{"run_id": r} for r in args.run_id] + [
        {"run_id": args.run_id[0], "zone": "low", "captured": True},
        {"status": "no_detections"}, {"status": "source_gap"}, {"zone": "accepted", "captured": True}]
    if len(args.run_id) > 1:
        cases.append({"run_id": args.run_id[1], "status": "source_gap"})
    for f in cases:
        params = {k: ("true" if v is True else v) for k, v in f.items()}
        exp = expected(evs, **f)
        r_csv = client.get("/exportar/eventos.csv", params=params)
        r_jl = client.get("/exportar/eventos.jsonl", params=params)
        got_csv = list(csv.DictReader(io.StringIO(r_csv.text)))
        got_jl = [json.loads(x) for x in r_jl.text.splitlines() if x]
        ids_ok = [x["event_id"] for x in got_csv] == [e["event_id"] for e in exp] == [x["event_id"] for x in got_jl]
        fields_ok = all(norm(x[k]) == norm(e.get(k)) for x, e in zip(got_csv, exp) for k in EXPORT_COLUMNS
                        if k != "detections") and \
            all(json.loads(x["detections"]) == e["detections"] for x, e in zip(got_csv, exp)) and \
            all(x == {k: e.get(k) for k in EXPORT_COLUMNS} for x, e in zip(got_jl, exp))
        checks.append({"filters": f or "(sin filtros)", "expected": len(exp), "csv": len(got_csv), "jsonl": len(got_jl),
                       "header_count": int(r_csv.headers["x-export-count"]), "ids_ok": ids_ok, "fields_ok": fields_ok,
                       "ok": r_csv.status_code == r_jl.status_code == 200 and ids_ok and fields_ok
                       and int(r_csv.headers["x-export-count"]) == len(exp)})
    errors = [("formato no soportado", "/exportar/eventos.xml", {}, 404),
              ("estado desconocido", "/exportar/eventos.csv", {"status": "perdido"}, 422),
              ("zona desconocida", "/exportar/eventos.csv", {"zone": "media"}, 422),
              ("ejecución inexistente", "/exportar/eventos.jsonl", {"run_id": "no-existe"}, 404),
              ("filtro válido sin resultados", "/exportar/eventos.csv", {"run_id": args.run_id[0], "status": "error"}, 200)]
    err_rows = []
    for name, url, params, status in errors:
        r = client.get(url, params=params)
        detail = r.json().get("detail") if r.headers.get("content-type", "").startswith("application/json") else \
            f"{r.headers.get('x-export-count')} eventos; {r.text.count(chr(10))} línea (encabezado)"
        err_rows.append({"case": name, "url": url, "params": params, "expected": status, "status": r.status_code,
                         "detail": detail, "ok": r.status_code == status})
    sample = {"run_id": args.run_id[0], "zone": "low", "captured": "true"}
    for fmt in ("csv", "jsonl"):
        r = client.get(f"/exportar/eventos.{fmt}", params=sample)
        (OUT / f"ejemplo-{args.run_id[0]}-low-captura.{fmt}").write_text(r.text)
    shots = []
    with portal(8770) as base, sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900}, accept_downloads=True)
        page.goto(f"{base}/eventos?run_id={args.run_id[0]}&zone=low&captured=true")
        page.screenshot(path=str(OUT / "01-eventos-con-exportar.png"), full_page=False)
        with page.expect_download() as dl:
            page.click("text=CSV")
        d = dl.value
        shots.append({"png": "01-eventos-con-exportar.png",
                      "what": f"Vista /eventos filtrada; el enlace CSV descargó «{d.suggested_filename}»"})
        browser.close()
    bad = [c for c in checks + err_rows if not c["ok"]]
    (OUT / "verificacion.json").write_text(json.dumps({"checks": checks, "errors": err_rows, "shots": shots},
                                                      indent=1, ensure_ascii=False))
    md = ["# Exportación de eventos (F2) · verificación", "",
          "Generado con `python scripts/verify_export.py " + " ".join(f"--run-id {r}" for r in args.run_id) + "`.",
          "Lo esperado se calcula filtrando `evidencias/runs/*/events.jsonl`, sin consultar SQLite.", "",
          f"**{len(checks) + len(err_rows)} comprobaciones, {len(bad)} fallas.**", "",
          "## Contenido exportado vs. esperado", "",
          "| Filtros | Esperados (JSONL) | CSV | JSONL | `X-Export-Count` | Mismos ids y orden | Mismos campos | Resultado |",
          "|---|---|---|---|---|---|---|---|"]
    md += [f"| `{c['filters']}` | {c['expected']} | {c['csv']} | {c['jsonl']} | {c['header_count']} | "
           f"{'sí' if c['ids_ok'] else 'no'} | {'sí' if c['fields_ok'] else 'no'} | {'ok' if c['ok'] else '**FALLA**'} |"
           for c in checks]
    md += ["", "## Estados vacío y de error", "", "| Caso | Ruta | Parámetros | HTTP esperado | HTTP | Detalle | Resultado |",
           "|---|---|---|---|---|---|---|"]
    md += [f"| {e['case']} | `{e['url']}` | `{e['params']}` | {e['expected']} | {e['status']} | {e['detail']} | "
           f"{'ok' if e['ok'] else '**FALLA**'} |" for e in err_rows]
    md += ["", "## Ejemplos y capturas", "",
           f"- [`ejemplo-{args.run_id[0]}-low-captura.csv`](ejemplo-{args.run_id[0]}-low-captura.csv) y `.jsonl`: "
           "eventos de zona baja con captura. Cada fila conserva `config_ref`, `model_ref`, `model_sha256`, "
           "`window_id`, `image_ref` y las detecciones con puntuación, zona y caja."]
    md += [f"- `{s['png']}`: {s['what']}" for s in shots]
    (OUT / "verificacion.md").write_text("\n".join(md) + "\n")
    print(f"{len(checks) + len(err_rows)} comprobaciones, {len(bad)} fallas")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
