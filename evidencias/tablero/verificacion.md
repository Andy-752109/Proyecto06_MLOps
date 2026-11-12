# Verificación del tablero histórico (F1)

Generado con `python scripts/verify_dashboard.py --run-id c2-baja-confianza-20261112T162525Z --run-id c1-normal-20261112T162444Z --run-id reference-20261112T162358Z`.

## 1. Valores del tablero contra los JSONL de cada ejecución

La API `/api/tablero` (lo mismo que dibuja `/tablero`) se compara con `windows.jsonl`, `metrics.jsonl` y `alerts.jsonl`, que se escriben aparte de SQLite.

| Ejecución | Comprobaciones iguales | Diferencias |
|---|---|---|
| `c2-baja-confianza-20261112T162525Z` | 88 | 0 |
| `c1-normal-20261112T162444Z` | 84 | 0 |
| `reference-20261112T162358Z` | 84 | 0 |

Total: **256 comprobaciones, 0 diferencias** (valor y estado de cada métrica base por ventana, estado de ventana, franja de cada alerta y conteos del resumen). Detalle en `verificacion.json`.

## 2. Estados vacío y de error (base real)

| Caso | URL | HTTP esperado | HTTP | Texto esperado | Resultado |
|---|---|---|---|---|---|
| sin selección | `/tablero?enviado=1` | 200 | 200 | Selecciona al menos una ejecución | ok |
| ejecución inexistente | `/tablero?run_id=no-existe` | 404 | 404 | Ejecuciones inexistentes: no-existe | ok |
| mezcla válida + inexistente | `/tablero?run_id=c2-baja-confianza-20261112T162525Z&run_id=no-existe` | 200 | 200 | Ejecuciones inexistentes: no-existe | ok |
| tres válidas + una inexistente (el tope de 3 se prueba en tests) | `/tablero?run_id=c2-baja-confianza-20261112T162525Z&run_id=c1-normal-20261112T162444Z&run_id=reference-20261112T162358Z&run_id=extra-4` | 200 | 200 | Ejecuciones inexistentes: extra-4 | ok |
| API inexistente | `/api/tablero?run_id=no-existe` | 404 | 404 | no-existe | ok |

Los casos borde que las ejecuciones reales no producen (ventanas insuficientes, métricas `no_data` como hueco, ejecución sin ventanas, configuraciones distintas separadas en grupos, base inexistente) están en `tests/test_dashboard.py` sobre una base sintética.

## 3. Recorrido en el navegador

| Captura | URL | Qué muestra |
|---|---|---|
| `01-tablero-comparacion.png` | `/tablero?run_id=c2-baja-confianza-20261112T162525Z&run_id=c1-normal-20261112T162444Z&run_id=reference-20261112T162358Z` | Comparación de las ejecuciones seleccionadas (un grupo comparable) |
| `02-tablero-una-ejecucion.png` | `/tablero?run_id=c2-baja-confianza-20261112T162525Z&enviado=1` | Formulario enviado con solo c2-baja-confianza-20261112T162525Z |
| `03-clic-franja-alerta.png` | `/alertas/c2-baja-confianza-20261112T162525Z-a01` | Clic en la primera franja de alerta: abre su detalle |
| `04-clic-punto-ventana.png` | `/ventanas/c2-baja-confianza-20261112T162525Z-w000` | Clic en el punto de la ventana 0 en G4: abre la ventana con sus métricas |
| `05-estado-vacio.png` | `/tablero?enviado=1` | Formulario enviado sin ejecuciones: estado vacío |
| `06-estado-error.png` | `/tablero?run_id=no-existe` | Ejecución inexistente: mensaje de error (HTTP 404) |
