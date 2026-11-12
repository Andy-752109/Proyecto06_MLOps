"""Portal de consulta: eventos y alertas, con vínculos hasta capturas, ventanas y configuración.

Uso:  uvicorn monitor.portal.app:app --port 8000
"""
import json
import os
import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from ..config import ROOT, load_config, load_reference
from ..store import row_to_dict
from . import dashboard

CFG = load_config()
DB_PATH = Path(os.environ.get("MONITOR_DB", ROOT / CFG["storage"]["db"]))
EVID_DIR = (ROOT / "evidencias").resolve()
PAGE = 50

app = FastAPI(title="Centro de monitoreo CV")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.filters["fmt"] = lambda v, n=3: "—" if v is None else (f"{v:.{n}f}" if isinstance(v, float) else v)
templates.env.filters["tojson_pretty"] = lambda v: json.dumps(v, indent=2, ensure_ascii=False)


def db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise HTTPException(503, f"no existe la base {DB_PATH}; ejecuta un escenario primero")
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def rows(sql: str, args=()) -> list[dict]:
    with db() as con:
        return [row_to_dict(r) for r in con.execute(sql, args)]


def one(sql: str, args=()) -> dict:
    r = rows(sql, args)
    if not r:
        raise HTTPException(404, "registro no encontrado")
    return r[0]


def run_ids() -> list[str]:
    return [r["run_id"] for r in rows("SELECT run_id FROM runs ORDER BY started_at DESC")]


def query_events(run_id, status, zone, captured, page):
    where, args = [], []
    if run_id:
        where.append("run_id = ?"); args.append(run_id)
    if status:
        where.append("status = ?"); args.append(status)
    if zone:
        where.append("frame_zone = ?"); args.append(zone)
    if captured:
        where.append("image_ref IS NOT NULL")
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    total = rows(f"SELECT COUNT(*) AS n FROM events {clause}", args)[0]["n"]
    items = rows(f"SELECT * FROM events {clause} ORDER BY run_id, seq LIMIT ? OFFSET ?",
                 args + [PAGE, (page - 1) * PAGE])
    return total, items


def query_alerts(run_id, status, rule_id):
    where, args = [], []
    if run_id:
        where.append("run_id = ?"); args.append(run_id)
    if status:
        where.append("status = ?"); args.append(status)
    if rule_id:
        where.append("rule_id = ?"); args.append(rule_id)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    return rows(f"SELECT * FROM alerts {clause} ORDER BY opened_at DESC", args)


def alerts_for_event(event_id: str) -> list[dict]:
    return [a for a in rows("SELECT * FROM alerts WHERE event_ids_json LIKE ?", (f'%"{event_id}"%',))
            if event_id in a["event_ids"]]


# ------------------------------------------------------------------ HTML
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    runs = rows("SELECT * FROM runs ORDER BY started_at DESC")
    for r in runs:
        r["n_alerts"] = rows("SELECT COUNT(*) AS n FROM alerts WHERE run_id=?", (r["run_id"],))[0]["n"]
    latest = rows("SELECT * FROM alerts ORDER BY opened_at DESC LIMIT 5")
    return templates.TemplateResponse(request, "home.html", {"runs": runs, "latest": latest})


@app.get("/eventos", response_class=HTMLResponse)
def events_page(request: Request, run_id: str = "", status: str = "", zone: str = "",
                captured: bool = False, page: int = Query(1, ge=1)):
    total, items = query_events(run_id, status, zone, captured, page)
    return templates.TemplateResponse(request, "events.html", {
        "items": items, "total": total, "page": page, "pages": max(1, -(-total // PAGE)),
        "f": {"run_id": run_id, "status": status, "zone": zone, "captured": captured},
        "run_ids": run_ids()})


@app.get("/eventos/{event_id}", response_class=HTMLResponse)
def event_page(request: Request, event_id: str):
    ev = one("SELECT * FROM events WHERE event_id=?", (event_id,))
    run = one("SELECT * FROM runs WHERE run_id=?", (ev["run_id"],))
    nav = {k: rows(f"SELECT event_id FROM events WHERE run_id=? AND seq{op}? ORDER BY seq {o} LIMIT 1",
                   (ev["run_id"], ev["seq"])) for k, op, o in (("prev", "<", "DESC"), ("next", ">", "ASC"))}
    return templates.TemplateResponse(request, "event.html", {
        "ev": ev, "run": run, "alerts": alerts_for_event(event_id),
        "prev": nav["prev"][0]["event_id"] if nav["prev"] else None,
        "next": nav["next"][0]["event_id"] if nav["next"] else None,
        "policy": CFG["policy"]})


@app.get("/alertas", response_class=HTMLResponse)
def alerts_page(request: Request, run_id: str = "", status: str = "", rule_id: str = ""):
    return templates.TemplateResponse(request, "alerts.html", {
        "items": query_alerts(run_id, status, rule_id), "run_ids": run_ids(),
        "rule_ids": [r["rule_id"] for r in CFG["alerts"]],
        "f": {"run_id": run_id, "status": status, "rule_id": rule_id}})


@app.get("/alertas/{alert_id}", response_class=HTMLResponse)
def alert_page(request: Request, alert_id: str):
    a = one("SELECT * FROM alerts WHERE alert_id=?", (alert_id,))
    marks = ",".join("?" * len(a["event_ids"]))
    evs = rows(f"SELECT * FROM events WHERE event_id IN ({marks}) ORDER BY seq", a["event_ids"])
    rule = next((r for r in CFG["alerts"] if r["rule_id"] == a["rule_id"]), None)
    return templates.TemplateResponse(request, "alert.html", {
        "a": a, "events": evs, "rule": rule, "captured": [e for e in evs if e["image_ref"]]})


@app.get("/ventanas/{window_id}", response_class=HTMLResponse)
def window_page(request: Request, window_id: str):
    w = one("SELECT * FROM windows WHERE window_id=?", (window_id,))
    return templates.TemplateResponse(request, "window.html", {
        "w": w,
        "metrics": rows("SELECT * FROM metric_values WHERE window_id=? ORDER BY grp", (window_id,)),
        "evals": rows("SELECT * FROM rule_evaluations WHERE window_id=?", (window_id,)),
        "events": rows("SELECT * FROM events WHERE window_id=? ORDER BY seq", (window_id,))})


@app.get("/ejecuciones/{run_id}", response_class=HTMLResponse)
def run_page(request: Request, run_id: str):
    run = one("SELECT * FROM runs WHERE run_id=?", (run_id,))
    wins = rows("SELECT * FROM windows WHERE run_id=? ORDER BY idx", (run_id,))
    mets = rows("SELECT * FROM metric_values WHERE run_id=?", (run_id,))
    by_win = {}
    for m in mets:
        by_win.setdefault(m["window_id"], {})[m["metric_id"]] = m
    return templates.TemplateResponse(request, "run.html", {
        "run": run, "windows": wins, "by_win": by_win,
        "metric_ids": sorted({m["metric_id"] for m in mets}),
        "alerts": rows("SELECT * FROM alerts WHERE run_id=? ORDER BY opened_at", (run_id,))})


@app.get("/config/{config_ref}", response_class=HTMLResponse)
def config_page(request: Request, config_ref: str):
    c = one("SELECT * FROM configs WHERE config_ref=?", (config_ref,))
    return templates.TemplateResponse(request, "config.html", {"c": c})


def dashboard_data(run_id: list[str]) -> tuple[int, dict]:
    with db() as con:
        data = dashboard.build(con, run_id, CFG, load_reference(CFG))
    status = 404 if run_id and data["available"] and not data["groups"] else 200
    return status, data


@app.get("/tablero", response_class=HTMLResponse)
def dashboard_page(request: Request, run_id: list[str] = Query(default=[])):
    if not request.query_params:  # primera visita: las ejecuciones más recientes
        run_id = [r["run_id"] for r in rows("SELECT run_id FROM runs ORDER BY started_at DESC")
                  ][:dashboard.MAX_RUNS]
    status, data = dashboard_data(run_id)
    groups = [dict(g, plots=dashboard.layout(g), alert_rows=dashboard.alert_bars(g))
              for g in data["groups"]]
    return templates.TemplateResponse(request, "dashboard.html", {
        "d": data, "groups": groups, "selected": set(run_id), "max_runs": dashboard.MAX_RUNS},
        status_code=status)


@app.get("/evidencia/{path:path}")
def evidence_file(path: str):
    target = (ROOT / path).resolve()
    if not target.is_relative_to(EVID_DIR) or not target.is_file():
        raise HTTPException(404, "archivo no encontrado")
    return FileResponse(target)


# ------------------------------------------------------------------ JSON
@app.get("/api/eventos")
def api_events(run_id: str = "", status: str = "", zone: str = "", captured: bool = False,
               page: int = Query(1, ge=1)):
    total, items = query_events(run_id, status, zone, captured, page)
    return {"total": total, "page": page, "page_size": PAGE, "items": items}


@app.get("/api/eventos/{event_id}")
def api_event(event_id: str):
    ev = one("SELECT * FROM events WHERE event_id=?", (event_id,))
    ev["alert_ids"] = [a["alert_id"] for a in alerts_for_event(event_id)]
    return ev


@app.get("/api/alertas")
def api_alerts(run_id: str = "", status: str = "", rule_id: str = ""):
    return {"items": query_alerts(run_id, status, rule_id)}


@app.get("/api/tablero")
def api_dashboard(run_id: list[str] = Query(default=[])):
    status, data = dashboard_data(run_id)
    if status != 200:
        raise HTTPException(status, "; ".join(data["errors"]) or data.get("empty"))
    return data


@app.get("/api/alertas/{alert_id}")
def api_alert(alert_id: str):
    return one("SELECT * FROM alerts WHERE alert_id=?", (alert_id,))
