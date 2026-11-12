"""Filtros avanzados de eventos (adicional F5) sobre la base de evidencias versionada."""
import pytest
from fastapi.testclient import TestClient

from monitor.portal.app import DB_PATH, app

pytestmark = pytest.mark.skipif(not DB_PATH.exists(), reason="sin base de evidencias")
client = TestClient(app)


def all_items(**params):
    items, page = [], 1
    while True:
        body = client.get("/api/eventos", params={**params, "page": page}).json()
        items += body["items"]
        if page * body["page_size"] >= body["total"]:
            return items
        page += 1


def test_score_range_excludes_unscored_and_respects_bounds():
    items = all_items(score_min=0.4, score_max=0.7)
    assert items and all(0.4 <= e["max_score"] <= 0.7 for e in items)


def test_sort_desc_is_monotonic_with_nulls_last():
    scores = [e["max_score"] for e in all_items(sort="score_desc")]
    scored = [s for s in scores if s is not None]
    assert scored == sorted(scored, reverse=True) and scores[:len(scored)] == scored


def test_in_alert_only_returns_events_cited_by_alerts():
    cited = {e for a in client.get("/api/alertas").json()["items"] for e in a["event_ids"]}
    items = all_items(in_alert="true")
    assert items and {e["event_id"] for e in items} == cited


def test_window_and_export_use_the_same_filters():
    run = client.get("/api/eventos").json()["items"][0]["run_id"]
    items = all_items(run_id=run, window=1)
    assert len(items) == 20 and all(e["window_id"].endswith("-w001") for e in items)
    csv = client.get("/exportar/eventos.csv", params={"run_id": run, "window": 1})
    assert csv.headers["x-export-count"] == "20"


@pytest.mark.parametrize("params, text", [
    ({"score_min": 0.9, "score_max": 0.1}, "es mayor que"),
    ({"score_min": 2}, "fuera del rango"),
    ({"since": "mañana"}, "fecha inválida"),
    ({"sort": "azar"}, "orden desconocido"),
    ({"dets_max": "muchas"}, "no es un número"),
])
def test_invalid_filters_are_rejected_everywhere(params, text):
    for url in ("/eventos", "/api/eventos", "/exportar/eventos.jsonl"):
        r = client.get(url, params=params)
        assert r.status_code == 422 and text in r.text
