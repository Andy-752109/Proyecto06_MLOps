"""Recorrido completo: fuente -> inferencia -> evento -> captura -> ventana -> reglas -> alertas.

Uso:  python -m monitor.pipeline --scenario c1-normal
"""
import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
import psutil

from .config import ROOT, config_snapshot, load_config, load_reference, load_scenario
from .detector import PersonDetector, file_sha256
from .metrics import VALID, compute_window_metrics
from .policy import frame_summary
from .rules import RuleEngine, window_state
from .source import SourceGap, VideoStreamSource, utc_now
from .store import RunStore, connect


def git_info() -> tuple[str | None, bool | None]:
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                         stderr=subprocess.DEVNULL, text=True).strip()
        dirty = bool(subprocess.check_output(
            ["git", "status", "--porcelain", "--", "src", "config", "scripts", "modelo"],
            cwd=ROOT, text=True).strip())
        return commit, dirty
    except Exception:
        return None, None


class Monitor:
    def __init__(self, scenario: str, run_id: str | None = None, max_frames: int | None = None):
        self.cfg = load_config()
        self.sc = load_scenario(scenario)
        self.max_frames = max_frames
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.run_id = run_id or f"{scenario}-{stamp}"
        self.run_dir = ROOT / self.cfg["storage"]["runs_dir"] / self.run_id
        if self.run_dir.exists():
            sys.exit(f"ya existe {self.run_dir}; las ejecuciones no se sobrescriben")
        self.reference = load_reference(self.cfg) if self.sc["evaluate_rules"] else None
        if self.sc["evaluate_rules"] and self.reference is None:
            sys.exit("falta config/reference.json: ejecuta primero el escenario 'reference' "
                     "y scripts/build_reference.py")
        self.con = connect(ROOT / self.cfg["storage"]["db"])
        self.store = RunStore(self.con, self.run_dir)
        self.detector = PersonDetector(self.cfg["model"], ROOT)
        if self.detector.sha256 != self.cfg["model"]["sha256"]:
            print("AVISO: el SHA-256 del modelo cargado no coincide con el configurado")
        self.engine = RuleEngine(self.cfg["alerts"], self.reference) if self.sc["evaluate_rules"] else None
        self.proc = psutil.Process(os.getpid())
        self.proc.cpu_percent(None)
        self.known_configs = {self.cfg["config_ref"]}
        self.seq = 0
        self.win_idx = 0
        self.win_events: list[dict] = []
        self.win_dets: list[dict] = []
        self.win_res: list[dict] = []
        self.last_image = None
        self.last_flagged_seq = -10**9
        self.alerts: dict[str, dict] = {}
        self.windows: list[dict] = []
        self.all_events: list[dict] = []  # eventos de ventanas cerradas

    # ---------------------------------------------------------------- run
    def run(self) -> dict:
        cfg, sc = self.cfg, self.sc
        src_path = ROOT / sc["source"]["path"]
        src_sha = file_sha256(src_path)
        if sc["source"].get("sha256") and src_sha != sc["source"]["sha256"]:
            sys.exit(f"SHA-256 de la fuente no coincide: {src_sha}")
        sw = sc["source"].get("switch")
        if sw and file_sha256(ROOT / sw["path"]) != sw["sha256"]:
            sys.exit(f"SHA-256 de {sw['path']} no coincide")
        commit, dirty = git_info()
        snap = config_snapshot(cfg)
        self.con.execute("INSERT OR IGNORE INTO configs VALUES (?,?,?)",
                         (cfg["config_ref"], json.dumps(snap, ensure_ascii=False), utc_now()))
        ref_path = ROOT / cfg["reference"]["path"]
        self.manifest = {
            "run_id": self.run_id, "scenario": sc["name"], "description": sc["description"],
            "started_at": utc_now(), "command": " ".join(shlex.quote(a) for a in sys.argv),
            "git_commit": commit, "git_dirty": dirty,
            "config_ref": cfg["config_ref"], "config_file": "config/monitor.yaml",
            "source_ref": sc["source_ref"], "source": sc["source"], "source_sha256": src_sha,
            "model_ref": self.detector.model_ref, "model_sha256": self.detector.sha256,
            "model_version": cfg["model"]["version"], "environment": self.detector.environment,
            "evaluate_rules": sc["evaluate_rules"],
            "reference": ({"path": cfg["reference"]["path"], "sha256": file_sha256(ref_path),
                           "low_prop": self.reference["low_prop"]} if self.reference else None),
        }
        self.con.execute(
            "INSERT INTO runs (run_id, scenario, description, started_at, status, config_ref, "
            "source_ref, source_id, source_json, model_ref, model_sha256, environment_json, "
            "git_commit, git_dirty, command) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (self.run_id, sc["name"], sc["description"], self.manifest["started_at"], "running",
             cfg["config_ref"], sc["source_ref"], sc["source"]["source_id"],
             json.dumps(sc["source"]), self.detector.model_ref, self.detector.sha256,
             json.dumps(self.detector.environment), commit, int(bool(dirty)),
             self.manifest["command"]))
        (self.run_dir / "config.snapshot.json").write_text(
            json.dumps({"config_ref": cfg["config_ref"], **snap}, indent=2, ensure_ascii=False))
        self.store.commit()
        print(f"run {self.run_id} · {cfg['config_ref']} · {self.detector.model_ref} · fuente {src_path.name}")

        source = VideoStreamSource(sc["source"], ROOT).start()
        t0 = time.perf_counter()
        for frame in source.frames():
            self._process(frame)
            if len(self.win_events) >= cfg["windows"]["size_frames"]:
                self._close_window()
            if self.max_frames and self.seq >= self.max_frames:
                source.stop()
        if self.win_events:
            self._close_window()
        elapsed = time.perf_counter() - t0
        return self._finish(source, elapsed)

    # ---------------------------------------------------------- per frame
    def _process_gap(self, gap: SourceGap) -> None:
        """Frame esperado que no llegó: evento sin frame, sin inferencia y sin puntuación."""
        seq = self.seq
        self.seq += 1
        event_id = f"{self.run_id}-e{seq:05d}"
        wd = self.sc["source"]["watchdog"]["gap_after_s"]
        self.win_events.append({
            "event_id": event_id, "run_id": self.run_id, "seq": seq,
            "frame_id": None, "frame_index": None, "pts_s": None,
            "window_id": f"{self.run_id}-w{self.win_idx:03d}",
            "captured_at": gap.detected_at, "inferred_at": gap.detected_at,
            "source_id": self.sc["source"]["source_id"], "task": "detection",
            "model_ref": self.detector.model_ref, "model_sha256": None,
            "config_ref": self.cfg["config_ref"], "status": "source_gap",
            "error": f"sin frames de la fuente durante {gap.silent_s:.1f} s "
                     f"(watchdog {wd} s; hueco {gap.slot} de este silencio)",
            "n_detections": 0, "n_low": 0, "n_doubt": 0, "n_accepted": 0,
            "max_score": None, "frame_zone": None,
            "inference_ms": None, "queue_ms": None, "e2e_ms": None,
            "image_ref": None, "capture_reason": None, "detections": [],
        })
        mem = self.proc.memory_info().rss / 2**20
        self.win_res.append({"run_id": self.run_id, "seq": seq, "event_id": event_id,
                             "ts": utc_now(), "rss_mb": round(mem, 3),
                             "cpu_percent": self.proc.cpu_percent(None)})

    def _process(self, frame) -> None:
        if isinstance(frame, SourceGap):
            return self._process_gap(frame)
        cfg = self.cfg
        dequeued = time.perf_counter()
        seq = self.seq
        self.seq += 1
        event_id = f"{self.run_id}-e{seq:05d}"
        status, error, dets, inf_ms = "ok", None, [], None
        try:
            dets, inf_ms = self.detector.predict(frame.image)
            if not dets:
                status = "no_detections"
        except Exception as exc:  # fallo técnico: estado aparte, sin puntuación
            status, error = "error", f"{type(exc).__name__}: {exc}"
        done = time.perf_counter()
        summ = frame_summary(dets, cfg["policy"]["lower"], cfg["policy"]["upper"])
        if status == "error":
            summ.update(n_detections=0, max_score=None, frame_zone=None)

        reason = self._capture_reason(seq, status, summ["frame_zone"])
        image_ref = None
        if reason:
            image_ref = self._save_image(event_id, frame.image)
        self.last_image = (event_id, frame.image)

        window_id = f"{self.run_id}-w{self.win_idx:03d}"
        for rank, d in enumerate(dets):
            d["det_id"] = f"{event_id}-d{rank:02d}"
        ev = {
            "event_id": event_id, "run_id": self.run_id, "seq": seq,
            "frame_id": f"{self.sc['source']['source_id']}-f{frame.frame_index:05d}",
            "frame_index": frame.frame_index, "pts_s": round(frame.pts_s, 3),
            "window_id": window_id, "captured_at": frame.captured_at, "inferred_at": utc_now(),
            "source_id": self.sc["source"]["source_id"], "task": "detection",
            "model_ref": self.detector.model_ref, "model_sha256": self.detector.sha256,
            "config_ref": cfg["config_ref"], "status": status, "error": error,
            **summ,
            "inference_ms": None if inf_ms is None else round(inf_ms, 3),
            "queue_ms": round((dequeued - frame.captured_mono) * 1000, 3),
            "e2e_ms": round((done - frame.captured_mono) * 1000, 3),
            "image_ref": image_ref, "capture_reason": reason,
            "detections": dets,
        }
        self.win_events.append(ev)
        for rank, d in enumerate(dets):
            x1, y1, x2, y2 = d["bbox_xyxy"]
            self.win_dets.append({
                "det_id": d["det_id"], "event_id": event_id, "run_id": self.run_id, "rank": rank,
                "class_id": d["class_id"], "class_name": d["class_name"], "score": d["score"],
                "zone": d["zone"], "x1": x1, "y1": y1, "x2": x2, "y2": y2})
        mem = self.proc.memory_info().rss / 2**20
        self.win_res.append({"run_id": self.run_id, "seq": seq, "event_id": event_id,
                             "ts": utc_now(), "rss_mb": round(mem, 3),
                             "cpu_percent": self.proc.cpu_percent(None)})

    def _capture_reason(self, seq: int, status: str, frame_zone: str | None) -> str | None:
        cap = self.cfg["capture"]
        flagged = {"error": "error", "no_detections": "sin_detecciones"}.get(status) or \
            {"low": "baja_confianza", "doubt": "duda"}.get(frame_zone)
        if flagged and seq - self.last_flagged_seq >= cap["flagged_min_gap"]:
            self.last_flagged_seq = seq
            return flagged
        if seq % cap["normal_sample_every"] == 0:
            return "muestra_normal"
        return None

    def _save_image(self, event_id: str, image) -> str:
        path = self.run_dir / "capturas" / f"{event_id}.jpg"
        cv2.imwrite(str(path), image, [cv2.IMWRITE_JPEG_QUALITY, self.cfg["capture"]["jpeg_quality"]])
        return str(path.relative_to(ROOT))

    # --------------------------------------------------------- per window
    def _close_window(self) -> None:
        evs = self.win_events
        valid = [e for e in evs if e["status"] in VALID]
        win = {
            "window_id": evs[0]["window_id"], "run_id": self.run_id, "idx": self.win_idx,
            "first_seq": evs[0]["seq"], "last_seq": evs[-1]["seq"],
            "start_at": evs[0]["captured_at"], "end_at": evs[-1]["inferred_at"],
            "n_events": len(evs),
            "n_ok": sum(e["status"] == "ok" for e in evs),
            "n_no_detections": sum(e["status"] == "no_detections" for e in evs),
            "n_errors": sum(e["status"] == "error" for e in evs),
            "n_valid": len(valid),
            "n_dets": sum(e["n_detections"] for e in valid),
            "n_low": sum(e["n_low"] for e in valid),
            "n_doubt": sum(e["n_doubt"] for e in valid),
            "n_accepted": sum(e["n_accepted"] for e in valid),
            "config_ref": self.cfg["config_ref"],
            "event_ids": [e["event_id"] for e in evs],
        }
        win["low_prop"] = round(win["n_low"] / win["n_dets"], 6) if win["n_dets"] else None
        win["state"] = window_state(win, self.cfg["windows"])

        evals = []
        if self.engine:
            evals, new, updated = self.engine.evaluate(win)
            for a in new:
                last = evs[-1]
                # un hueco de la fuente no tiene imagen: no se adjunta un frame anterior
                if self.cfg["capture"]["on_alert"] and not last["image_ref"] \
                        and last["status"] != "source_gap":
                    last["image_ref"] = self._save_image(last["event_id"], self.last_image[1])
                    last["capture_reason"] = "alerta"
            for a in new + updated:
                ids = set(a["event_ids"])
                a["model_ref"] = self.detector.model_ref
                a["source_id"] = self.sc["source"]["source_id"]
                a["image_refs"] = sorted({e["image_ref"] for e in self.all_events + evs
                                          if e["event_id"] in ids and e["image_ref"]})
                self.alerts[a["alert_id"]] = a
                self.store.insert("alerts", {k: v for k, v in a.items()}, replace=True)

        for e in evs:
            self.store.insert("events", e)
        for d in self.win_dets:
            self.store.insert("detections", d)
        for r in self.win_res:
            self.store.insert("resource_samples", r)
        self.store.insert("windows", win)
        self.windows.append(win)

        mets = compute_window_metrics(
            evs, self.win_res, self.cfg["model"]["sha256"], self.known_configs,
            self.engine.active_count if self.engine else 0, self.cfg["windows"], ROOT)
        for mid, m in mets.items():
            self.store.insert("metric_values", {
                "run_id": self.run_id, "window_id": win["window_id"], "metric_id": mid,
                "grp": m["grp"], "value": m["value"], "unit": m["unit"], "n_obs": m["n_obs"],
                "status": m["status"], "detail": m["detail"]})
        for ev in evals:
            self.store.insert("rule_evaluations", {
                "run_id": self.run_id, "window_id": win["window_id"], **ev})
        self.store.commit()

        fired = [e["rule_id"] + ":" + e["outcome"] for e in evals if e["outcome"] in ("fired", "resolved")]
        lp = "—" if win["low_prop"] is None else f"{win['low_prop']:.3f}"
        print(f"  {win['window_id']}  frames={win['n_events']:2d} dets={win['n_dets']:3d} "
              f"low_prop={lp} {win['state']:<12s} {' '.join(fired)}")
        self.all_events.extend(evs)
        self.win_idx += 1
        self.win_events, self.win_dets, self.win_res = [], [], []

    # ------------------------------------------------------------- finish
    def _finish(self, source, elapsed: float) -> dict:
        st = source.stats
        evs = self.all_events
        valid = [e for e in evs if e["status"] in VALID]
        n_dets = sum(e["n_detections"] for e in valid)
        summary = {
            "elapsed_s": round(elapsed, 3),
            "source": {"native_fps": st.native_fps, "frames_read": st.read,
                       "read_failures": st.read_failures, "frames_selected": st.selected,
                       "dropped": st.dropped,
                       **({"gaps": st.gaps, "events": len(st.events)} if st.events or st.gaps else {})},
            "events": len(evs),
            "by_status": {s: sum(e["status"] == s for e in evs)
                          for s in ("ok", "no_detections", "error") + (("source_gap",) if st.gaps else ())},
            "detections": n_dets,
            "by_zone": {z: sum(e[f"n_{z}"] for e in valid) for z in ("low", "doubt", "accepted")},
            "low_prop_run": round(sum(e["n_low"] for e in valid) / n_dets, 6) if n_dets else None,
            "captures": sum(1 for e in evs if e["image_ref"]),
            "capture_reasons": {r: sum(e["capture_reason"] == r for e in evs)
                                for r in sorted({e["capture_reason"] for e in evs if e["capture_reason"]})},
            "windows": len(self.windows),
            "windows_by_state": {s: sum(w["state"] == s for w in self.windows)
                                 for s in ("eligible", "insufficient")},
            "alerts": [{"alert_id": a["alert_id"], "rule_id": a["rule_id"], "status": a["status"],
                        "severity": a["severity"]} for a in self.alerts.values()],
        }
        for i, se in enumerate(st.events):
            self.store.insert("source_events", {"run_id": self.run_id, "seq": i, "ts": se["ts"],
                                                "kind": se["kind"],
                                                "detail": {k: v for k, v in se.items() if k not in ("ts", "kind")}})
        self.manifest.update(ended_at=utc_now(), status="completed", summary=summary)
        self.con.execute("UPDATE runs SET ended_at=?, status=?, summary_json=? WHERE run_id=?",
                         (self.manifest["ended_at"], "completed", json.dumps(summary), self.run_id))
        self.store.dump_alerts(self.run_id)
        self.store.close()
        (self.run_dir / "manifest.json").write_text(json.dumps(self.manifest, indent=2, ensure_ascii=False))
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        print(f"evidencias en {self.run_dir.relative_to(ROOT)}")
        return self.manifest


def main() -> None:
    ap = argparse.ArgumentParser(description="Ejecuta un escenario del centro de monitoreo")
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--run-id")
    ap.add_argument("--max-frames", type=int, help="limita frames procesados (pruebas rápidas)")
    args = ap.parse_args()
    Monitor(args.scenario, args.run_id, args.max_frames).run()


if __name__ == "__main__":
    main()
