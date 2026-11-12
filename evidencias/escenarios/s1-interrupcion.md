# S1 · Interrupción y recuperación del stream

Ejecución `s1-interrupcion-20261112T175603Z` · commit `07e0e17` (git_dirty=False) ·
`cfg-517d02606b3e` (la misma que C1/C2) · `yolov8n@sha256:f59b3d833e2f` · fuente `src-f5dcc4c4c5ab`.

Generado con `python scripts/verify_s1.py --run-id s1-interrupcion-20261112T175603Z --c1 c1-normal-20261112T162444Z` a partir de los
JSONL de la ejecución. **19 expectativas, 0 fallas.**

## Entrada y falla inyectada

Tramo de C1 (`vtest.avi`, frames 400–794, ritmo nativo 10 fps, muestreo 1/2). La fuente pierde la
conexión en el frame 500 durante 15 s y reintenta cada
2 s; al reconectar retoma en la posición en vivo. El watchdog del
pipeline registra un evento `source_gap` por cada frame esperado (0.2 s) que no llega
tras 1.0 s de silencio.

## Línea de tiempo de la fuente (`source_events.jsonl`)

| # | Momento (UTC) | Tipo | Detalle |
|---|---|---|---|
| 0 | `2026-11-12T17:56:13.796Z` | connection_lost | `{"frame_index": 500, "simulated": true}` |
| 1 | `2026-11-12T17:56:15.802Z` | reconnect_failed | `{"attempt": 1, "simulated": true}` |
| 2 | `2026-11-12T17:56:17.803Z` | reconnect_failed | `{"attempt": 2, "simulated": true}` |
| 3 | `2026-11-12T17:56:19.803Z` | reconnect_failed | `{"attempt": 3, "simulated": true}` |
| 4 | `2026-11-12T17:56:21.808Z` | reconnect_failed | `{"attempt": 4, "simulated": true}` |
| 5 | `2026-11-12T17:56:23.811Z` | reconnect_failed | `{"attempt": 5, "simulated": true}` |
| 6 | `2026-11-12T17:56:25.816Z` | reconnect_failed | `{"attempt": 6, "simulated": true}` |
| 7 | `2026-11-12T17:56:27.821Z` | reconnect_failed | `{"attempt": 7, "simulated": true}` |
| 8 | `2026-11-12T17:56:29.886Z` | reconnected | `{"attempt": 8, "frame_index": 659, "frames_lost": 159, "outage_s": 16.091}` |

## Ventanas (`windows.jsonl`, `rule_evaluations.jsonl`)

| Ventana | Inicio–fin | Eventos | Frames válidos | Huecos | Detecciones | low_prop | Estado | Reglas |
|---|---|---|---|---|---|---|---|---|
| `w000` | `17:56:03.892`–`17:56:07.742` | 20 | 20 | 0 | 61 | 0.148 | eligible | — |
| `w001` | `17:56:07.897`–`17:56:11.723` | 20 | 20 | 0 | 77 | 0.156 | eligible | — |
| `w002` | `17:56:11.896`–`17:56:15.784` | 20 | 10 | 10 | 44 | 0.136 | insufficient | evidencia-insuficiente-v1: accumulating |
| `w003` | `17:56:15.996`–`17:56:19.880` | 20 | 0 | 20 | 0 | — | insufficient | evidencia-insuficiente-v1: accumulating |
| `w004` | `17:56:20.091`–`17:56:23.763` | 20 | 0 | 20 | 0 | — | insufficient | evidencia-insuficiente-v1: fired |
| `w005` | `17:56:23.972`–`17:56:27.858` | 20 | 0 | 20 | 0 | — | insufficient | evidencia-insuficiente-v1: continuing |
| `w006` | `17:56:28.063`–`17:56:31.740` | 20 | 10 | 10 | 71 | 0.056 | insufficient | evidencia-insuficiente-v1: continuing |
| `w007` | `17:56:31.897`–`17:56:35.742` | 20 | 20 | 0 | 163 | 0.110 | eligible | evidencia-insuficiente-v1: resolved |
| `w008` | `17:56:35.897`–`17:56:39.741` | 20 | 20 | 0 | 158 | 0.089 | eligible | — |
| `w009` | `17:56:39.897`–`17:56:43.338` | 18 | 18 | 0 | 134 | 0.104 | eligible | — |

## Expectativas por etapa

| Etapa | Expectativa | Esperado | Observado | Resultado |
|---|---|---|---|---|
| 1 antes | ventanas cerradas antes del corte son elegibles | todas eligible | ['eligible', 'eligible'] | ok |
| 1 antes | sin alertas abiertas antes del corte | 0 | 0 | ok |
| 2 fallo | la conexión se pierde en el frame declarado | 500 | 500 | ok |
| 2 fallo | ningún frame inferido con índice entre el corte y la reconexión | ninguno en [500, 659) | [] | ok |
| 3 diagnóstico | primer hueco detectado tras el periodo de gracia del watchdog | 1.0 s ≤ retraso ≤ 1.4 s desde el último frame | 1.067 | ok |
| 3 diagnóstico | un hueco por frame esperado durante el silencio | ≈ 80 (± 3) | 80 | ok |
| 3 diagnóstico | huecos sin frame, sin inferencia, sin imagen y con detalle | frame_id/inference_ms/image_ref nulos, error con texto | 80 | ok |
| 3 diagnóstico | ventanas con huecos quedan insuficientes (no normales) | todas insufficient | {'s1-interrupcion-20261112T175603Z-w002': 'insufficient', 's1-interrupcion-20261112T175603Z-w003': 'insufficient', 's1-interrupcion-20261112T175603Z-w004': 'insufficient', 's1-interrupcion-20261112T175603Z-w005': 'insufficient', 's1-interrupcion-20261112T175603Z-w006': 'insufficient'} | ok |
| 3 diagnóstico | evidencia-insuficiente-v1 se abre al cumplir 3 ventanas insuficientes | 1 alerta, abierta en s1-interrupcion-20261112T175603Z-w004 | [('s1-interrupcion-20261112T175603Z-a01', 's1-interrupcion-20261112T175603Z-w004')] | ok |
| 3 diagnóstico | reglas de confianza no se evalúan con evidencia insuficiente | insufficient_evidence | ['insufficient_evidence'] | ok |
| 4 reacción | reintentos cada 2 s hasta superar 15 s | 7 reintentos fallidos + 1 exitoso | 7 fallidos, intervalo 2.00–2.06 s | ok |
| 4 reacción | frames perdidos = posición en vivo − frame del corte = descarte 'outage' | 159 | [159, 159] | ok |
| 5 recuperación | la alerta se resuelve en la primera ventana elegible tras reconectar | s1-interrupcion-20261112T175603Z-w007 | ['resolved', 's1-interrupcion-20261112T175603Z-w007'] | ok |
| 5 recuperación | resolución posterior a la reconexión | > 2026-11-12T17:56:29.886Z | 2026-11-12T17:56:35.742Z | ok |
| 6 posterior | todas las ventanas desde la recuperación son elegibles | todas eligible | ['eligible', 'eligible', 'eligible'] | ok |
| 6 posterior | ninguna alerta abierta al terminar | 0 | 0 | ok |
| 6 posterior | low_prop tras la recuperación por debajo de 0.40 (como C1) | < 0.4 | [0.11, 0.089, 0.104] | ok |
| 6 posterior | cada frame inferido tiene las mismas puntuaciones que en C1 | 118 de 118 | 118 | ok |
| 6 posterior | misma configuración y modelo que C1 | ['cfg-517d02606b3e', 'yolov8n@sha256:f59b3d833e2f'] | ['cfg-517d02606b3e', 'yolov8n@sha256:f59b3d833e2f'] | ok |

## Portal

| Captura | Ruta | HTTP | Qué muestra |
|---|---|---|---|
| `s1-01-ejecucion.png` | `/ejecuciones/s1-interrupcion-20261112T175603Z` | 200 | Falla inyectada, ventanas, eventos de conexión y huecos |
| `s1-02-huecos.png` | `/eventos?run_id=s1-interrupcion-20261112T175603Z&status=source_gap` | 200 | Eventos source_gap del watchdog |
| `s1-03-hueco.png` | `/eventos/s1-interrupcion-20261112T175603Z-e00050` | 200 | Primer hueco: sin frame, sin inferencia, con detalle |
| `s1-04-alerta.png` | `/alertas/s1-interrupcion-20261112T175603Z-a01` | 200 | evidencia-insuficiente-v1: ventanas, eventos y resolución |
| `s1-05-tablero.png` | `/tablero?run_id=s1-interrupcion-20261112T175603Z&run_id=c1-normal-20261112T162444Z` | 200 | S1 junto a C1: ventanas insuficientes (huecas), métricas sin datos (✕) y la franja de la alerta |
