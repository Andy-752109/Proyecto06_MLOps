"""Portal de consulta: eventos y alertas, con vínculos hasta capturas, ventanas y configuración.

Uso:  uvicorn monitor.portal.app:app --port 8000
"""
import csv
import io
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlencode

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from ..config import ROOT, load_config, load_reference
from ..store import row_to_dict
from . import dashboard
from .reviews import LABELS, ReviewError, ReviewStore

CFG = load_config()
DB_PATH = Path(os.environ.get("MONITOR_DB", ROOT / CFG["storage"]["db"]))
EVID_DIR = (ROOT / "evidencias").resolve()
LIVE_DIR = Path(os.environ.get("LIVE_DIR", ROOT / CFG["storage"].get("live_dir", "evidencias/live")))
LIVE_STALE_S = 3.0  # sin actualizaciones por más de esto y sin terminar: detenido
REVIEWS = ReviewStore(Path(os.environ.get("REVIEW_DB", ROOT / "evidencias/revisiones.db")))
PAGE = 50
GALLERY_PAGE = 24

app = FastAPI(title="Centro de monitoreo CV")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.filters["fmt"] = lambda v, n=3: "—" if v is None else (f"{v:.{n}f}" if isinstance(v, float) else v)
templates.env.filters["qs"] = lambda f, **extra: urlencode(
    {k: ("true" if v is True else v) for k, v in {**f, **extra}.items() if v not in ("", None, False)})
templates.env.filters["tojson_pretty"] = lambda v: json.dumps(v, indent=2, ensure_ascii=False)

# Presentación: ids cortos, nombres legibles de ejecución y etiquetas en español (el valor
# crudo se conserva en los filtros, la API y el atributo title).
LABELS_ES = {
    "ok": "ok", "no_detections": "sin detecciones", "error": "error", "source_gap": "hueco de fuente",
    "low": "baja", "doubt": "duda", "accepted": "aceptada",
    "open": "abierta", "resolved": "resuelta", "info": "info", "warning": "advertencia", "high": "alta",
    "eligible": "elegible", "insufficient": "insuficiente",
}


def run_label(run_id: str | None) -> str:
    """'c2-baja-confianza-20261112T162525Z' -> 'c2-baja-confianza · 16:25:25'."""
    if not run_id:
        return "—"
    name, _, stamp = run_id.rpartition("-")
    if len(stamp) == 16 and stamp[8] == "T":
        return f"{name} · {stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]}"
    return run_id


def when(ts: str | None, date: bool = True) -> str:
    """'2026-11-12T16:25:29.788Z' -> '2026-11-12 16:25:29' (UTC)."""
    if not ts:
        return "—"
    d, _, t = ts.replace("Z", "").partition("T")
    return f"{d} {t[:8]}" if date else t[:8]


templates.env.filters["short"] = lambda v: (v or "—").rsplit("-", 1)[-1]
templates.env.filters["run_label"] = run_label
templates.env.filters["when"] = when
templates.env.filters["es"] = lambda v: LABELS_ES.get(v, v)


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


EVENT_STATUSES = ("ok", "no_detections", "error", "source_gap")
ZONES = ("low", "doubt", "accepted")
EXPORT_COLUMNS = ("event_id", "run_id", "seq", "frame_id", "frame_index", "pts_s", "window_id",
                  "captured_at", "inferred_at", "source_id", "task", "model_ref", "model_sha256",
                  "config_ref", "status", "error", "n_detections", "n_low", "n_doubt", "n_accepted",
                  "max_score", "frame_zone", "inference_ms", "queue_ms", "e2e_ms", "image_ref",
                  "capture_reason", "detections")


# Orden de /eventos: clave -> (etiqueta, ORDER BY). Los nulos (sin puntuación o sin tiempo
# de inferencia) van siempre al final; el desempate es run_id, seq.
EVENT_SORTS = {
    "": ("ejecución y secuencia", "run_id, seq"),
    "score_desc": ("máx. puntuación ↓", "max_score IS NULL, max_score DESC, run_id, seq"),
    "score_asc": ("máx. puntuación ↑", "max_score IS NULL, max_score ASC, run_id, seq"),
    "dets_desc": ("detecciones ↓", "n_detections DESC, run_id, seq"),
    "inference_desc": ("tiempo de inferencia ↓", "inference_ms IS NULL, inference_ms DESC, run_id, seq"),
    "e2e_desc": ("extremo a extremo ↓", "e2e_ms IS NULL, e2e_ms DESC, run_id, seq"),
    "recent": ("más recientes", "captured_at DESC, run_id, seq DESC"),
}


class EventFilters(dict):
    """Filtros de eventos validados (los mismos para /eventos, /api/eventos y /exportar).

    Básicos: run_id, status, zone, captured. Avanzados: rango de máx. puntuación
    (score_min/score_max; excluye eventos sin puntuación), rango de detecciones
    (dets_min/dets_max), intervalo de captura (since/until, UTC), ventana (window, índice),
    motivo de captura (reason), vínculo con alertas (in_alert), texto en el id (q) y orden."""

    def where(self) -> tuple[str, list]:
        where, args = [], []
        for key, col in (("run_id", "run_id"), ("status", "status"), ("zone", "frame_zone"),
                         ("reason", "capture_reason")):
            if self[key]:
                where.append(f"{col} = ?"); args.append(self[key])
        if self["captured"]:
            where.append("image_ref IS NOT NULL")
        for key, col, op in (("score_min", "max_score", ">="), ("score_max", "max_score", "<="),
                             ("dets_min", "n_detections", ">="), ("dets_max", "n_detections", "<="),
                             ("since", "captured_at", ">="), ("until", "captured_at", "<=")):
            if self[key] not in ("", None):
                where.append(f"{col} {op} ?"); args.append(self[key])
        if self["window"] not in ("", None):
            where.append("window_id LIKE ?"); args.append(f"%-w{int(self['window']):03d}")
        if self["in_alert"]:
            where.append("event_id IN (SELECT j.value FROM alerts, json_each(alerts.event_ids_json) j)")
        if self["q"]:
            where.append("event_id LIKE ?"); args.append(f"%{self['q']}%")
        return ("WHERE " + " AND ".join(where)) if where else "", args

    def active(self) -> dict:
        return {k: v for k, v in self.items() if v not in ("", None, False)}


def _ts(value: str, name: str) -> str:
    """Acepta fecha u hora ISO (con o sin Z) y la normaliza al formato de captured_at."""
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(422, f"{name}: fecha inválida {value!r}; usa ISO 8601, p. ej. 2026-11-12T16:25:00")
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _num(value: str, name: str, cast, lo=None, hi=None):
    if value in ("", None):
        return ""
    try:
        v = cast(value)
    except ValueError:
        raise HTTPException(422, f"{name}: {value!r} no es un número válido")
    if (lo is not None and v < lo) or (hi is not None and v > hi):
        raise HTTPException(422, f"{name}: {v} fuera del rango [{lo}, {hi}]")
    return v


def event_filters(run_id: str = "", status: str = "", zone: str = "", captured: bool = False,
                  score_min: str = "", score_max: str = "", dets_min: str = "", dets_max: str = "",
                  since: str = "", until: str = "", window: str = "", reason: str = "",
                  in_alert: bool = False, q: str = "", sort: str = "") -> EventFilters:
    if status and status not in EVENT_STATUSES:
        raise HTTPException(422, f"estado desconocido {status!r}; opciones: {', '.join(EVENT_STATUSES)}")
    if zone and zone not in ZONES:
        raise HTTPException(422, f"zona desconocida {zone!r}; opciones: {', '.join(ZONES)}")
    if sort not in EVENT_SORTS:
        raise HTTPException(422, f"orden desconocido {sort!r}; opciones: {', '.join(k for k in EVENT_SORTS if k)}")
    f = EventFilters(
        run_id=run_id, status=status, zone=zone, captured=captured,
        score_min=_num(score_min, "score_min", float, 0, 1), score_max=_num(score_max, "score_max", float, 0, 1),
        dets_min=_num(dets_min, "dets_min", int, 0), dets_max=_num(dets_max, "dets_max", int, 0),
        since=_ts(since, "since") if since else "", until=_ts(until, "until") if until else "",
        window=_num(window, "window", int, 0, 999), reason=reason, in_alert=in_alert, q=q.strip(), sort=sort)
    for lo, hi in (("score_min", "score_max"), ("dets_min", "dets_max"), ("since", "until")):
        if f[lo] not in ("", None) and f[hi] not in ("", None) and f[lo] > f[hi]:
            raise HTTPException(422, f"{lo} ({f[lo]}) es mayor que {hi} ({f[hi]}): el rango está vacío")
    return f


def query_events(f: EventFilters, page):
    clause, args = f.where()
    order = EVENT_SORTS[f["sort"]][1]
    total = rows(f"SELECT COUNT(*) AS n FROM events {clause}", args)[0]["n"]
    if page is None:  # exportación: todos los eventos que cumplen el filtro
        return total, rows(f"SELECT * FROM events {clause} ORDER BY {order}", args)
    items = rows(f"SELECT * FROM events {clause} ORDER BY {order} LIMIT ? OFFSET ?",
                 args + [PAGE, (page - 1) * PAGE])
    return total, items


def query_alerts(run_id, status, rule_id, severity=""):
    where, args = [], []
    if run_id:
        where.append("run_id = ?"); args.append(run_id)
    if status:
        where.append("status = ?"); args.append(status)
    if rule_id:
        where.append("rule_id = ?"); args.append(rule_id)
    if severity:
        where.append("severity = ?"); args.append(severity)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    return rows(f"SELECT * FROM alerts {clause} ORDER BY opened_at DESC", args)


def source_events(run_id: str) -> list[dict]:
    with db() as con:  # bases anteriores al escenario S1 no tienen la tabla
        if not con.execute("SELECT 1 FROM sqlite_master WHERE name='source_events'").fetchone():
            return []
    return rows("SELECT * FROM source_events WHERE run_id=? ORDER BY seq", (run_id,))


def alerts_for_event(event_id: str) -> list[dict]:
    return [a for a in rows("SELECT * FROM alerts WHERE event_ids_json LIKE ?", (f'%"{event_id}"%',))
            if event_id in a["event_ids"]]


# ------------------------------------------------------------------ HTML
def sparkline(wins: list[dict], threshold: float, w: int = 220, h: int = 44) -> dict:
    """Puntos de low_prop por ventana para una gráfica pequeña (0-1 en el eje y). Las ventanas
    insuficientes o sin dato cortan la línea en lugar de dibujarse como 0."""
    n = max(1, len(wins) - 1)
    x = lambda i: round(4 + i * (w - 8) / n, 1)
    y = lambda v: round(h - 4 - v * (h - 8), 1)
    segs, cur, dots = [], [], []
    for i, win in enumerate(wins):
        ok = win["state"] == "eligible" and win["low_prop"] is not None
        if ok:
            cur.append(f"{x(i)},{y(win['low_prop'])}")
        elif cur:
            segs.append(" ".join(cur)); cur = []
        dots.append({"x": x(i), "y": y(win["low_prop"] or 0), "ok": ok, "idx": win["idx"],
                     "v": win["low_prop"], "state": win["state"], "window_id": win["window_id"]})
    if cur:
        segs.append(" ".join(cur))
    return {"w": w, "h": h, "segs": segs, "dots": dots, "ty": y(threshold)}


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    runs = rows("SELECT * FROM runs ORDER BY started_at DESC")
    alerts = rows("SELECT * FROM alerts ORDER BY opened_at DESC")
    threshold = next(r["threshold"] for r in CFG["alerts"] if r["rule_id"] == "baja-confianza-v1")
    wins = rows("SELECT run_id, idx, window_id, state, low_prop FROM windows ORDER BY run_id, idx")
    for r in runs:
        mine = [a for a in alerts if a["run_id"] == r["run_id"]]
        r["n_alerts"], r["alerts"] = len(mine), mine
        r["spark"] = sparkline([w for w in wins if w["run_id"] == r["run_id"]], threshold)
    n_captures = rows("SELECT COUNT(*) AS n FROM events WHERE image_ref IS NOT NULL")[0]["n"]
    kpis = {
        "runs": len(runs),
        "events": sum((r["summary"] or {}).get("events", 0) for r in runs),
        "detections": sum((r["summary"] or {}).get("detections", 0) for r in runs),
        "alerts": len(alerts), "open": sum(a["status"] == "open" for a in alerts),
        "captures": n_captures, "reviewed": len(REVIEWS.current()),
        "windows": len(wins), "insufficient": sum(w["state"] == "insufficient" for w in wins),
    }
    return templates.TemplateResponse(request, "home.html", {
        "runs": runs, "latest": alerts[:6], "kpis": kpis, "threshold": threshold})


FILTER_KEYS = ("run_id", "status", "zone", "captured", "score_min", "score_max", "dets_min", "dets_max",
               "since", "until", "window", "reason", "in_alert", "q", "sort")


def filters_from(request: Request) -> EventFilters:
    """Filtros de la página HTML: los mismos parámetros que la API, leídos de la URL."""
    qp = request.query_params
    raw = {k: qp.get(k, "") for k in FILTER_KEYS}
    for k in ("captured", "in_alert"):
        raw[k] = raw[k].lower() in ("true", "1", "on")
    return event_filters(**raw)


def filter_options() -> dict:
    return {"run_ids": run_ids(), "statuses": EVENT_STATUSES, "zones": ZONES,
            "sorts": {k: v[0] for k, v in EVENT_SORTS.items()},
            "reasons": [r["capture_reason"] for r in rows(
                "SELECT DISTINCT capture_reason FROM events WHERE capture_reason IS NOT NULL ORDER BY 1")]}


@app.get("/eventos", response_class=HTMLResponse)
def events_page(request: Request, page: int = Query(1, ge=1)):
    try:
        f = filters_from(request)
        error, status_code = None, 200
        total, items = query_events(f, page)
    except HTTPException as exc:  # filtro inválido: la página explica el error y no muestra resultados
        f = EventFilters({k: request.query_params.get(k, "") for k in FILTER_KEYS})
        error, status_code, total, items = exc.detail, exc.status_code, 0, []
    return templates.TemplateResponse(request, "events.html", {
        "items": items, "total": total, "page": page, "pages": max(1, -(-total // PAGE)),
        "f": f, "active": f.active(), "error": error, **filter_options()}, status_code=status_code)


@app.get("/exportar/eventos.{fmt}")
def export_events(fmt: str, f: EventFilters = Depends(event_filters)):
    """Descarga de los eventos que cumplen los mismos filtros que /eventos (sin paginar)."""
    if fmt not in ("csv", "jsonl"):
        raise HTTPException(404, "formato no soportado: usa .csv o .jsonl")
    if f["run_id"] and f["run_id"] not in run_ids():
        raise HTTPException(404, f"ejecución inexistente: {f['run_id']}")
    total, items = query_events(f, None)
    if fmt == "jsonl":
        body = "".join(json.dumps({k: e.get(k) for k in EXPORT_COLUMNS}, ensure_ascii=False) + "\n"
                       for e in items)
        media = "application/x-ndjson"
    else:
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=EXPORT_COLUMNS, lineterminator="\n")
        w.writeheader()
        for e in items:
            w.writerow({k: json.dumps(e[k], ensure_ascii=False) if k == "detections" else e.get(k)
                        for k in EXPORT_COLUMNS})
        body, media = buf.getvalue(), "text/csv; charset=utf-8"
    filters = f.active()
    flags = {"captured": "captura", "in_alert": "en-alerta"}
    tag = "-".join(flags[k] if v is True else str(v).replace(":", "") for k, v in filters.items())[:120] or "todos"
    return Response(body, media_type=media, headers={
        "Content-Disposition": f'attachment; filename="eventos-{tag}.{fmt}"',
        "X-Export-Count": str(total),
        "X-Export-Filters": urlencode({k: "true" if v is True else v for k, v in filters.items()}),
        "X-Export-Generated-At": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "X-Export-Source": str(DB_PATH.relative_to(ROOT)) if DB_PATH.is_relative_to(ROOT) else DB_PATH.name})


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


# ------------------------------------------------------------------ revisión de capturas
def captures(run_id: str, reason: str, review: str) -> list[dict]:
    where, args = ["image_ref IS NOT NULL"], []
    if run_id:
        where.append("run_id = ?"); args.append(run_id)
    if reason:
        where.append("capture_reason = ?"); args.append(reason)
    items = rows(f"SELECT event_id, run_id, seq, frame_id, captured_at, status, frame_zone, max_score, "
                 f"n_detections, n_low, image_ref, capture_reason, window_id FROM events "
                 f"WHERE {' AND '.join(where)} ORDER BY run_id, seq", args)
    cur = REVIEWS.current()
    for e in items:
        e["review"] = cur.get(e["event_id"])
    if review == "sin_revisar":
        items = [e for e in items if not e["review"]]
    elif review:
        items = [e for e in items if e["review"] and e["review"]["label"] == review]
    return items


def next_unreviewed(ev: dict) -> str | None:
    cur = REVIEWS.current()
    nxt = [r["event_id"] for r in rows("SELECT event_id FROM events WHERE run_id=? AND seq>? AND "
                                       "image_ref IS NOT NULL ORDER BY seq", (ev["run_id"], ev["seq"]))
           if r["event_id"] not in cur]
    return nxt[0] if nxt else None


@app.get("/capturas", response_class=HTMLResponse)
def captures_page(request: Request, run_id: str = "", reason: str = "", review: str = "",
                  page: int = Query(1, ge=1)):
    if review and review not in ("sin_revisar", *LABELS):
        raise HTTPException(422, f"estado de revisión desconocido: {review}")
    items = captures(run_id, reason, review)
    pages = max(1, -(-len(items) // GALLERY_PAGE))
    reasons = [r["capture_reason"] for r in rows(
        "SELECT DISTINCT capture_reason FROM events WHERE capture_reason IS NOT NULL ORDER BY 1")]
    return templates.TemplateResponse(request, "captures.html", {
        "items": items[(page - 1) * GALLERY_PAGE: page * GALLERY_PAGE], "total": len(items),
        "page": page, "pages": pages, "run_ids": run_ids(), "reasons": reasons, "labels": LABELS,
        "f": {"run_id": run_id, "reason": reason, "review": review}})


@app.get("/capturas/{event_id}", response_class=HTMLResponse)
def capture_page(request: Request, event_id: str, guardado: int = 0, error: str = "",
                 status_code: int = 200):
    ev = one("SELECT * FROM events WHERE event_id=?", (event_id,))
    return templates.TemplateResponse(request, "capture.html", {
        "ev": ev, "alerts": alerts_for_event(event_id), "history": REVIEWS.history(event_id),
        "labels": LABELS, "next": next_unreviewed(ev), "saved": guardado, "error": error},
        status_code=status_code)


@app.post("/capturas/{event_id}/revision")
async def capture_review(request: Request, event_id: str):
    form = {k: v[0] for k, v in parse_qs((await request.body()).decode()).items()}
    ev = one("SELECT * FROM events WHERE event_id=?", (event_id,))
    try:
        REVIEWS.add(ev, [a["alert_id"] for a in alerts_for_event(event_id)],
                    form.get("label", ""), form.get("note", ""), form.get("reviewer", ""))
    except ReviewError as exc:
        return capture_page(request, event_id, error=str(exc), status_code=exc.status)
    nxt = next_unreviewed(ev) if form.get("siguiente") else None
    return RedirectResponse(f"/capturas/{nxt}?guardado=1" if nxt else f"/capturas/{event_id}?guardado=1",
                            status_code=303)


@app.get("/api/revisiones")
def api_reviews(run_id: str = ""):
    return {"labels": LABELS, "items": REVIEWS.all(run_id)}


@app.post("/api/capturas/{event_id}/revision", status_code=201)
async def api_capture_review(event_id: str, request: Request):
    body = await request.json()
    ev = one("SELECT * FROM events WHERE event_id=?", (event_id,))
    try:
        return REVIEWS.add(ev, [a["alert_id"] for a in alerts_for_event(event_id)],
                           body.get("label", ""), body.get("note", ""), body.get("reviewer", ""))
    except ReviewError as exc:
        raise HTTPException(exc.status, str(exc))


@app.get("/alertas", response_class=HTMLResponse)
def alerts_page(request: Request, run_id: str = "", status: str = "", rule_id: str = "", severity: str = ""):
    return templates.TemplateResponse(request, "alerts.html", {
        "items": query_alerts(run_id, status, rule_id, severity), "run_ids": run_ids(),
        "rule_ids": [r["rule_id"] for r in CFG["alerts"]],
        "severities": sorted({r["severity"] for r in CFG["alerts"]}),
        "f": {"run_id": run_id, "status": status, "rule_id": rule_id, "severity": severity}})


@app.get("/alertas/{alert_id}", response_class=HTMLResponse)
def alert_page(request: Request, alert_id: str):
    a = one("SELECT * FROM alerts WHERE alert_id=?", (alert_id,))
    marks = ",".join("?" * len(a["event_ids"]))
    evs = rows(f"SELECT * FROM events WHERE event_id IN ({marks}) ORDER BY seq", a["event_ids"])
    rule = next((r for r in CFG["alerts"] if r["rule_id"] == a["rule_id"]), None)
    captured = [e for e in evs if e["image_ref"]]
    reviews = REVIEWS.current([e["event_id"] for e in captured])
    return templates.TemplateResponse(request, "alert.html", {
        "a": a, "events": evs, "rule": rule, "captured": captured, "reviews": reviews,
        "review_summary": REVIEWS.summary([e["event_id"] for e in captured]), "labels": LABELS})


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
        "alerts": rows("SELECT * FROM alerts WHERE run_id=? ORDER BY opened_at", (run_id,)),
        "source_events": source_events(run_id),
        "n_gaps": rows("SELECT COUNT(*) AS n FROM events WHERE run_id=? AND status='source_gap'",
                       (run_id,))[0]["n"]})


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


# ------------------------------------------------------------------ vista en vivo
def live_status() -> dict:
    """Estado publicado por `monitor.pipeline --live` más una salud derivada."""
    path = LIVE_DIR / "status.json"
    if not path.exists():
        return {"health": "sin_ejecucion", "detail": "No hay estado publicado. Ejecuta el pipeline con --live."}
    try:
        st = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:  # escritura atómica: no debería pasar
        return {"health": "error", "detail": f"estado ilegible: {exc}"}
    age = datetime.now(timezone.utc).timestamp() - datetime.fromisoformat(
        st["updated_at"].replace("Z", "+00:00")).timestamp()
    last = st.get("last_event") or {}
    if st["state"] == "finished":
        health, detail = "terminada", "La ejecución terminó; se muestra el último estado publicado."
    elif age > LIVE_STALE_S:
        health, detail = "detenido", f"Sin actualizaciones desde hace {age:.1f} s: el monitor no está publicando."
    elif last.get("status") == "source_gap":
        health, detail = "hueco_fuente", last.get("error") or "La fuente no entrega frames."
    else:
        health, detail = "en_curso", "Recibiendo frames."
    return {**st, "health": health, "detail": detail, "age_s": round(age, 2)}


@app.get("/en-vivo", response_class=HTMLResponse)
def live_page(request: Request):
    return templates.TemplateResponse(request, "live.html", {"st": live_status(), "stale_s": LIVE_STALE_S})


@app.get("/api/en-vivo")
def api_live():
    return live_status()


@app.get("/en-vivo/frame.jpg")
def live_frame():
    path = LIVE_DIR / "frame.jpg"
    if not path.exists():
        raise HTTPException(404, "todavía no hay frame publicado")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/evidencia/{path:path}")
def evidence_file(path: str):
    target = (ROOT / path).resolve()
    if not target.is_relative_to(EVID_DIR) or not target.is_file():
        raise HTTPException(404, "archivo no encontrado")
    return FileResponse(target)


# ------------------------------------------------------------------ JSON
@app.get("/api/eventos")
def api_events(f: EventFilters = Depends(event_filters), page: int = Query(1, ge=1)):
    total, items = query_events(f, page)
    return {"total": total, "page": page, "page_size": PAGE, "filters": f.active(), "items": items}


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
