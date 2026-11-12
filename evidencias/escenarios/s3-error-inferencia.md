# S3 · Error de inferencia con reacción y recuperación

Ejecución `s3-error-inferencia-20261112T205403Z` · commit `84b576a` (git_dirty=False) ·
`cfg-517d02606b3e` (la misma que C1/C2) · `yolov8n@sha256:f59b3d833e2f` · fuente `src-fd4a1a5a3eeb`.

Generado con `python scripts/verify_s3.py --run-id s3-error-inferencia-20261112T205403Z --c1 c1-normal-20261112T162444Z` a partir de los
JSONL de la ejecución. **21 expectativas, 0 fallas.**

## Entrada y falla inyectada

Tramo de C1 (`vtest.avi`, frames 400–794, ritmo nativo 10 fps, muestreo 1/2). A diferencia de S1,
la fuente entrega todos los frames: lo que falla es la llamada al modelo para los frames
500–599 (`InjectedInferenceError`). Cada evento queda con estado
`error`, el frame y el detalle, sin puntuaciones (no se cuenta como confianza 0).

**Reacción** (`config/monitor.yaml → recovery`): cada 20 errores consecutivos el monitor vuelve a
cargar el modelo desde disco y comprueba su SHA-256. Así distingue un artefacto cambiado o dañado
(que sería un cambio de versión, G6) de un fallo de ejecución. La causa inyectada no depende del
artefacto, por lo que las recargas confirman la identidad pero no lo resuelven; la inferencia
vuelve a responder cuando termina el tramo y se registra `inference_recovered`.

## Línea de tiempo del detector (`source_events.jsonl`)

| # | Momento (UTC) | Tipo | Detalle |
|---|---|---|---|
| 0 | `2026-11-12T20:54:14.137Z` | inference_failed | `{"frame_index": 500, "event_id": "s3-error-inferencia-20261112T205403Z-e00050", "error": "InjectedInferenceError: fallo inyectado en la llamada al modelo (frames 500-599)"}` |
| 1 | `2026-11-12T20:54:17.969Z` | detector_reloaded | `{"frame_index": 538, "after_errors": 20, "load_ms": 32.6, "sha256": "f59b3d833e2f", "sha256_match": true}` |
| 2 | `2026-11-12T20:54:21.971Z` | detector_reloaded | `{"frame_index": 578, "after_errors": 40, "load_ms": 33.8, "sha256": "f59b3d833e2f", "sha256_match": true}` |
| 3 | `2026-11-12T20:54:24.187Z` | inference_recovered | `{"frame_index": 600, "event_id": "s3-error-inferencia-20261112T205403Z-e00100", "consecutive_errors": 50, "reloads": 2, "failing_s": 10.051}` |

## Ventanas (`windows.jsonl`, `metrics.jsonl`, `rule_evaluations.jsonl`)

| Ventana | Eventos | Errores | Frames válidos | Detecciones | low_prop | G1 p95 (ms) | Estado | Reglas |
|---|---|---|---|---|---|---|---|---|
| `w000` | 20 | 0 | 20 | 61 | 0.148 | 50.1 | eligible | — |
| `w001` | 20 | 0 | 20 | 77 | 0.156 | 46.0 | eligible | — |
| `w002` | 20 | 10 | 10 | 44 | 0.136 | 46.7 | insufficient | evidencia-insuficiente-v1: accumulating |
| `w003` | 20 | 20 | 0 | 0 | — | — | insufficient | evidencia-insuficiente-v1: accumulating |
| `w004` | 20 | 20 | 0 | 0 | — | — | insufficient | evidencia-insuficiente-v1: fired |
| `w005` | 20 | 0 | 20 | 136 | 0.088 | 47.9 | eligible | evidencia-insuficiente-v1: resolved |
| `w006` | 20 | 0 | 20 | 137 | 0.058 | 47.6 | eligible | — |
| `w007` | 20 | 0 | 20 | 163 | 0.110 | 45.6 | eligible | — |
| `w008` | 20 | 0 | 20 | 158 | 0.089 | 45.2 | eligible | — |
| `w009` | 18 | 0 | 18 | 134 | 0.104 | 46.2 | eligible | — |

## Expectativas por etapa

| Etapa | Expectativa | Esperado | Observado | Resultado |
|---|---|---|---|---|
| 1 antes | ventanas cerradas antes del primer error son elegibles | todas eligible | ['eligible', 'eligible'] | ok |
| 1 antes | sin alertas abiertas antes del primer error | 0 | 0 | ok |
| 2 fallo | los eventos con error son exactamente los frames del tramo declarado | índice en [500, 600) (50 eventos) | 50 errores, frames 500–598 | ok |
| 2 fallo | la fuente no pierde frames: sin huecos ni descartes por saturación | 0 source_gap, 0 saturation, índices consecutivos de 2 en 2 | [0, 0] | ok |
| 2 fallo | cada error conserva el frame, el modelo y el detalle, sin puntuaciones | frame_id y model_sha256 presentes; error con texto; sin detecciones, inference_ms ni max_score | 50 | ok |
| 3 diagnóstico | el primer error queda registrado en la línea de tiempo del detector | inference_failed en el frame 500 | ['inference_failed', 500] | ok |
| 3 diagnóstico | se capturan frames con error (máx. 1 cada 3) y las imágenes existen | ≈ 16 capturas 'error', separación ≥ 3 | 17 capturas, separación mínima 3 | ok |
| 3 diagnóstico | ventanas con menos de 15 frames válidos quedan insuficientes | insufficient donde n_valid < mínimo | {'w002': '10 válidos, insufficient', 'w003': '0 válidos, insufficient', 'w004': '0 válidos, insufficient'} | ok |
| 3 diagnóstico | evidencia-insuficiente-v1 se abre al cumplir 3 ventanas insuficientes | 1 alerta, abierta en w004 | [('a01', 'w004')] | ok |
| 3 diagnóstico | reglas de confianza no se evalúan con evidencia insuficiente | insufficient_evidence | ['insufficient_evidence'] | ok |
| 3 diagnóstico | ventanas solo con errores: G1 y G4 sin datos (null, no 0) | no_data | ['no_data'] | ok |
| 3 diagnóstico | los errores siguen siendo trazables (G5) y la versión no cambió (G6) | G5 = 1.0 y G6 = 1.0 en las ventanas con errores | {'w002': [1.0, 1.0], 'w003': [1.0, 1.0], 'w004': [1.0, 1.0]} | ok |
| 4 reacción | el modelo se recarga cada 20 errores consecutivos | 2 recargas, tras [20, 40] errores | 2 recargas, tras [20, 40] errores | ok |
| 4 reacción | cada recarga verifica el SHA-256: el artefacto es el configurado (no es cambio de versión) | sha256_match = true, f59b3d833e2f | [('f59b3d833e2f', True), ('f59b3d833e2f', True)] | ok |
| 5 recuperación | la inferencia vuelve a responder en el primer frame tras el tramo | inference_recovered en el frame 600 tras 50 errores | [600, 50, 2] | ok |
| 5 recuperación | la alerta se resuelve en la primera ventana elegible tras recuperarse | w005 | ['resolved', 'w005'] | ok |
| 6 posterior | todas las ventanas desde la recuperación son elegibles | todas eligible | ['eligible', 'eligible', 'eligible', 'eligible', 'eligible'] | ok |
| 6 posterior | ninguna alerta abierta al terminar | 0 | 0 | ok |
| 6 posterior | low_prop tras la recuperación por debajo de 0.40 (como C1) | < 0.4 | [0.088, 0.058, 0.11, 0.089, 0.104] | ok |
| 6 posterior | cada frame inferido (antes y después de las recargas) tiene las mismas puntuaciones que en C1 | 148 de 148 (98 después de recuperarse) | 148 | ok |
| 6 posterior | misma configuración y modelo que C1 | ['cfg-517d02606b3e', 'yolov8n@sha256:f59b3d833e2f'] | ['cfg-517d02606b3e', 'yolov8n@sha256:f59b3d833e2f'] | ok |

## Portal

| Captura | Ruta | HTTP | Qué muestra |
|---|---|---|---|
| `s3-01-ejecucion.png` | `/ejecuciones/s3-error-inferencia-20261112T205403Z` | 200 | Falla inyectada, ventanas y línea de tiempo del detector |
| `s3-02-errores.png` | `/eventos?run_id=s3-error-inferencia-20261112T205403Z&status=error` | 200 | Eventos con error de inferencia |
| `s3-03-error.png` | `/eventos/s3-error-inferencia-20261112T205403Z-e00050` | 200 | Primer error capturado: frame, detalle y sin puntuaciones |
| `s3-04-alerta.png` | `/alertas/s3-error-inferencia-20261112T205403Z-a01` | 200 | evidencia-insuficiente-v1: ventanas, capturas de error y resolución |
| `s3-05-tablero.png` | `/tablero?run_id=s3-error-inferencia-20261112T205403Z&run_id=c1-normal-20261112T162444Z` | 200 | S3 junto a C1: ventanas insuficientes, G1/G4 sin datos (✕) y la franja de la alerta |
