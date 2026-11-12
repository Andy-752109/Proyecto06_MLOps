# S2 · Cambio sostenido de confianza: normal → desenfocado → normal

Ejecución `s2-cambio-sostenido-20261112T181053Z` · commit `257712f` (git_dirty=False) ·
`cfg-517d02606b3e` (la misma que C1/C2) · `yolov8n@sha256:f59b3d833e2f` · fuente `src-06a561d72391` ·
referencia `low_prop` = 0.182573.

Generado con `python scripts/verify_s2.py --run-id s2-cambio-sostenido-20261112T181053Z --c1 c1-normal-20261112T162444Z --c2 c2-baja-confianza-20261112T162525Z`.
**21 expectativas, 0 fallas.**

## Entrada

Tramo de C1 (`vtest.avi`, frames 400–794, 10 fps, muestreo 1/2). Entre los frames
480 y 719 la fuente entrega el frame del mismo índice de
`data/videos/vtest_blur7.avi` (el video de C2). Con 20 frames procesados por ventana (40 frames del archivo),
ese tramo son exactamente las ventanas 2–7: ninguna ventana mezcla entradas.

## Esperado (antes de ejecutar)

Como C1 y C2 ya observaron esos mismos frames, cada ventana de S2 debe repetir la ventana del
mismo índice de C1 (normal) o C2 (desenfocada). Aplicando las reglas a esas ventanas
predichas (implementación propia de este script, no `monitor.rules`):

| Regla | Abre en | Se resuelve en |
|---|---|---|
| baja-confianza-v1 | w002 | w003 |
| baja-confianza-v1 | w004 | w008 |
| cambio-sostenido-v1 | w006 | w008 |

## Observado: ventanas

| Ventana | Entrada | low/dets | low_prop | Δ vs. referencia | Estado | Reglas |
|---|---|---|---|---|---|---|
| `w000` | normal | 9/61 | 0.148 | -0.035 | eligible | — |
| `w001` | normal | 12/77 | 0.156 | -0.027 | eligible | — |
| `w002` | desenfocada | 42/72 | 0.583 | +0.401 | eligible | baja-confianza-v1: fired, cambio-sostenido-v1: accumulating |
| `w003` | desenfocada | 22/76 | 0.289 | +0.107 | eligible | baja-confianza-v1: resolved |
| `w004` | desenfocada | 43/70 | 0.614 | +0.432 | eligible | baja-confianza-v1: fired, cambio-sostenido-v1: accumulating |
| `w005` | desenfocada | 68/97 | 0.701 | +0.518 | eligible | baja-confianza-v1: continuing, cambio-sostenido-v1: accumulating |
| `w006` | desenfocada | 71/98 | 0.724 | +0.542 | eligible | baja-confianza-v1: continuing, cambio-sostenido-v1: fired |
| `w007` | desenfocada | 84/124 | 0.677 | +0.495 | eligible | baja-confianza-v1: continuing, cambio-sostenido-v1: continuing |
| `w008` | normal | 14/158 | 0.089 | -0.094 | eligible | baja-confianza-v1: resolved, cambio-sostenido-v1: resolved |
| `w009` | normal | 14/134 | 0.104 | -0.078 | eligible | — |

## Observado: alertas

| Alerta | Regla | Severidad | Ventanas | Resuelta en | Estado | Capturas |
|---|---|---|---|---|---|---|
| `a01` | baja-confianza-v1 | warning | w002 | w003 | resolved | 9 |
| `a02` | baja-confianza-v1 | warning | w004, w005, w006, w007 | w008 | resolved | 33 |
| `a03` | cambio-sostenido-v1 | high | w004, w005, w006, w007 | w008 | resolved | 33 |

## Expectativas

| Etapa | Expectativa | Esperado | Observado | Resultado |
|---|---|---|---|---|
| 0 identidad | misma configuración, modelo y referencia que C1 y C2 | ['cfg-517d02606b3e', 'yolov8n@sha256:f59b3d833e2f', '4a67f430ccf542d08bd6fa318e9415949f6ed98807b133f7dc6db977f1f744a0'] | ['cfg-517d02606b3e', 'yolov8n@sha256:f59b3d833e2f', '4a67f430ccf542d08bd6fa318e9415949f6ed98807b133f7dc6db977f1f744a0'] | ok |
| 1 transición | la entrada cambia en los frames declarados | [('switch_on', 480), ('switch_off', 720)] | [('switch_on', 480), ('switch_off', 720)] | ok |
| 2 ventanas | w000 (normal) igual a la ventana 0 de C1 | {'n_valid': 20, 'n_dets': 61, 'n_low': 9, 'low_prop': 0.147541, 'state': 'eligible'} | {'n_valid': 20, 'n_dets': 61, 'n_low': 9, 'low_prop': 0.147541, 'state': 'eligible'} | ok |
| 2 ventanas | w001 (normal) igual a la ventana 1 de C1 | {'n_valid': 20, 'n_dets': 77, 'n_low': 12, 'low_prop': 0.155844, 'state': 'eligible'} | {'n_valid': 20, 'n_dets': 77, 'n_low': 12, 'low_prop': 0.155844, 'state': 'eligible'} | ok |
| 2 ventanas | w002 (desenfocada) igual a la ventana 2 de C2 | {'n_valid': 20, 'n_dets': 72, 'n_low': 42, 'low_prop': 0.583333, 'state': 'eligible'} | {'n_valid': 20, 'n_dets': 72, 'n_low': 42, 'low_prop': 0.583333, 'state': 'eligible'} | ok |
| 2 ventanas | w003 (desenfocada) igual a la ventana 3 de C2 | {'n_valid': 20, 'n_dets': 76, 'n_low': 22, 'low_prop': 0.289474, 'state': 'eligible'} | {'n_valid': 20, 'n_dets': 76, 'n_low': 22, 'low_prop': 0.289474, 'state': 'eligible'} | ok |
| 2 ventanas | w004 (desenfocada) igual a la ventana 4 de C2 | {'n_valid': 20, 'n_dets': 70, 'n_low': 43, 'low_prop': 0.614286, 'state': 'eligible'} | {'n_valid': 20, 'n_dets': 70, 'n_low': 43, 'low_prop': 0.614286, 'state': 'eligible'} | ok |
| 2 ventanas | w005 (desenfocada) igual a la ventana 5 de C2 | {'n_valid': 20, 'n_dets': 97, 'n_low': 68, 'low_prop': 0.701031, 'state': 'eligible'} | {'n_valid': 20, 'n_dets': 97, 'n_low': 68, 'low_prop': 0.701031, 'state': 'eligible'} | ok |
| 2 ventanas | w006 (desenfocada) igual a la ventana 6 de C2 | {'n_valid': 20, 'n_dets': 98, 'n_low': 71, 'low_prop': 0.72449, 'state': 'eligible'} | {'n_valid': 20, 'n_dets': 98, 'n_low': 71, 'low_prop': 0.72449, 'state': 'eligible'} | ok |
| 2 ventanas | w007 (desenfocada) igual a la ventana 7 de C2 | {'n_valid': 20, 'n_dets': 124, 'n_low': 84, 'low_prop': 0.677419, 'state': 'eligible'} | {'n_valid': 20, 'n_dets': 124, 'n_low': 84, 'low_prop': 0.677419, 'state': 'eligible'} | ok |
| 2 ventanas | w008 (normal) igual a la ventana 8 de C1 | {'n_valid': 20, 'n_dets': 158, 'n_low': 14, 'low_prop': 0.088608, 'state': 'eligible'} | {'n_valid': 20, 'n_dets': 158, 'n_low': 14, 'low_prop': 0.088608, 'state': 'eligible'} | ok |
| 2 ventanas | w009 (normal) igual a la ventana 9 de C1 | {'n_valid': 18, 'n_dets': 134, 'n_low': 14, 'low_prop': 0.104478, 'state': 'eligible'} | {'n_valid': 18, 'n_dets': 134, 'n_low': 14, 'low_prop': 0.104478, 'state': 'eligible'} | ok |
| 3 frames | frames normals con las mismas puntuaciones que en C1 | 78 de 78 | 78 | ok |
| 3 frames | frames desenfocados con las mismas puntuaciones que en C2 | 120 de 120 | 120 | ok |
| 4 alertas | alertas abiertas y resueltas en las ventanas que predicen las reglas | [{'rule_id': 'baja-confianza-v1', 'fired_at': 2, 'resolved_by': 3}, {'rule_id': 'baja-confianza-v1', 'fired_at': 4, 'resolved_by': 8}, {'rule_id': 'cambio-sostenido-v1', 'fired_at': 6, 'resolved_by': 8}] | [{'rule_id': 'baja-confianza-v1', 'fired_at': 2, 'resolved_by': 3}, {'rule_id': 'baja-confianza-v1', 'fired_at': 4, 'resolved_by': 8}, {'rule_id': 'cambio-sostenido-v1', 'fired_at': 6, 'resolved_by': 8}] | ok |
| 4 alertas | ninguna alerta antes del cambio de entrada | 0 | 0 | ok |
| 4 alertas | la regla sostenida acumula 1/3 y 2/3 justo antes de abrirse | ['accumulating', 'accumulating', 'fired'] | ['accumulating', 'accumulating', 'fired'] | ok |
| 5 recuperación | las alertas abiertas al volver la entrada normal se resuelven en la primera ventana normal | {'a02': 8, 'a03': 8} | {'a02': 8, 'a03': 8} | ok |
| 5 recuperación | ninguna alerta abierta al terminar | 0 | 0 | ok |
| 5 recuperación | ventanas posteriores elegibles y por debajo del umbral | eligible y low_prop < 0.4 | [('eligible', 0.089), ('eligible', 0.104)] | ok |
| 5 recuperación | las capturas vinculadas a las alertas existen | 75 | 75 | ok |

## Portal

| Captura | Ruta | HTTP | Qué muestra |
|---|---|---|---|
| `s2-01-ejecucion.png` | `/ejecuciones/s2-cambio-sostenido-20261112T181053Z` | 200 | Ventanas, cambios de entrada y alertas de S2 |
| `s2-02-alertas.png` | `/alertas?run_id=s2-cambio-sostenido-20261112T181053Z` | 200 | Alertas de S2: todas resueltas |
| `s2-03-alerta-sostenida.png` | `/alertas/s2-cambio-sostenido-20261112T181053Z-a03` | 200 | cambio-sostenido-v1: ventanas, delta contra la referencia, capturas y resolución |
| `s2-04-tablero.png` | `/tablero?run_id=s2-cambio-sostenido-20261112T181053Z&run_id=c1-normal-20261112T162444Z&run_id=c2-baja-confianza-20261112T162525Z` | 200 | S2 entre C1 y C2: sube con el desenfoque y vuelve a C1 |
