"""Tablero histórico: casos normal, borde y error sobre una base SQLite sintética.

La base sintética solo prueba la lógica del tablero (series, huecos, grupos, errores);
los datos reales de C1/C2 se verifican con scripts/verify_dashboard.py.
"""
import json

import pytest
from fastapi.testclient import TestClient

import monitor.portal.app as portal
from monitor.config import load_config
from monitor.metrics import BASE_METRICS
from monitor.portal import dashboard
from monitor.store import connect

CFG = load_config()
REF = {"config_ref": "cfg-A", "model_ref": "m@1", "low_prop": 0.2}


def add_run(con, run_id, config_ref="cfg-A", model_ref="m@1", windows=(), alerts=()):
    """windows: lista de (state, {metric_id: valor o None})."""
    con.execute("INSERT INTO runs (run_id, scenario, started_at, config_ref, model_ref) VALUES (?,?,?,?,?)",
                (run_id, run_id.split("-")[0], f"2026-01-01T00:00:0{len(list(con.execute('SELECT 1 FROM runs')))}Z",
                 config_ref, model_ref))
    for i, (state, vals) in enumerate(windows):
        wid = f"{run_id}-w{i:03d}"
        con.execute("INSERT INTO windows (window_id, run_id, idx, state) VALUES (?,?,?,?)", (wid, run_id, i, state))
        for mid in BASE_METRICS:
            v = vals.get(mid, 0.5)
            con.execute("INSERT INTO metric_values (run_id, window_id, metric_id, value, n_obs, status) "
                        "VALUES (?,?,?,?,?,?)", (run_id, wid, mid, v, 0 if v is None else 20,
                                                 "no_data" if v is None else "ok"))
    for aid, rule, sev, status, idxs in alerts:
        con.execute("INSERT INTO alerts (alert_id, run_id, rule_id, severity, status, opened_at, window_ids_json) "
                    "VALUES (?,?,?,?,?,?,?)", (aid, run_id, rule, sev, status, "2026-01-01T00:00:00Z",
                                               json.dumps([f"{run_id}-w{i:03d}" for i in idxs])))
    con.commit()


@pytest.fixture
def con(tmp_path):
    c = connect(tmp_path / "t.db")
    yield c
    c.close()


def test_empty_db_and_no_selection(con):
    assert "No hay ejecuciones" in dashboard.build(con, ["x"], CFG, REF)["empty"]
    add_run(con, "c1-a", windows=[("eligible", {})])
    d = dashboard.build(con, [], CFG, REF)
    assert d["groups"] == [] and "Selecciona" in d["empty"]


def test_normal_series_alert_span_and_reference(con):
    add_run(con, "c2-a", windows=[("eligible", {"g4_low_conf_prop": v}) for v in (0.1, 0.5, 0.6, 0.1)],
            alerts=[("c2-a-a01", "baja-confianza-v1", "warning", "resolved", [1, 2])])
    d = dashboard.build(con, ["c2-a"], CFG, REF)
    run = d["groups"][0]["runs"][0]
    assert [p["y"] for p in run["series"]["g4_low_conf_prop"]] == [0.1, 0.5, 0.6, 0.1]
    assert (run["alerts"][0]["first_idx"], run["alerts"][0]["last_idx"]) == (1, 2)
    guides = d["groups"][0]["charts"][3]["guides"]
    assert {g["kind"] for g in guides} == {"rule", "ref"}
    assert pytest.approx(0.35) in [g["y"] for g in guides]  # referencia 0.20 + delta 0.15
    plot = dashboard.layout(d["groups"][0])[3]
    assert len(plot["series"][0]["paths"]) == 1 and len(plot["series"][0]["points"]) == 4


def test_null_metric_breaks_line_and_insufficient_is_marked(con):
    add_run(con, "c3-a", windows=[("eligible", {}), ("insufficient", {"g1_inference_ms_p95": None}),
                                  ("eligible", {})])
    d = dashboard.build(con, ["c3-a"], CFG, REF)
    run = d["groups"][0]["runs"][0]
    assert run["summary"]["n_insufficient"] == 1 and run["summary"]["n_no_data"] == 1
    g1 = dashboard.layout(d["groups"][0])[0]["series"][0]
    assert len(g1["paths"]) == 2, "un valor nulo corta la línea en dos tramos, no se dibuja como 0"
    assert [p["missing"] for p in g1["points"]] == [False, True, False]
    assert g1["points"][1]["state"] == "insufficient"


def test_mixed_config_is_split_and_reference_only_where_comparable(con):
    add_run(con, "c1-a", windows=[("eligible", {})])
    add_run(con, "c1-b", config_ref="cfg-B", windows=[("eligible", {})])
    d = dashboard.build(con, ["c1-a", "c1-b"], CFG, REF)
    assert len(d["groups"]) == 2 and any("grupos separados" in n for n in d["notes"])
    comparable = {g["config_ref"]: g["reference_comparable"] for g in d["groups"]}
    assert comparable == {"cfg-A": True, "cfg-B": False}


def test_unknown_too_many_and_windowless_runs(con):
    for r in ("r1-a", "r2-a", "r3-a", "r4-a"):
        add_run(con, r, windows=[("eligible", {})])
    add_run(con, "r5-a")
    d = dashboard.build(con, ["no-existe", "r1-a", "r2-a", "r3-a", "r4-a"], CFG, REF)
    assert any("inexistentes: no-existe" in e for e in d["errors"])
    assert any("máximo de 3" in e and "r4-a" in e for e in d["errors"])
    assert sum(len(g["runs"]) for g in d["groups"]) == 3
    d = dashboard.build(con, ["r5-a"], CFG, REF)
    assert any("no cerró ninguna ventana" in n for n in d["notes"])
    assert dashboard.layout(d["groups"][0])[0]["series"][0]["points"] == []


def test_http_states_on_synthetic_db(con, tmp_path, monkeypatch):
    add_run(con, "c3-a", windows=[("eligible", {}), ("insufficient", {"g1_inference_ms_p95": None})])
    monkeypatch.setattr(portal, "DB_PATH", tmp_path / "t.db")
    client = TestClient(portal.app)
    r = client.get("/tablero", params={"run_id": "c3-a"})
    assert r.status_code == 200 and "/ventanas/c3-a-w001" in r.text and "sin datos (no_data)" in r.text
    assert client.get("/tablero", params={"run_id": "nada"}).status_code == 404
    assert "Selecciona" in client.get("/tablero", params={"enviado": "1"}).text
    assert client.get("/api/tablero", params={"run_id": "nada"}).status_code == 404
    monkeypatch.setattr(portal, "DB_PATH", tmp_path / "no-existe.db")
    assert client.get("/tablero").status_code == 503
