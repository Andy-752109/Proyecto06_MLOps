"""Construye config/reference.json a partir de una ejecución del escenario 'reference'
y documenta la justificación de umbrales y reglas con esas observaciones.

Uso:  python scripts/build_reference.py --run-id <run_id de reference>

Lee solo los JSONL de la ejecución (datos primarios), no la base SQLite.
Salidas:
  config/reference.json
  evidencias/referencia/justificacion-umbrales.md
"""
import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from monitor.config import ROOT, load_config  # noqa: E402


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def pct(values, p):
    s = sorted(values)
    k = max(1, -(-p * len(s) // 100))  # ceil -> rango más cercano
    return s[int(k) - 1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    args = ap.parse_args()
    cfg = load_config()
    run_dir = ROOT / cfg["storage"]["runs_dir"] / args.run_id
    manifest = json.loads((run_dir / "manifest.json").read_text())
    if manifest["scenario"] != "reference":
        sys.exit("la referencia debe construirse con una ejecución del escenario 'reference'")
    events = read_jsonl(run_dir / "events.jsonl")
    windows = read_jsonl(run_dir / "windows.jsonl")
    valid = [e for e in events if e["status"] in ("ok", "no_detections")]
    scores = [d["score"] for e in valid for d in e["detections"]]
    lo, hi = cfg["policy"]["lower"], cfg["policy"]["upper"]
    wcfg = cfg["windows"]

    hist = {f"[{b/10:.1f},{(b+1)/10:.1f})": sum(b / 10 <= s < (b + 1) / 10 for s in scores)
            for b in range(1, 10)}
    below = {f"{t:.2f}": round(sum(s < t for s in scores) / len(scores), 4)
             for t in (0.20, 0.30, 0.35, 0.40, 0.45, 0.50, 0.60, 0.70, 0.80)}
    n_low = sum(s < lo for s in scores)
    ref_low_prop = n_low / len(scores)
    elig = [w for w in windows if w["state"] == "eligible"]
    wl = [w["low_prop"] for w in elig]
    w_mean, w_sd = statistics.mean(wl), statistics.pstdev(wl)

    reference = {
        "reference_id": f"ref-{args.run_id}",
        "run_id": args.run_id,
        "source": manifest["source"],
        "source_sha256": manifest["source_sha256"],
        "model_ref": manifest["model_ref"],
        "model_sha256": manifest["model_sha256"],
        "config_ref": manifest["config_ref"],
        "git_commit": manifest["git_commit"],
        "unit": "detection",
        "population": "detecciones candidatas (s >= conf_floor tras NMS) en frames con inferencia válida",
        "thresholds": {"lower": lo, "upper": hi},
        "n_frames_valid": len(valid),
        "n_detections": len(scores),
        "n_low": n_low,
        "low_prop": round(ref_low_prop, 6),
        "score_percentiles": {f"p{p}": pct(scores, p) for p in (5, 10, 25, 50, 75, 90, 95)},
        "score_histogram": hist,
        "prop_below": below,
        "windows": {"n": len(windows), "n_eligible": len(elig),
                    "low_prop_mean": round(w_mean, 6), "low_prop_sd": round(w_sd, 6),
                    "low_prop_min": min(wl), "low_prop_max": max(wl)},
    }
    out = ROOT / cfg["reference"]["path"]
    out.write_text(json.dumps(reference, indent=2, ensure_ascii=False) + "\n")
    ref_sha = hashlib.sha256(out.read_bytes()).hexdigest()

    rules = {r["rule_id"]: r for r in cfg["alerts"]}
    low_thr = rules["baja-confianza-v1"]["threshold"]
    d_thr = rules["cambio-sostenido-v1"]["threshold"]
    hist_rows = "\n".join(f"| {k} | {v} | {v/len(scores):.3f} |" for k, v in hist.items())
    below_rows = "\n".join(f"| s < {k} | {v:.3f} |" for k, v in below.items())
    win_rows = "\n".join(f"| {w['window_id']} | {w['n_valid']} | {w['n_dets']} | {w['n_low']} | "
                         f"{w['low_prop']:.3f} | {w['state']} |" for w in windows)
    md = f"""# Referencia y justificación de umbrales

Generado por `scripts/build_reference.py --run-id {args.run_id}` a partir de
`evidencias/runs/{args.run_id}/events.jsonl` y `windows.jsonl` (datos primarios).

- Referencia: `config/reference.json` (SHA-256 `{ref_sha}`)
- Ejecución: `{args.run_id}` · commit `{manifest['git_commit']}` · {manifest['config_ref']}
- Fuente: `{manifest['source']['path']}` frames {manifest['source']['start_frame']}–{manifest['source']['end_frame']} (exclusivo),
  muestreo 1 de cada {manifest['source']['sample_every']} a {manifest['summary']['source']['native_fps']} fps nativos
- Modelo: `{manifest['model_ref']}` · piso de salida {cfg['model']['conf_floor']} · NMS IoU {cfg['model']['nms_iou']} · imgsz {cfg['model']['imgsz']}
- Unidad de análisis: **detección candidata**; población: {reference['population']}.
- Observaciones: {len(valid)} frames válidos, {len(scores)} detecciones, {len(windows)} ventanas de {wcfg['size_frames']} frames.

## Distribución de puntuaciones en la referencia

| Intervalo | Detecciones | Fracción |
|---|---|---|
{hist_rows}

Percentiles (rango más cercano): {", ".join(f"{k}={v:.3f}" for k, v in reference['score_percentiles'].items())}.

| Condición | Fracción de detecciones |
|---|---|
{below_rows}

## Elección de umbrales (fijados antes de C1/C2)

La distribución es **bimodal**: un grupo de candidatas débiles cerca del piso de salida
(0.10–0.30) y la masa principal entre 0.70 y 0.90, con un valle entre ambos.

- **Umbral inferior = {lo}**: cae en el valle. La fracción bajo el umbral casi no cambia
  entre 0.30 y 0.50 ({below['0.30']:.3f} → {below['0.50']:.3f}), así que la zona baja aísla
  las candidatas débiles sin depender del valor exacto.
- **Umbral superior = {hi}**: inicio de la masa principal (p25 = {reference['score_percentiles']['p25']:.3f}).
  En la referencia, {1 - below['0.70']:.3f} de las detecciones son aceptadas por la política.
- Resultado: zona baja {n_low} ({ref_low_prop:.3f}), duda
  {sum(lo <= s < hi for s in scores)}, aceptada {sum(s >= hi for s in scores)}.
- Las zonas describen la puntuación, no aciertos: no hay etiquetas reales.

## Ventanas de la referencia

| Ventana | Frames válidos | Detecciones | Bajas | low_prop | Estado |
|---|---|---|---|---|---|
{win_rows}

Proporción de baja confianza por ventana: media {w_mean:.3f}, desviación {w_sd:.3f},
mínimo {min(wl):.3f}, máximo {max(wl):.3f}.

## Reglas derivadas

- `baja-confianza-v1`: alerta si `low_prop >= {low_thr}` en una ventana elegible.
  {low_thr} es mayor que el máximo de la referencia ({max(wl):.3f}) y que la media + 3σ
  ({w_mean + 3*w_sd:.3f}), así que la operación representativa no la dispara.
- `cambio-sostenido-v1`: alerta si `low_prop - {ref_low_prop:.3f} >= {d_thr}` durante
  3 ventanas elegibles consecutivas. {d_thr} ≈ {d_thr / w_sd:.1f}σ de la variación entre ventanas;
  exigir 3 ventanas (~12 s de stream) evita reaccionar a una sola ventana atípica.
- Mínimos por ventana: {wcfg['min_frames']} frames válidos y {wcfg['min_detections']} detecciones.
  La referencia tiene entre {min(w['n_dets'] for w in windows)} y {max(w['n_dets'] for w in windows)}
  detecciones por ventana. Si no se alcanza el mínimo, la ventana es `insufficient`:
  no se evalúan las reglas de confianza y no se interpreta como normalidad.
"""
    jdir = ROOT / "evidencias/referencia"
    jdir.mkdir(parents=True, exist_ok=True)
    (jdir / "justificacion-umbrales.md").write_text(md)
    print(f"referencia: low_prop={ref_low_prop:.4f} n_dets={len(scores)} -> {out.relative_to(ROOT)}")
    print(f"justificación -> {(jdir / 'justificacion-umbrales.md').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
