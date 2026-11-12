# Recálculo independiente · `s3-error-inferencia-20261112T205403Z`

Comando: `python scripts/recalc_metrics.py --run-id s3-error-inferencia-20261112T205403Z`
Commit de la ejecución: `84b576af13db95ad9c26cba655245eb9d32c5150` · configuración `cfg-517d02606b3e`

Fuentes primarias: `events.jsonl` (puntuaciones crudas de cada detección, tiempos, estados),
`resources.jsonl`, `alerts.jsonl`, `config.snapshot.json`. Las zonas se recalculan desde la
puntuación con los umbrales del snapshot; no se usan los contadores guardados por el monitor.

**Comprobaciones: 114 · diferencias: 0**

Diferencias:
- ninguna

## Totales de la ejecución (recalculados)

```json
{
  "events": 198,
  "valid_frames": 148,
  "detections": 910,
  "by_zone": {
    "accepted": 732,
    "low": 93,
    "doubt": 85
  },
  "low_prop_run": 0.1021978021978022,
  "inference_ms_p50": 37.258,
  "inference_ms_p95": 47.259,
  "frames_without_detections": 0,
  "errors": 50,
  "source_gaps": 0,
  "captures": 36
}
```

## Métricas base por ventana (recalculadas)

| window_id | state | n_valid | n_dets | n_low | g1_inference_ms_p95 | g2_processing_fps | g3_rss_mb_max | g4_low_conf_prop | g5_trace_coverage | g6_model_version_match | g7_active_alerts |
|---|---|---|---|---|---|---|---|---|---|---|---|
| s3-error-inferencia-20261112T205403Z-w000 | eligible | 20 | 61 | 9 | 50.0560 | 6.1389 | 440.7030 | 0.1475 | 1.0000 | 1.0000 | 0 |
| s3-error-inferencia-20261112T205403Z-w001 | eligible | 20 | 77 | 12 | 45.9700 | 5.0066 | 441.3120 | 0.1558 | 1.0000 | 1.0000 | 0 |
| s3-error-inferencia-20261112T205403Z-w002 | insufficient | 10 | 44 | 6 | 46.7250 | 5.0223 | 395.7970 | 0.1364 | 1.0000 | 1.0000 | 0 |
| s3-error-inferencia-20261112T205403Z-w003 | insufficient | 0 | 0 | 0 | — | — | 400.0310 | — | 1.0000 | 1.0000 | 0 |
| s3-error-inferencia-20261112T205403Z-w004 | insufficient | 0 | 0 | 0 | — | — | 400.3280 | — | 1.0000 | 1.0000 | 1 |
| s3-error-inferencia-20261112T205403Z-w005 | eligible | 20 | 136 | 12 | 47.8620 | 5.0053 | 405.5780 | 0.0882 | 1.0000 | 1.0000 | 0 |
| s3-error-inferencia-20261112T205403Z-w006 | eligible | 20 | 137 | 8 | 47.6430 | 4.9908 | 405.7660 | 0.0584 | 1.0000 | 1.0000 | 0 |
| s3-error-inferencia-20261112T205403Z-w007 | eligible | 20 | 163 | 18 | 45.5840 | 4.9816 | 392.4840 | 0.1104 | 1.0000 | 1.0000 | 0 |
| s3-error-inferencia-20261112T205403Z-w008 | eligible | 20 | 158 | 14 | 45.2480 | 4.9830 | 393.7190 | 0.0886 | 1.0000 | 1.0000 | 0 |
| s3-error-inferencia-20261112T205403Z-w009 | eligible | 18 | 134 | 14 | 46.1990 | 5.0074 | 393.8750 | 0.1045 | 1.0000 | 1.0000 | 0 |
