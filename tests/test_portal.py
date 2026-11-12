"""El portal responde y enlaza evento -> captura -> alerta sobre la base de evidencias versionada."""
import html

import pytest
from fastapi.testclient import TestClient

from monitor.portal.app import DB_PATH, app

pytestmark = pytest.mark.skipif(not DB_PATH.exists(), reason="sin base de evidencias")
client = TestClient(app)


def test_pages_respond():
    for url in ("/", "/eventos", "/alertas"):
        assert client.get(url).status_code == 200


def test_empty_query_states():
    r = client.get("/eventos", params={"run_id": "no-existe"})
    assert r.status_code == 200 and "Ningún evento coincide" in r.text
    assert client.get("/alertas", params={"run_id": "no-existe"}).status_code == 200
    assert client.get("/eventos/no-existe").status_code == 404


def test_alert_links_resolve_to_events_and_images():
    alerts = client.get("/api/alertas").json()["items"]
    assert alerts, "se esperan alertas de C2"
    a = alerts[0]
    page = client.get(f"/alertas/{a['alert_id']}")
    assert page.status_code == 200 and html.escape(a["reason"], quote=False) in page.text
    for eid in a["event_ids"][:5]:
        assert client.get(f"/api/eventos/{eid}").status_code == 200
    for ref in a["image_refs"]:
        img = client.get(f"/evidencia/{ref}")
        assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"


def test_path_traversal_blocked():
    assert client.get("/evidencia/../config/monitor.yaml").status_code == 404
