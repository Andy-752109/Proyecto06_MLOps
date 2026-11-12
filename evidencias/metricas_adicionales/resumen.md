# Métricas adicionales M1–M3

Generado con `python scripts/extra_metrics.py --run-id reference-20261112T162358Z --run-id c1-normal-20261112T162444Z --run-id c2-baja-confianza-20261112T162525Z --run-id s1-interrupcion-20261112T175603Z --run-id s2-cambio-sostenido-20261112T181053Z --run-id s3-error-inferencia-20261112T205403Z`.
Definiciones: [`docs/metricas-adicionales.md`](../../docs/metricas-adicionales.md). Recálculo independiente: [`recalculo.md`](recalculo.md).

**Expectativas: 17 · fallas: 0**

| Métrica | Expectativa | Esperado | Observado | Resultado |
|---|---|---|---|---|
| m1_e2e_ms_p95 | reference-20261112T162358Z: e2e ≥ cola + inferencia en cada evento válido | 0 | 0 | ok |
| m2_delivery_ratio | reference-20261112T162358Z: sin corte ni saturación → entrega 1.0 en todas las ventanas | todas 1.0 | [1.0] | ok |
| m1_e2e_ms_p95 | c1-normal-20261112T162444Z: e2e ≥ cola + inferencia en cada evento válido | 0 | 0 | ok |
| m2_delivery_ratio | c1-normal-20261112T162444Z: sin corte ni saturación → entrega 1.0 en todas las ventanas | todas 1.0 | [1.0] | ok |
| m1_e2e_ms_p95 | c2-baja-confianza-20261112T162525Z: e2e ≥ cola + inferencia en cada evento válido | 0 | 0 | ok |
| m2_delivery_ratio | c2-baja-confianza-20261112T162525Z: sin corte ni saturación → entrega 1.0 en todas las ventanas | todas 1.0 | [1.0] | ok |
| m1_e2e_ms_p95 | s1-interrupcion-20261112T175603Z: e2e ≥ cola + inferencia en cada evento válido | 0 | 0 | ok |
| m2_delivery_ratio | s1-interrupcion-20261112T175603Z: pérdida por saltos = huecos del watchdog (± 1) | 80 | 80.0 | ok |
| m2_delivery_ratio | s1-interrupcion-20261112T175603Z: pérdida por saltos = frames del corte / muestreo (± 1) | 79.5 | 80.0 | ok |
| m1_e2e_ms_p95 | s2-cambio-sostenido-20261112T181053Z: e2e ≥ cola + inferencia en cada evento válido | 0 | 0 | ok |
| m2_delivery_ratio | s2-cambio-sostenido-20261112T181053Z: sin corte ni saturación → entrega 1.0 en todas las ventanas | todas 1.0 | [1.0] | ok |
| m1_e2e_ms_p95 | s3-error-inferencia-20261112T205403Z: e2e ≥ cola + inferencia en cada evento válido | 0 | 0 | ok |
| m2_delivery_ratio | s3-error-inferencia-20261112T205403Z: sin corte ni saturación → entrega 1.0 en todas las ventanas | todas 1.0 | [1.0] | ok |
| m2_delivery_ratio | s3-error-inferencia-20261112T205403Z: con 50 errores de inferencia la entrega sigue en 1.0 | 1.0 también en las ventanas con errores | [1.0] | ok |
| m1_e2e_ms_p95 | s3-error-inferencia-20261112T205403Z: ventanas solo con errores → M1 sin datos (no 0) | no_data | ['no_data'] | ok |
| m3_score_psi | s2-cambio-sostenido-20261112T181053Z: PSI mínimo de ventanas desenfocadas > PSI máximo de ventanas normales | > 0.549 | 4.062 | ok |
| m3_score_psi | variación propia de la referencia (sus ventanas contra su histograma agregado) | documentada | 0.073–0.254 | ok |

## `reference-20261112T162358Z`

| Ventana | M1 e2e p95 (ms) | cola p50 | inferencia p50 | M2 entrega | perdidos | M3 PSI | n dets |
|---|---|---|---|---|---|---|---|
| w000 | 535.4 | 0.1 | 32.3 | 1.000 | 0 | 0.088 | 97 |
| w001 | 46.1 | 0.1 | 41.5 | 1.000 | 0 | 0.111 | 134 |
| w002 | 44.4 | 0.1 | 35.8 | 1.000 | 0 | 0.254 | 149 |
| w003 | 45.1 | 0.1 | 36.2 | 1.000 | 0 | 0.192 | 183 |
| w004 | 45.5 | 0.1 | 37.0 | 1.000 | 0 | 0.135 | 156 |
| w005 | 46.2 | 0.1 | 37.5 | 1.000 | 0 | 0.149 | 157 |
| w006 | 46.6 | 0.1 | 37.6 | 1.000 | 0 | 0.175 | 183 |
| w007 | 44.5 | 0.1 | 41.5 | 1.000 | 0 | 0.073 | 144 |
| w008 | 43.8 | 0.1 | 31.1 | 1.000 | 0 | 0.200 | 126 |
| w009 | 45.3 | 0.1 | 42.5 | 1.000 | 0 | 0.150 | 117 |

## `c1-normal-20261112T162444Z`

| Ventana | M1 e2e p95 (ms) | cola p50 | inferencia p50 | M2 entrega | perdidos | M3 PSI | n dets |
|---|---|---|---|---|---|---|---|
| w000 | 421.9 | 0.1 | 29.0 | 1.000 | 0 | 0.539 | 61 |
| w001 | 50.2 | 0.1 | 39.8 | 1.000 | 0 | 0.549 | 77 |
| w002 | 49.6 | 0.1 | 43.3 | 1.000 | 0 | 0.197 | 110 |
| w003 | 45.1 | 0.1 | 37.4 | 1.000 | 0 | 0.839 | 116 |
| w004 | 45.3 | 0.1 | 34.9 | 1.000 | 0 | 0.613 | 128 |
| w005 | 44.3 | 0.1 | 39.6 | 1.000 | 0 | 0.375 | 136 |
| w006 | 46.3 | 0.1 | 31.5 | 1.000 | 0 | 0.677 | 137 |
| w007 | 46.0 | 0.1 | 41.8 | 1.000 | 0 | 0.087 | 163 |
| w008 | 44.8 | 0.1 | 35.1 | 1.000 | 0 | 0.254 | 158 |
| w009 | 47.9 | 0.1 | 40.4 | 1.000 | 0 | 0.105 | 134 |

## `c2-baja-confianza-20261112T162525Z`

| Ventana | M1 e2e p95 (ms) | cola p50 | inferencia p50 | M2 entrega | perdidos | M3 PSI | n dets |
|---|---|---|---|---|---|---|---|
| w000 | 472.6 | 0.1 | 32.6 | 1.000 | 0 | 4.368 | 34 |
| w001 | 50.9 | 0.1 | 34.8 | 1.000 | 0 | 4.989 | 62 |
| w002 | 49.4 | 0.1 | 41.5 | 1.000 | 0 | 5.215 | 72 |
| w003 | 49.5 | 0.1 | 31.2 | 1.000 | 0 | 4.062 | 76 |
| w004 | 45.2 | 0.1 | 37.8 | 1.000 | 0 | 6.640 | 70 |
| w005 | 43.8 | 0.1 | 30.5 | 1.000 | 0 | 4.947 | 97 |
| w006 | 44.4 | 0.1 | 39.1 | 1.000 | 0 | 7.169 | 98 |
| w007 | 44.4 | 0.1 | 39.4 | 1.000 | 0 | 7.344 | 124 |
| w008 | 45.7 | 0.1 | 36.5 | 1.000 | 0 | 7.268 | 123 |
| w009 | 48.9 | 0.1 | 40.1 | 1.000 | 0 | 5.547 | 85 |

## `s1-interrupcion-20261112T175603Z`

| Ventana | M1 e2e p95 (ms) | cola p50 | inferencia p50 | M2 entrega | perdidos | M3 PSI | n dets |
|---|---|---|---|---|---|---|---|
| w000 | 531.9 | 0.1 | 43.9 | 1.000 | 0 | 0.539 | 61 |
| w001 | 46.1 | 0.1 | 43.5 | 1.000 | 0 | 0.549 | 77 |
| w002 | 45.9 | 0.1 | 43.1 | 1.000 | 0 | — (insufficient) | 44 |
| w003 | — | — | — | — (no_data) | 0 | — (no_data) | 0 |
| w004 | — | — | — | — (no_data) | 0 | — (no_data) | 0 |
| w005 | — | — | — | — (no_data) | 0 | — (no_data) | 0 |
| w006 | 46.5 | 0.1 | 44.5 | 0.111 | 80 | — (insufficient) | 71 |
| w007 | 46.1 | 0.1 | 43.5 | 1.000 | 0 | 0.087 | 163 |
| w008 | 44.9 | 0.1 | 43.5 | 1.000 | 0 | 0.254 | 158 |
| w009 | 46.1 | 0.1 | 42.6 | 1.000 | 0 | 0.105 | 134 |

## `s2-cambio-sostenido-20261112T181053Z`

| Ventana | M1 e2e p95 (ms) | cola p50 | inferencia p50 | M2 entrega | perdidos | M3 PSI | n dets |
|---|---|---|---|---|---|---|---|
| w000 | 478.2 | 0.1 | 42.0 | 1.000 | 0 | 0.539 | 61 |
| w001 | 42.9 | 0.1 | 41.8 | 1.000 | 0 | 0.549 | 77 |
| w002 | 43.6 | 0.1 | 41.4 | 1.000 | 0 | 5.215 | 72 |
| w003 | 44.5 | 0.1 | 41.7 | 1.000 | 0 | 4.062 | 76 |
| w004 | 42.9 | 0.1 | 41.6 | 1.000 | 0 | 6.640 | 70 |
| w005 | 42.8 | 0.1 | 41.9 | 1.000 | 0 | 4.947 | 97 |
| w006 | 43.7 | 0.1 | 41.8 | 1.000 | 0 | 7.169 | 98 |
| w007 | 43.8 | 0.1 | 41.8 | 1.000 | 0 | 7.344 | 124 |
| w008 | 43.8 | 0.1 | 41.9 | 1.000 | 0 | 0.254 | 158 |
| w009 | 44.3 | 0.1 | 41.9 | 1.000 | 0 | 0.105 | 134 |

## `s3-error-inferencia-20261112T205403Z`

| Ventana | M1 e2e p95 (ms) | cola p50 | inferencia p50 | M2 entrega | perdidos | M3 PSI | n dets |
|---|---|---|---|---|---|---|---|
| w000 | 565.8 | 0.1 | 33.9 | 1.000 | 0 | 0.539 | 61 |
| w001 | 46.2 | 0.1 | 35.6 | 1.000 | 0 | 0.549 | 77 |
| w002 | 46.9 | 0.1 | 36.6 | 1.000 | 0 | — (insufficient) | 44 |
| w003 | — | — | — | 1.000 | 0 | — (no_data) | 0 |
| w004 | — | — | — | 1.000 | 0 | — (no_data) | 0 |
| w005 | 48.1 | 0.1 | 39.5 | 1.000 | 0 | 0.375 | 136 |
| w006 | 47.8 | 0.1 | 35.7 | 1.000 | 0 | 0.677 | 137 |
| w007 | 45.8 | 0.1 | 38.0 | 1.000 | 0 | 0.087 | 163 |
| w008 | 45.4 | 0.1 | 35.9 | 1.000 | 0 | 0.254 | 158 |
| w009 | 46.4 | 0.1 | 37.3 | 1.000 | 0 | 0.105 | 134 |
