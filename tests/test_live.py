"""Estados de la vista en vivo con estados sintéticos (sin ejecutar el pipeline)."""
import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import monitor.portal.app as portal

client = TestClient(portal.app)


def status(age_s=0.0, state="running", last_status="ok"):
    ts = (datetime.now(timezone.utc) - timedelta(seconds=age_s)).isoformat(timespec="milliseconds")
    return {"run_id": "t", "scenario": "t", "updated_at": ts.replace("+00:00", "Z"), "state": state,
            "last_event": {"status": last_status, "error": "sin frames de la fuente durante 2.0 s"
                           if last_status == "source_gap" else None}}


def health(tmp_path, monkeypatch, st):
    monkeypatch.setattr(portal, "LIVE_DIR", tmp_path)
    if st is not None:
        (tmp_path / "status.json").write_text(st if isinstance(st, str) else json.dumps(st))
    return client.get("/api/en-vivo").json()["health"]


def test_live_health_states(tmp_path, monkeypatch):
    assert health(tmp_path, monkeypatch, None) == "sin_ejecucion"
    assert health(tmp_path, monkeypatch, status()) == "en_curso"
    assert health(tmp_path, monkeypatch, status(last_status="source_gap")) == "hueco_fuente"
    assert health(tmp_path, monkeypatch, status(age_s=10)) == "detenido"
    assert health(tmp_path, monkeypatch, status(age_s=10, last_status="source_gap")) == "detenido"
    assert health(tmp_path, monkeypatch, status(age_s=100, state="finished")) == "terminada"
    assert health(tmp_path, monkeypatch, "{no es json") == "error"


def test_live_page_and_missing_frame(tmp_path, monkeypatch):
    monkeypatch.setattr(portal, "LIVE_DIR", tmp_path)
    assert client.get("/en-vivo").status_code == 200
    assert client.get("/en-vivo/frame.jpg").status_code == 404
