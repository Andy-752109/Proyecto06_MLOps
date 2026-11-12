"""Revisión manual de capturas: validaciones, historial y estado vigente."""
import pytest

from monitor.portal.reviews import ReviewError, ReviewStore

EV = {"event_id": "r-e001", "run_id": "r", "image_ref": "evidencias/runs/r/capturas/r-e001.jpg"}


def test_history_is_append_only_and_latest_wins(tmp_path):
    store = ReviewStore(tmp_path / "rev.db")
    assert store.current() == {} and store.history("r-e001") == []  # base aún inexistente
    store.add(EV, ["r-a01"], "dudosa", "", "ana")
    store.add(EV, ["r-a01"], "imagen_degradada", "desenfocada", "ana")
    hist = store.history("r-e001")
    assert [h["label"] for h in hist] == ["imagen_degradada", "dudosa"]
    assert store.current()["r-e001"]["label"] == "imagen_degradada"
    assert hist[0]["alert_ids"] == ["r-a01"] and hist[0]["image_ref"] == EV["image_ref"]
    s = store.summary(["r-e001", "r-e002"])
    assert s["reviewed"] == 1 and s["by_label"]["imagen_degradada"] == 1


@pytest.mark.parametrize("event,label,note,reviewer,status", [
    (dict(EV, image_ref=None), "dudosa", "", "ana", 409),
    (EV, "excelente", "", "ana", 422),
    (EV, "dudosa", "", "   ", 422),
    (EV, "dudosa", "x" * 501, "ana", 422),
])
def test_invalid_reviews_are_rejected(tmp_path, event, label, note, reviewer, status):
    store = ReviewStore(tmp_path / "rev.db")
    with pytest.raises(ReviewError) as exc:
        store.add(event, [], label, note, reviewer)
    assert exc.value.status == status and store.all() == []
