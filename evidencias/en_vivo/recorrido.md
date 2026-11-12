# Vista en vivo (F4) · recorrido durante una ejecución real

Generado con `python scripts/demo_live.py --scenario s1-interrupcion`. Ejecución `s1-interrupcion-20261112T185945Z` (commit `e244ed1`, git_dirty=False), lanzada con `--live`.

**6 comprobaciones, 0 fallas.**

## Estados observados en `/api/en-vivo` (consulta cada 0.25 s)

| t (s) | Estado | Último evento (seq) | Alertas abiertas |
|---|---|---|---|
| 0.0 | sin_ejecucion | — | — |
| 2.03 | en_curso | 4 | — |
| 12.06 | hueco_fuente | 54 | — |
| 27.16 | en_curso | 130 | a01 |
| 40.61 | terminada | 197 | — |

## Último estado publicado contra lo guardado por la ejecución

| Comprobación | Guardado | Publicado en vivo | Resultado |
|---|---|---|---|
| eventos publicados en vivo = eventos guardados | 198 | 198 | ok |
| huecos publicados = huecos guardados | 80 | 80 | ok |
| frames ok publicados = guardados | 118 | 118 | ok |
| alertas de la ejecución = alerts.jsonl | 1 | 1 | ok |
| alertas abiertas al final = abiertas en alerts.jsonl | 0 | 0 | ok |
| secuencia de estados de la vista | ['sin_ejecucion', 'en_curso', 'hueco_fuente', 'en_curso', 'terminada'] | ['sin_ejecucion', 'en_curso', 'hueco_fuente', 'en_curso', 'terminada'] | ok |

## Capturas de `/en-vivo`

| Captura | Qué muestra |
|---|---|
| `00-sin-ejecucion.png` | Antes de iniciar: no hay estado publicado |
| `01-en-curso.png` | Recibiendo frames: cajas por zona, ventana en curso |
| `02-hueco-fuente.png` | Corte: el watchdog registra huecos; se conserva el último frame velado |
| `03-alerta-abierta.png` | Durante el corte se abre evidencia-insuficiente-v1 y aparece en la vista |
| `04-recuperado.png` | La fuente vuelve a entregar frames tras la reconexión |
| `05-alerta-resuelta.png` | Tras la recuperación la alerta se resuelve y sale de la lista |
| `06-terminada.png` | Fin de la ejecución: último estado publicado |

Los estados `detenido` (sin actualizaciones por más de 3 s sin terminar) y `error` (estado ilegible) se prueban en `tests/test_live.py` con estados sintéticos.
