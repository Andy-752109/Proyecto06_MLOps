# Recálculo independiente · `c2-baja-confianza-20261112T162525Z`

Comando: `python scripts/recalc_metrics.py --run-id c2-baja-confianza-20261112T162525Z`
Commit de la ejecución: `872e7c58a97e8f5eb46e80b8afaeb1fa467429e2` · configuración `cfg-517d02606b3e`

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
  "detections": 841,
  "by_zone": {
    "low": 510,
    "doubt": 317,
    "accepted": 14
  },
  "low_prop_run": 0.6064209274673008,
  "inference_ms_p50": 37.506,
  "inference_ms_p95": 48.745,
  "frames_without_detections": 3,
  "errors": 0,
  "source_gaps": 0,
  "captures": 82
}
```

## Métricas base por ventana (recalculadas)

| window_id | state | n_valid | n_dets | n_low | g1_inference_ms_p95 | g2_processing_fps | g3_rss_mb_max | g4_low_conf_prop | g5_trace_coverage | g6_model_version_match | g7_active_alerts |
|---|---|---|---|---|---|---|---|---|---|---|---|
| c2-baja-confianza-20261112T162525Z-w000 | eligible | 20 | 34 | 22 | 43.9820 | 5.9449 | 435.9220 | 0.6471 | 1.0000 | 1.0000 | 1 |
| c2-baja-confianza-20261112T162525Z-w001 | eligible | 20 | 62 | 33 | 50.6890 | 4.9777 | 436.2190 | 0.5323 | 1.0000 | 1.0000 | 1 |
| c2-baja-confianza-20261112T162525Z-w002 | eligible | 20 | 72 | 42 | 49.2640 | 4.9751 | 217.4840 | 0.5833 | 1.0000 | 1.0000 | 2 |
| c2-baja-confianza-20261112T162525Z-w003 | eligible | 20 | 76 | 22 | 49.4490 | 4.9934 | 232.6560 | 0.2895 | 1.0000 | 1.0000 | 0 |
| c2-baja-confianza-20261112T162525Z-w004 | eligible | 20 | 70 | 43 | 44.9880 | 5.0211 | 233.6720 | 0.6143 | 1.0000 | 1.0000 | 1 |
| c2-baja-confianza-20261112T162525Z-w005 | eligible | 20 | 97 | 68 | 43.6710 | 5.0000 | 223.2340 | 0.7010 | 1.0000 | 1.0000 | 1 |
| c2-baja-confianza-20261112T162525Z-w006 | eligible | 20 | 98 | 71 | 44.2560 | 5.0040 | 239.7030 | 0.7245 | 1.0000 | 1.0000 | 2 |
| c2-baja-confianza-20261112T162525Z-w007 | eligible | 20 | 124 | 84 | 44.2440 | 4.9961 | 240.0470 | 0.6774 | 1.0000 | 1.0000 | 2 |
| c2-baja-confianza-20261112T162525Z-w008 | eligible | 20 | 123 | 75 | 45.5490 | 5.0053 | 230.2500 | 0.6098 | 1.0000 | 1.0000 | 2 |
| c2-baja-confianza-20261112T162525Z-w009 | eligible | 18 | 85 | 50 | 48.7450 | 4.9941 | 229.8910 | 0.5882 | 1.0000 | 1.0000 | 2 |
