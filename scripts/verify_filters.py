"""Verificación de los filtros avanzados de eventos (adicional F5) contra los JSONL de las ejecuciones.

Para varias consultas (rangos de puntuación y detecciones, intervalo de captura, ventana, motivo,
vínculo con alertas, texto en el id, orden y combinaciones) recalcula qué eventos deben salir y en
qué orden leyendo evidencias/runs/*/{events,alerts}.jsonl (no SQLite), y lo compara con
/api/eventos (todas las páginas), /exportar/eventos.csv y el conteo de la página /eventos. Prueba
también los estados vacío y de error, que las etiquetas de filtro quiten solo su filtro, y guarda
capturas del portal.

Uso:  python scripts/verify_filters.py --c2 <id-c2> --s3 <id-s3>
Salida: evidencias/filtros/{verificacion.md,verificacion.json,*.png}. Sale con 1 si algo falla.
"""
import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from monitor.portal.app import app
from portal_shots import shoot

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidencias/filtros"


def jl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def load():
    evs, alert_events = [], set()
    for d in sorted((ROOT / "evidencias/runs").iterdir()):
        evs += jl(d / "events.jsonl")
        if (d / "alerts.jsonl").exists():
            for a in jl(d / "alerts.jsonl"):
                alert_events |= set(a["event_ids"])
    return evs, alert_events


def expected(evs, alert_events, f: dict) -> list[str]:
    """Filtro y orden reimplementados en Python, con la semántica documentada en /eventos."""
    def keep(e):
        return all([
            not f.get("run_id") or e["run_id"] == f["run_id"],
            not f.get("status") or e["status"] == f["status"],
            not f.get("zone") or e["frame_zone"] == f["zone"],
            not f.get("reason") or e["capture_reason"] == f["reason"],
            not f.get("captured") or e["image_ref"],
            "score_min" not in f or (e["max_score"] is not None and e["max_score"] >= f["score_min"]),
            "score_max" not in f or (e["max_score"] is not None and e["max_score"] <= f["score_max"]),
            "dets_min" not in f or e["n_detections"] >= f["dets_min"],
            "dets_max" not in f or e["n_detections"] <= f["dets_max"],
            "since" not in f or e["captured_at"] >= f["since"],
            "until" not in f or e["captured_at"] <= f["until"],
            "window" not in f or e["window_id"].endswith(f"-w{f['window']:03d}"),
            not f.get("in_alert") or e["event_id"] in alert_events,
            not f.get("q") or f["q"] in e["event_id"],
        ])
    sel = [e for e in evs if keep(e)]
    base = sorted(sel, key=lambda e: (e["run_id"], e["seq"]))
    sort = f.get("sort", "")
    nulls_last = lambda k, rev: sorted(base, key=lambda e: (e[k] is None, -(e[k] or 0) if rev else (e[k] or 0)))
    if sort == "score_desc":
        out = nulls_last("max_score", True)
    elif sort == "score_asc":
        out = nulls_last("max_score", False)
    elif sort == "inference_desc":
        out = nulls_last("inference_ms", True)
    elif sort == "e2e_desc":
        out = nulls_last("e2e_ms", True)
    elif sort == "dets_desc":
        out = sorted(base, key=lambda e: -e["n_detections"])
    elif sort == "recent":
        out = sorted(sorted(sel, key=lambda e: (e["run_id"], -e["seq"])), key=lambda e: e["captured_at"], reverse=True)
    else:
        out = base
    return [e["event_id"] for e in out]


def params(f: dict) -> dict:
    return {k: ("true" if v is True else v) for k, v in f.items()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--c2", required=True)
    ap.add_argument("--s3", required=True)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    client = TestClient(app)
    evs, alert_events = load()
    c2_evs = [e for e in evs if e["run_id"] == args.c2]
    mid = c2_evs[len(c2_evs) // 2]["captured_at"]
    since, until = c2_evs[40]["captured_at"], c2_evs[79]["captured_at"]  # ventanas 2 y 3 de C2
    cases = [
        ("rango de puntuación en zona de duda", {"run_id": args.c2, "score_min": 0.4, "score_max": 0.7}),
        ("puntuación ≥ 0.8 en todas las ejecuciones, orden ↓", {"score_min": 0.8, "sort": "score_desc"}),
        ("puntuación baja ↑ (los eventos sin puntuación no entran)", {"score_max": 0.3, "sort": "score_asc"}),
        ("frames concurridos: ≥ 8 detecciones, orden por detecciones", {"dets_min": 8, "sort": "dets_desc"}),
        ("pocas detecciones en C2 (0 a 1)", {"run_id": args.c2, "dets_min": 0, "dets_max": 1}),
        ("intervalo de captura (ventanas 2–3 de C2)", {"since": since, "until": until}),
        ("hasta la mitad de C2, más recientes primero", {"run_id": args.c2, "until": mid, "sort": "recent"}),
        ("ventana 3 de S3 (solo errores)", {"run_id": args.s3, "window": 3}),
        ("motivo de captura 'error'", {"reason": "error"}),
        ("eventos que sustentan alguna alerta en C2", {"run_id": args.c2, "in_alert": True}),
        ("id contiene e0004", {"run_id": args.c2, "q": "e0004"}),
        ("inferencia más lenta primero (nulos al final)", {"run_id": args.s3, "sort": "inference_desc"}),
        ("extremo a extremo más lento primero", {"run_id": args.c2, "sort": "e2e_desc"}),
        ("combinada: C2, baja, con captura, en alerta, 2–6 detecciones, ↓",
         {"run_id": args.c2, "zone": "low", "captured": True, "in_alert": True, "dets_min": 2, "dets_max": 6,
          "sort": "score_desc"}),
    ]
    checks = []
    for name, f in cases:
        exp = expected(evs, alert_events, f)
        api_ids, page = [], 1
        while True:
            r = client.get("/api/eventos", params={**params(f), "page": page})
            body = r.json()
            api_ids += [e["event_id"] for e in body["items"]]
            if page * body["page_size"] >= body["total"]:
                break
            page += 1
        r_csv = client.get("/exportar/eventos.csv", params=params(f))
        csv_ids = [x["event_id"] for x in csv.DictReader(io.StringIO(r_csv.text))]
        html = client.get("/eventos", params=params(f))
        m = re.search(r"<b>([\d,]+)</b>&nbsp;eventos", html.text)
        html_n = int(m.group(1).replace(",", "")) if m else None
        ok = api_ids == exp == csv_ids and html_n == len(exp) and html.status_code == 200
        checks.append({"case": name, "filters": f, "expected": len(exp), "api": len(api_ids), "csv": len(csv_ids),
                       "html": html_n, "same_order": api_ids == exp == csv_ids, "first": exp[:3], "ok": ok})
    # coherencia: cada filtro añadido nunca agrega eventos
    base = {"run_id": args.c2}
    chain, counts = [], []
    for step in ({}, {"zone": "low"}, {"captured": True}, {"in_alert": True}, {"score_max": 0.35}):
        base = {**base, **step}
        counts.append(len(expected(evs, alert_events, base)))
        chain.append(client.get("/api/eventos", params=params(base)).json()["total"])
    checks.append({"case": "agregar filtros solo reduce el resultado (C2 → baja → captura → alerta → s ≤ 0.35)",
                   "filters": base, "expected": counts, "api": chain, "csv": "—", "html": "—", "same_order": chain == counts,
                   "first": [], "ok": chain == counts and all(a >= b for a, b in zip(chain, chain[1:]))})
    # quitar una etiqueta de filtro conserva los demás
    f = {"run_id": args.c2, "zone": "low", "captured": True}
    html = client.get("/eventos", params=params(f)).text
    links = re.findall(r'<a href="/eventos\?([^"]*)" title="quitar este filtro"', html)
    removed = [sorted(set(params(f)) - set(dict(x.split("=", 1) for x in l.replace("&amp;", "&").split("&") if x))) for l in links]
    checks.append({"case": "cada etiqueta × quita solo su filtro", "filters": f, "expected": [["run_id"], ["zone"], ["captured"]],
                   "api": removed, "csv": "—", "html": len(links), "same_order": removed == [["run_id"], ["zone"], ["captured"]],
                   "first": [], "ok": removed == [["run_id"], ["zone"], ["captured"]]})

    errors = [
        ("rango de puntuación invertido (página)", "/eventos", {"score_min": 0.9, "score_max": 0.1}, 422, "es mayor que"),
        ("puntuación fuera de [0, 1] (API)", "/api/eventos", {"score_min": 1.5}, 422, "fuera del rango"),
        ("puntuación no numérica (exportación)", "/exportar/eventos.csv", {"score_max": "alta"}, 422, "no es un número"),
        ("fecha inválida (página)", "/eventos", {"since": "ayer"}, 422, "fecha inválida"),
        ("intervalo invertido (API)", "/api/eventos", {"since": until, "until": since}, 422, "es mayor que"),
        ("orden desconocido (API)", "/api/eventos", {"sort": "azar"}, 422, "orden desconocido"),
        ("detecciones negativas (página)", "/eventos", {"dets_min": -1}, 422, "fuera del rango"),
        ("consulta válida sin resultados (página)", "/eventos", {"run_id": args.c2, "status": "error"}, 200,
         "Ningún evento coincide"),
        ("consulta válida sin resultados (API)", "/api/eventos", {"score_min": 0.99}, 200, '"total":0'),
    ]
    err_rows = []
    for name, url, p, status, text in errors:
        r = client.get(url, params=p)
        err_rows.append({"case": name, "url": url, "params": p, "expected": status, "status": r.status_code,
                         "text": text, "found": text in r.text, "ok": r.status_code == status and text in r.text})

    shots = shoot([
        ("01-inicio", "/", "Inicio rediseñado: indicadores, una tarjeta por ejecución con low_prop por ventana y últimas alertas"),
        ("02-filtros-avanzados", "/eventos?" + "&".join(f"{k}={v}" for k, v in params(cases[-1][1]).items()),
         "Consulta combinada con el panel avanzado abierto, etiquetas de filtros activos y orden por puntuación"),
        ("03-error-rango", "/eventos?score_min=0.9&score_max=0.1", "Rango invertido: HTTP 422 con explicación, sin resultados"),
        ("04-vacio", f"/eventos?run_id={args.c2}&status=error", "Consulta válida sin resultados: estado vacío"),
        ("05-ventana-s3", f"/eventos?run_id={args.s3}&window=3", "Ventana 3 de S3: todos los eventos con error de inferencia"),
        ("06-alertas", "/alertas?severity=high", "Alertas filtradas por severidad alta"),
    ], OUT, port=8773)

    bad = [c for c in checks + err_rows if not c["ok"]]
    (OUT / "verificacion.json").write_text(json.dumps({"checks": checks, "errors": err_rows, "shots": shots},
                                                      indent=1, ensure_ascii=False))
    md = ["# Filtros avanzados de eventos (F5) · verificación", "",
          f"Generado con `python scripts/verify_filters.py --c2 {args.c2} --s3 {args.s3}`.",
          "Lo esperado se calcula filtrando y ordenando `evidencias/runs/*/events.jsonl` y `alerts.jsonl` en Python, "
          "sin consultar SQLite; se compara con `/api/eventos` (todas las páginas), `/exportar/eventos.csv` y el conteo "
          "que muestra `/eventos`.", "",
          f"**{len(checks) + len(err_rows)} comprobaciones, {len(bad)} fallas.**", "",
          "## Resultados y orden", "",
          "| Consulta | Filtros | Esperados (JSONL) | API | CSV | Página | Mismos ids y orden | Primeros | Resultado |",
          "|---|---|---|---|---|---|---|---|---|"]
    md += [f"| {c['case']} | `{json.dumps(c['filters'], ensure_ascii=False)}` | {c['expected']} | {c['api']} | {c['csv']} | "
           f"{c['html']} | {'sí' if c['same_order'] else 'no'} | {', '.join(x.split('-')[-1] for x in c['first']) or '—'} | "
           f"{'ok' if c['ok'] else '**FALLA**'} |" for c in checks]
    md += ["", "## Estados vacío y de error", "", "| Caso | Ruta | Parámetros | HTTP esperado | HTTP | Texto esperado | Resultado |",
           "|---|---|---|---|---|---|---|"]
    md += [f"| {e['case']} | `{e['url']}` | `{json.dumps(e['params'], ensure_ascii=False)}` | {e['expected']} | {e['status']} | "
           f"`{e['text']}` | {'ok' if e['ok'] else '**FALLA**'} |" for e in err_rows]
    md += ["", "## Capturas", "", "| Captura | Ruta | HTTP | Qué muestra |", "|---|---|---|---|"]
    md += [f"| `{s['png']}` | `{s['url']}` | {s['status']} | {s['what']} |" for s in shots]
    (OUT / "verificacion.md").write_text("\n".join(md) + "\n")
    print(f"{len(checks) + len(err_rows)} comprobaciones, {len(bad)} fallas")
    for c in bad:
        print("FALLA:", c)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
