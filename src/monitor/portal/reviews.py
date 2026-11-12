"""Revisión manual de capturas: persistencia propia (no toca la base de monitoreo).

Cada revisión es un registro nuevo (historial sin borrado); el estado vigente de una
captura es su revisión más reciente. Las etiquetas describen lo que una persona observa en
la imagen; no se usan como métrica de calidad del modelo.
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

LABELS = {
    "confirma": "Las cajas corresponden a personas visibles",
    "falso_positivo": "Al menos una caja no corresponde a una persona",
    "omision": "Hay al menos una persona visible sin caja",
    "imagen_degradada": "La imagen está desenfocada, oscura u ocluida",
    "dudosa": "No se puede decidir con la imagen",
}
MAX_NOTE = 500

SCHEMA = """
CREATE TABLE IF NOT EXISTS reviews (
  review_id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL, run_id TEXT NOT NULL,
  image_ref TEXT NOT NULL, label TEXT NOT NULL, note TEXT, reviewer TEXT NOT NULL,
  created_at TEXT NOT NULL, alert_ids_json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_reviews_event ON reviews(event_id, review_id);
"""


class ReviewError(ValueError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class ReviewStore:
    def __init__(self, path: Path):
        self.path = path

    def _con(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        con.executescript(SCHEMA)
        return con

    @staticmethod
    def _row(r) -> dict:
        d = dict(r)
        d["alert_ids"] = json.loads(d.pop("alert_ids_json"))
        return d

    def add(self, event: dict, alert_ids: list[str], label: str, note: str, reviewer: str) -> dict:
        if not event.get("image_ref"):
            raise ReviewError(409, "el evento no tiene captura: no hay imagen que revisar")
        if label not in LABELS:
            raise ReviewError(422, f"etiqueta desconocida {label!r}; opciones: {', '.join(LABELS)}")
        reviewer, note = (reviewer or "").strip(), (note or "").strip()
        if not reviewer:
            raise ReviewError(422, "falta el nombre de quien revisa")
        if len(note) > MAX_NOTE:
            raise ReviewError(422, f"la nota supera {MAX_NOTE} caracteres")
        rec = {"event_id": event["event_id"], "run_id": event["run_id"], "image_ref": event["image_ref"],
               "label": label, "note": note or None, "reviewer": reviewer,
               "created_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
               "alert_ids_json": json.dumps(alert_ids)}
        with self._con() as con:
            cur = con.execute(f"INSERT INTO reviews ({', '.join(rec)}) VALUES ({', '.join('?' * len(rec))})",
                              list(rec.values()))
            return self._row(con.execute("SELECT * FROM reviews WHERE review_id=?", (cur.lastrowid,)).fetchone())

    def history(self, event_id: str) -> list[dict]:
        if not self.path.exists():
            return []
        with self._con() as con:
            return [self._row(r) for r in con.execute(
                "SELECT * FROM reviews WHERE event_id=? ORDER BY review_id DESC", (event_id,))]

    def current(self, event_ids: list[str] | None = None) -> dict[str, dict]:
        """Revisión vigente por evento (la más reciente)."""
        if not self.path.exists():
            return {}
        with self._con() as con:
            rows = con.execute("SELECT r.* FROM reviews r JOIN (SELECT event_id, MAX(review_id) AS m "
                               "FROM reviews GROUP BY event_id) x ON r.review_id = x.m")
            cur = {r["event_id"]: self._row(r) for r in rows}
        return cur if event_ids is None else {k: v for k, v in cur.items() if k in set(event_ids)}

    def all(self, run_id: str = "") -> list[dict]:
        if not self.path.exists():
            return []
        with self._con() as con:
            sql, args = "SELECT * FROM reviews", ()
            if run_id:
                sql, args = sql + " WHERE run_id=?", (run_id,)
            return [self._row(r) for r in con.execute(sql + " ORDER BY review_id", args)]

    def summary(self, event_ids: list[str]) -> dict:
        cur = self.current(event_ids)
        counts = {k: 0 for k in LABELS}
        for r in cur.values():
            counts[r["label"]] += 1
        return {"reviewed": len(cur), "by_label": counts}
