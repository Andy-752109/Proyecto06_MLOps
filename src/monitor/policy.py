"""Política de confianza: dos umbrales, tres zonas.

    s <  lower          -> "low"       (baja confianza)
    lower <= s < upper  -> "doubt"     (duda)
    s >= upper          -> "accepted"  (aceptada por la política; no implica acierto)

Fallos de inferencia ("error") y frames sin detecciones ("no_detections") son
estados del evento, no zonas: no reciben puntuación artificial.
"""
ZONES = ("low", "doubt", "accepted")


def zone_for(score: float | None, lower: float, upper: float) -> str | None:
    if score is None:
        return None
    if score < lower:
        return "low"
    if score < upper:
        return "doubt"
    return "accepted"


def frame_summary(dets: list[dict], lower: float, upper: float) -> dict:
    """Asigna zona a cada detección y resume el frame.

    frame_zone = zona de la detección con mayor puntuación (resumen informativo del
    frame; las reglas usan la unidad 'detección')."""
    counts = {z: 0 for z in ZONES}
    for d in dets:
        d["zone"] = zone_for(d["score"], lower, upper)
        counts[d["zone"]] += 1
    max_score = max((d["score"] for d in dets), default=None)
    return {
        "n_detections": len(dets),
        "n_low": counts["low"],
        "n_doubt": counts["doubt"],
        "n_accepted": counts["accepted"],
        "max_score": max_score,
        "frame_zone": zone_for(max_score, lower, upper),
    }
