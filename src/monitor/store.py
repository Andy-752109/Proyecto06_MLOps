"""Persistencia: SQLite (consultada por el portal) + JSONL por ejecución (recalculable).

Cada registro se escribe en ambos destinos con el mismo contenido. Las imágenes se
guardan en evidencias/runs/<run_id>/capturas/ y no existe ningún proceso de borrado.
"""
import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS configs (
  config_ref TEXT PRIMARY KEY, snapshot_json TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, scenario TEXT, description TEXT, started_at TEXT, ended_at TEXT,
  status TEXT, config_ref TEXT REFERENCES configs(config_ref), source_ref TEXT, source_id TEXT,
  source_json TEXT, model_ref TEXT, model_sha256 TEXT, environment_json TEXT,
  git_commit TEXT, git_dirty INTEGER, command TEXT, summary_json TEXT);
CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY, run_id TEXT REFERENCES runs(run_id), seq INTEGER,
  frame_id TEXT, frame_index INTEGER, pts_s REAL, window_id TEXT,
  captured_at TEXT, inferred_at TEXT, source_id TEXT, task TEXT,
  model_ref TEXT, model_sha256 TEXT, config_ref TEXT, status TEXT, error TEXT,
  n_detections INTEGER, n_low INTEGER, n_doubt INTEGER, n_accepted INTEGER,
  max_score REAL, frame_zone TEXT, inference_ms REAL, queue_ms REAL, e2e_ms REAL,
  image_ref TEXT, capture_reason TEXT, detections_json TEXT);
CREATE INDEX IF NOT EXISTS ix_events_run ON events(run_id, seq);
CREATE TABLE IF NOT EXISTS detections (
  det_id TEXT PRIMARY KEY, event_id TEXT REFERENCES events(event_id), run_id TEXT,
  rank INTEGER, class_id INTEGER, class_name TEXT, score REAL, zone TEXT,
  x1 REAL, y1 REAL, x2 REAL, y2 REAL);
CREATE TABLE IF NOT EXISTS resource_samples (
  run_id TEXT, seq INTEGER, event_id TEXT, ts TEXT, rss_mb REAL, cpu_percent REAL);
CREATE TABLE IF NOT EXISTS windows (
  window_id TEXT PRIMARY KEY, run_id TEXT, idx INTEGER, first_seq INTEGER, last_seq INTEGER,
  start_at TEXT, end_at TEXT, n_events INTEGER, n_ok INTEGER, n_no_detections INTEGER,
  n_errors INTEGER, n_valid INTEGER, n_dets INTEGER, n_low INTEGER, n_doubt INTEGER,
  n_accepted INTEGER, low_prop REAL, state TEXT, config_ref TEXT, event_ids_json TEXT);
CREATE TABLE IF NOT EXISTS metric_values (
  run_id TEXT, window_id TEXT, metric_id TEXT, grp TEXT, value REAL, unit TEXT,
  n_obs INTEGER, status TEXT, detail_json TEXT, PRIMARY KEY (window_id, metric_id));
CREATE TABLE IF NOT EXISTS rule_evaluations (
  run_id TEXT, window_id TEXT, rule_id TEXT, outcome TEXT, observed_json TEXT, alert_id TEXT,
  PRIMARY KEY (window_id, rule_id));
CREATE TABLE IF NOT EXISTS source_events (
  run_id TEXT, seq INTEGER, ts TEXT, kind TEXT, detail_json TEXT, PRIMARY KEY (run_id, seq));
CREATE TABLE IF NOT EXISTS alerts (
  alert_id TEXT PRIMARY KEY, run_id TEXT, rule_id TEXT, severity TEXT, status TEXT,
  opened_at TEXT, resolved_at TEXT, first_window_id TEXT, last_window_id TEXT,
  n_windows INTEGER, config_ref TEXT, model_ref TEXT, source_id TEXT, condition TEXT,
  reason TEXT, suggested_action TEXT, observed_json TEXT, window_ids_json TEXT,
  event_ids_json TEXT, image_refs_json TEXT);
"""

JSON_COLS = {"detections_json", "observed_json", "window_ids_json", "event_ids_json",
             "image_refs_json", "detail_json", "summary_json", "environment_json", "source_json",
             "snapshot_json"}


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    for k in JSON_COLS & d.keys():
        if d[k] is not None:
            d[k[:-5]] = json.loads(d.pop(k))
        else:
            d[k[:-5]] = d.pop(k)
    return d


def _to_row(rec: dict) -> dict:
    out = {}
    for k, v in rec.items():
        if f"{k}_json" in JSON_COLS:
            out[f"{k}_json"] = json.dumps(v, ensure_ascii=False)
        else:
            out[k] = v
    return out


class RunStore:
    """Escribe los registros de una ejecución en SQLite y en JSONL."""

    TABLES = {
        "events": "events.jsonl", "detections": "detections.jsonl",
        "resource_samples": "resources.jsonl", "windows": "windows.jsonl",
        "metric_values": "metrics.jsonl", "rule_evaluations": "rule_evaluations.jsonl",
        "alerts": "alerts.jsonl", "source_events": "source_events.jsonl",
    }

    def __init__(self, con: sqlite3.Connection, run_dir: Path):
        self.con = con
        self.run_dir = run_dir
        (run_dir / "capturas").mkdir(parents=True, exist_ok=True)
        self._files = {t: open(run_dir / f, "a", encoding="utf-8") for t, f in self.TABLES.items()}

    def insert(self, table: str, rec: dict, replace: bool = False) -> None:
        row = _to_row(rec)
        cols = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        verb = "INSERT OR REPLACE" if replace else "INSERT"
        self.con.execute(f"{verb} INTO {table} ({cols}) VALUES ({marks})", list(row.values()))
        if table != "alerts":  # las alertas se vuelcan completas al cerrar (cambian de estado)
            self._files[table].write(json.dumps(rec, ensure_ascii=False) + "\n")

    def dump_alerts(self, run_id: str) -> None:
        rows = self.con.execute("SELECT * FROM alerts WHERE run_id=? ORDER BY opened_at", (run_id,))
        f = self._files["alerts"]
        f.seek(0)
        f.truncate()
        for r in rows:
            f.write(json.dumps(row_to_dict(r), ensure_ascii=False) + "\n")

    def commit(self) -> None:
        self.con.commit()
        for f in self._files.values():
            f.flush()

    def close(self) -> None:
        self.commit()
        for f in self._files.values():
            f.close()
