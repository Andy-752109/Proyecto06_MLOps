# Recálculo independiente · `s2-cambio-sostenido-20261112T181053Z`

Comando: `python scripts/recalc_metrics.py --run-id s2-cambio-sostenido-20261112T181053Z`
Commit de la ejecución: `257712f864de4f08e4efeea3a720bc5d89025144` · configuración `cfg-517d02606b3e`

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
  "valid_frames": 198,
  "detections": 967,
  "by_zone": {
    "low": 379,
    "accepted": 358,
    "doubt": 230
  },
  "low_prop_run": 0.39193381592554294,
  "inference_ms_p50": 41.766,
  "inference_ms_p95": 43.687,
  "frames_without_detections": 0,
  "errors": 0,
  "source_gaps": 0,
  "captures": 58
}
```

## Métricas base por ventana (recalculadas)

| window_id | state | n_valid | n_dets | n_low | g1_inference_ms_p95 | g2_processing_fps | g3_rss_mb_max | g4_low_conf_prop | g5_trace_coverage | g6_model_version_match | g7_active_alerts |
|---|---|---|---|---|---|---|---|---|---|---|---|
| s2-cambio-sostenido-20261112T181053Z-w000 | eligible | 20 | 61 | 9 | 43.5900 | 5.9580 | 446.1880 | 0.1475 | 1.0000 | 1.0000 | 0 |
| s2-cambio-sostenido-20261112T181053Z-w001 | eligible | 20 | 77 | 12 | 42.7560 | 5.0040 | 438.5310 | 0.1558 | 1.0000 | 1.0000 | 0 |
| s2-cambio-sostenido-20261112T181053Z-w002 | eligible | 20 | 72 | 42 | 43.4280 | 5.0053 | 442.7810 | 0.5833 | 1.0000 | 1.0000 | 1 |
| s2-cambio-sostenido-20261112T181053Z-w003 | eligible | 20 | 76 | 22 | 44.2690 | 5.0053 | 437.7030 | 0.2895 | 1.0000 | 1.0000 | 0 |
| s2-cambio-sostenido-20261112T181053Z-w004 | eligible | 20 | 70 | 43 | 42.7790 | 5.0265 | 437.8280 | 0.6143 | 1.0000 | 1.0000 | 1 |
| s2-cambio-sostenido-20261112T181053Z-w005 | eligible | 20 | 97 | 68 | 42.6430 | 5.0026 | 438.0470 | 0.7010 | 1.0000 | 1.0000 | 1 |
| s2-cambio-sostenido-20261112T181053Z-w006 | eligible | 20 | 98 | 71 | 43.4840 | 5.0013 | 451.5940 | 0.7245 | 1.0000 | 1.0000 | 2 |
| s2-cambio-sostenido-20261112T181053Z-w007 | eligible | 20 | 124 | 84 | 43.6870 | 5.0013 | 451.7340 | 0.6774 | 1.0000 | 1.0000 | 2 |
| s2-cambio-sostenido-20261112T181053Z-w008 | eligible | 20 | 158 | 14 | 43.6930 | 5.0066 | 455.2810 | 0.0886 | 1.0000 | 1.0000 | 0 |
| s2-cambio-sostenido-20261112T181053Z-w009 | eligible | 18 | 134 | 14 | 44.1470 | 5.0015 | 457.6720 | 0.1045 | 1.0000 | 1.0000 | 0 |
