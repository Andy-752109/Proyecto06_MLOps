"""Reglas de alerta evaluadas al cerrar cada ventana.

Estado de ventana:
  eligible     -> n_valid >= min_frames y n_dets >= min_detections
  insufficient -> evidencia insuficiente; NO equivale a normalidad

Resultados por regla y ventana (outcome):
  fired, continuing, resolved, not_met, accumulating, insufficient_evidence, no_reference

Ciclo de vida: una alerta se abre (status=open) al cumplirse la regla, se extiende
mientras la condición siga cumpliéndose y se resuelve (status=resolved) en la primera
ventana ELEGIBLE que no la cumple. Una ventana insuficiente no abre, no extiende y no
resuelve alertas de confianza, ni reinicia la racha de la regla sostenida.
"""


def window_state(win: dict, wcfg: dict) -> str:
    ok = win["n_valid"] >= wcfg["min_frames"] and win["n_dets"] >= wcfg["min_detections"]
    return "eligible" if ok else "insufficient"


class RuleEngine:
    def __init__(self, rules: list[dict], reference: dict | None):
        self.rules = {r["rule_id"]: r for r in rules}
        self.reference = reference
        self.open: dict[str, dict] = {}     # rule_id -> alerta abierta
        self.streak: dict[str, list] = {}   # rule_id -> ventanas consecutivas que cumplen
        self.n_alerts = 0

    @property
    def active_count(self) -> int:
        return len(self.open)

    def evaluate(self, win: dict) -> tuple[list[dict], list[dict], list[dict]]:
        """Devuelve (evaluaciones, alertas_nuevas, alertas_actualizadas)."""
        evals, new, updated = [], [], []
        for rid, rule in self.rules.items():
            outcome, observed, met = self._check(rid, rule, win)
            alert = self.open.get(rid)
            if met is None:  # evidencia insuficiente o sin referencia: no cambia el estado
                pass
            elif met:
                streak = self.streak.setdefault(rid, [])
                streak.append(win)
                need = rule["persistence_windows"]
                if alert:
                    outcome = "continuing"
                    alert["last_window_id"] = win["window_id"]
                    alert["n_windows"] += 1
                    alert["window_ids"].append(win["window_id"])
                    alert["event_ids"].extend(win["event_ids"])
                    alert["observed"]["windows"].append(observed)
                    updated.append(alert)
                elif len(streak) >= need:
                    outcome = "fired"
                    alert = self._open(rid, rule, win, streak[-need:], observed)
                    new.append(alert)
                else:
                    outcome = "accumulating"
                    observed["streak"] = f"{len(streak)}/{need}"
            else:
                self.streak[rid] = []
                if alert:
                    outcome = "resolved"
                    alert["status"] = "resolved"
                    alert["resolved_at"] = win["end_at"]
                    alert["observed"]["resolved_by"] = {"window_id": win["window_id"], **observed}
                    del self.open[rid]
                    updated.append(alert)
                else:
                    outcome = "not_met"
            evals.append({"rule_id": rid, "outcome": outcome, "observed": observed,
                          "alert_id": alert["alert_id"] if alert else None})
        return evals, new, updated

    def _check(self, rid: str, rule: dict, win: dict):
        """(outcome provisional, observado, cumple: True/False/None=no evaluable)."""
        state = win["state"]
        obs = {"window_id": win["window_id"], "state": state, "n_valid": win["n_valid"],
               "n_dets": win["n_dets"], "n_low": win["n_low"], "low_prop": win["low_prop"]}
        if rule["metric"] == "window_state":
            if state == "insufficient":
                return "accumulating", obs, True
            return "not_met", obs, False
        if state == "insufficient":
            return "insufficient_evidence", obs, None
        if rule["metric"] == "low_prop":
            return None, obs, win["low_prop"] >= rule["threshold"]
        if rule["metric"] == "low_prop_delta":
            if not self.reference:
                return "no_reference", obs, None
            ref = self.reference["low_prop"]
            obs["ref_low_prop"] = ref
            obs["delta"] = round(win["low_prop"] - ref, 6)
            return None, obs, obs["delta"] >= rule["threshold"]
        raise ValueError(f"métrica de regla desconocida: {rule['metric']}")

    def _open(self, rid, rule, win, wins, observed) -> dict:
        self.n_alerts += 1
        run_id = win["run_id"]
        alert = {
            "alert_id": f"{run_id}-a{self.n_alerts:02d}",
            "run_id": run_id,
            "rule_id": rid,
            "severity": rule["severity"],
            "status": "open",
            "opened_at": win["end_at"],
            "resolved_at": None,
            "first_window_id": wins[0]["window_id"],
            "last_window_id": win["window_id"],
            "n_windows": len(wins),
            "config_ref": win["config_ref"],
            "condition": rule["condition"],
            "reason": self._reason(rid, rule, wins, observed),
            "suggested_action": rule["suggested_action"].strip(),
            "observed": {"windows": [self._obs(w) for w in wins[:-1]] + [observed]},
            "window_ids": [w["window_id"] for w in wins],
            "event_ids": [e for w in wins for e in w["event_ids"]],
            "image_refs": [],
        }
        self.open[rid] = alert
        return alert

    def _obs(self, w):
        o = {"window_id": w["window_id"], "state": w["state"], "n_valid": w["n_valid"],
             "n_dets": w["n_dets"], "n_low": w["n_low"], "low_prop": w["low_prop"]}
        if self.reference:
            o["ref_low_prop"] = self.reference["low_prop"]
            o["delta"] = round(w["low_prop"] - self.reference["low_prop"], 6) if w["low_prop"] is not None else None
        return o

    def _reason(self, rid, rule, wins, observed) -> str:
        w = wins[-1]
        if rule["metric"] == "low_prop":
            return (f"Proporción de baja confianza {w['low_prop']:.3f} ({w['n_low']}/{w['n_dets']} "
                    f"detecciones con s < umbral inferior) >= {rule['threshold']} en la ventana "
                    f"{w['window_id']}.")
        if rule["metric"] == "low_prop_delta":
            deltas = ", ".join(f"{x['low_prop'] - self.reference['low_prop']:+.3f}" for x in wins)
            return (f"La proporción de baja confianza superó la referencia "
                    f"({self.reference['low_prop']:.3f}) en >= {rule['threshold']} durante "
                    f"{len(wins)} ventanas elegibles consecutivas (deltas: {deltas}).")
        return (f"{len(wins)} ventanas consecutivas con evidencia insuficiente "
                f"(último: {w['n_valid']} frames válidos, {w['n_dets']} detecciones); "
                f"no es posible evaluar la confianza.")
