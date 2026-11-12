"""Resumen y verificación de las revisiones humanas de capturas (adicional F3).

Lee la base real de revisiones (evidencias/revisiones.db, o REVIEW_DB) y contrasta cada
revisión con los registros de su ejecución (evidencias/runs/*/events.jsonl y alerts.jsonl,
sin pasar por el portal): el evento existe, la imagen es la del evento y el archivo existe,
las alertas guardadas son las que citan ese evento, la etiqueta es válida, la etiqueta vigente
es la más reciente. Después comprueba que el portal muestra lo mismo (/api/revisiones,
resumen de cada alerta, historial) y guarda capturas.

Uso:  python scripts/summarize_reviews.py
Salida: evidencias/revisiones/humanas.{md,json} y humanas-*.png. Sale con 1 si algo falla.
"""
import json
import os
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from fastapi.testclient import TestClient

from monitor.portal.app import app
from monitor.portal.reviews import LABELS
from portal_shots import shoot

ROOT = Path(__file__).resolve().parents[1]
DB = Path(os.environ.get("REVIEW_DB", ROOT / "evidencias/revisiones.db"))
OUT = ROOT / "evidencias/revisiones"


def jl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def main() -> None:
    if not DB.exists():
        sys.exit(f"no existe {DB}: todavía no hay revisiones")
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    reviews = [dict(r) for r in con.execute("SELECT * FROM reviews ORDER BY review_id")]
    for r in reviews:
        r["alert_ids"] = json.loads(r.pop("alert_ids_json"))
    runs = sorted({r["run_id"] for r in reviews})
    events = {e["event_id"]: e for rid in runs for e in jl(ROOT / "evidencias/runs" / rid / "events.jsonl")}
    alerts = [a for rid in runs for a in jl(ROOT / "evidencias/runs" / rid / "alerts.jsonl")]
    checks = []

    def check(what, expected, observed, ok):
        checks.append({"what": what, "expected": expected, "observed": observed, "ok": bool(ok)})

    # contra los registros primarios de las ejecuciones
    check("cada revisión apunta a un evento existente de su ejecución", len(reviews),
          sum(r["event_id"] in events and events[r["event_id"]]["run_id"] == r["run_id"] for r in reviews),
          all(r["event_id"] in events and events[r["event_id"]]["run_id"] == r["run_id"] for r in reviews))
    check("la imagen guardada es la del evento y el archivo existe", len(reviews),
          sum(r["image_ref"] == events[r["event_id"]]["image_ref"] and (ROOT / r["image_ref"]).is_file() for r in reviews),
          all(r["image_ref"] == events[r["event_id"]]["image_ref"] and (ROOT / r["image_ref"]).is_file() for r in reviews))
    cited = lambda eid: sorted(a["alert_id"] for a in alerts if eid in a["event_ids"])
    check("las alertas guardadas con cada revisión son las que citan ese evento (alerts.jsonl)", len(reviews),
          sum(sorted(r["alert_ids"]) == cited(r["event_id"]) for r in reviews),
          all(sorted(r["alert_ids"]) == cited(r["event_id"]) for r in reviews))
    check("etiquetas dentro del catálogo y quien revisa identificado", f"{len(reviews)} con etiqueta de {list(LABELS)}",
          sum(r["label"] in LABELS and r["reviewer"].strip() != "" for r in reviews),
          all(r["label"] in LABELS and r["reviewer"].strip() for r in reviews))
    check("registros de solo inserción: id y momento crecen juntos", "orden creciente",
          "creciente" if all(a["created_at"] <= b["created_at"] for a, b in zip(reviews, reviews[1:])) else "desordenado",
          all(a["created_at"] <= b["created_at"] for a, b in zip(reviews, reviews[1:])))
    current = {}
    for r in reviews:
        current[r["event_id"]] = r
    multi = {e: [r for r in reviews if r["event_id"] == e] for e, n in Counter(r["event_id"] for r in reviews).items() if n > 1}

    # contra el portal
    client = TestClient(app)
    api = client.get("/api/revisiones").json()["items"]
    check("/api/revisiones devuelve las mismas revisiones en el mismo orden", len(reviews), len(api),
          [(x["review_id"], x["event_id"], x["label"]) for x in api] == [(r["review_id"], r["event_id"], r["label"]) for r in reviews])
    alert_rows = []
    for a in sorted({x for r in reviews for x in r["alert_ids"]}):
        al = next(x for x in alerts if x["alert_id"] == a)
        with_img = [e for e in al["event_ids"] if events[e]["image_ref"]]
        exp = sum(e in current for e in with_img)
        page = client.get(f"/alertas/{a}").text
        m = re.search(r"Revisión manual: <b>(\d+) de (\d+)</b>", page)
        alert_rows.append({"alert_id": a, "expected": f"{exp} de {len(with_img)}",
                           "portal": f"{m.group(1)} de {m.group(2)}" if m else None})
    check("el resumen de revisión de cada alerta coincide con las revisiones vigentes", [x["expected"] for x in alert_rows],
          [x["portal"] for x in alert_rows], all(x["expected"] == x["portal"] for x in alert_rows))
    for e, rs in multi.items():
        page = client.get(f"/capturas/{e}").text
        n = re.search(r'Historial de revisiones <span class="count">(\d+)', page)
        check(f"historial de {e.split('-')[-1]}: {len(rs)} revisiones y la vigente es la última",
              f"{len(rs)}, vigente {rs[-1]['label']}", f"{n.group(1) if n else '—'}",
              n and int(n.group(1)) == len(rs) and "(vigente)" in page)

    bad = [c for c in checks if not c["ok"]]
    first_multi = next(iter(multi), reviews[0]["event_id"])
    first_alert = alert_rows[0]["alert_id"] if alert_rows else None
    pages = [("humanas-01-galeria-revisadas", "/capturas?review=" + current[reviews[-1]["event_id"]]["label"],
              "Galería filtrada por la etiqueta vigente de la última revisión"),
             ("humanas-02-historial", f"/capturas/{first_multi}", "Captura con más de una revisión: historial y vigente")]
    if first_alert:
        pages.append(("humanas-03-alerta", f"/alertas/{first_alert}", "Resumen de revisión dentro de la alerta"))
    shots = shoot(pages, OUT, port=8774)

    by_run_label = Counter((r["run_id"], current[r["event_id"]]["label"]) for r in current.values())
    (OUT / "humanas.json").write_text(json.dumps({"db": str(DB.relative_to(ROOT)) if DB.is_relative_to(ROOT) else DB.name,
                                                  "reviews": reviews, "checks": checks, "alerts": alert_rows,
                                                  "shots": shots}, indent=1, ensure_ascii=False))
    md = ["# Revisiones humanas de capturas (F3)", "",
          "Generado con `python scripts/summarize_reviews.py` sobre la base real `evidencias/revisiones.db`. "
          "Estas revisiones las hizo la autora en el portal (`/capturas`); son distintas de la demostración "
          "automatizada de [`recorrido.md`](recorrido.md), que usa otra base (`demo.db`).", "",
          "Las etiquetas describen lo que ve una persona en la imagen. No se usan como métrica de calidad ni "
          "cambian eventos, métricas o alertas.", "",
          f"**{len(reviews)} revisiones de {len(current)} capturas, {len(multi)} con historial. "
          f"{len(checks)} comprobaciones, {len(bad)} fallas.**", "",
          "## Etiqueta vigente por ejecución", "", "| Ejecución | Etiqueta | Capturas |", "|---|---|---|"]
    md += [f"| `{rid}` | {lab} | {n} |" for (rid, lab), n in sorted(by_run_label.items())]
    md += ["", "## Comprobaciones", "", "| Comprobación | Esperado | Observado | Resultado |", "|---|---|---|---|"]
    md += [f"| {c['what']} | {c['expected']} | {c['observed']} | {'ok' if c['ok'] else '**FALLA**'} |" for c in checks]
    md += ["", "## Revisiones (`revisiones.db`)", "",
           "| # | Momento (UTC) | Ejecución | Evento | Motivo de captura | Etiqueta | Revisa | Nota | Alertas del evento |",
           "|---|---|---|---|---|---|---|---|---|"]
    md += [f"| {r['review_id']} | `{r['created_at']}` | `{r['run_id'].rsplit('-', 1)[0]}` | `{r['event_id'].split('-')[-1]}` | "
           f"{events[r['event_id']]['capture_reason']} ({events[r['event_id']]['status']}) | {r['label']} | {r['reviewer']} | "
           f"{(r['note'] or '—').replace('|', '/')} | {', '.join(a.split('-')[-1] for a in r['alert_ids']) or '—'} |" for r in reviews]
    md += ["", "## Capturas", "", "| Captura | Ruta | HTTP | Qué muestra |", "|---|---|---|---|"]
    md += [f"| `{s['png']}` | `{s['url']}` | {s['status']} | {s['what']} |" for s in shots]
    (OUT / "humanas.md").write_text("\n".join(md) + "\n")
    print(f"{len(reviews)} revisiones, {len(checks)} comprobaciones, {len(bad)} fallas")
    for c in bad:
        print("FALLA:", c)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
