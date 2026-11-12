# Adicionales reclamados

La base (C1, C2, una métrica base por grupo, vistas mínimas de eventos y alertas) no se
presenta como adicional. Tampoco las funciones que ya formaban parte de ella: filtros simples
de eventos y alertas, vistas de detalle de ventana y ejecución, `p50` y `cpu_percent`
informativos, y la regla `evidencia-insuficiente-v1`.

| ID | Tipo | Descripción | Nivel solicitado | Evidencia |
|---|---|---|---|---|
| F1 | F (funcionalidad) | Tablero histórico por ventana: gráficas de las métricas base G1–G7 con comparación de ejecuciones | 15 | [`evidencias/tablero/verificacion.md`](evidencias/tablero/verificacion.md) |

## F1 · Tablero histórico por ventana (`/tablero`, `/api/tablero`)

**Qué hace.** Compara hasta 3 ejecuciones elegidas en un formulario (consulta parametrizada
por `run_id`, compartible por URL):

- Una gráfica por métrica base G1–G7. Cada punto es una ventana real leída de
  `metric_values` y `windows` (SQLite).
- El estado de cada ventana es visible: relleno = elegible, hueco = insuficiente. Un valor
  `no_data` corta la línea y se marca con ✕; nunca se dibuja como 0.
- G4 muestra el umbral de `baja-confianza-v1` (0.40). Si la referencia es comparable (mismo
  `config_ref` y `model_ref`), también muestra `low_prop` de referencia y el umbral de
  `cambio-sostenido-v1` (referencia + 0.15).
- Franjas de alertas por ejecución y regla, sobre el mismo eje de ventanas, con su estado
  (`open`/`resolved`).
- Ejecuciones con distinto `config_ref` o `model_ref` se separan en grupos y nunca comparten
  gráfica.
- Tabla por gráfica ("Ver tabla") con los mismos valores.

**Trazabilidad.** Cada punto enlaza a `/ventanas/{id}` (métricas, evaluación de reglas y
eventos de la ventana). Cada franja enlaza a `/alertas/{id}` (eventos y capturas). El resumen
enlaza a la ejecución, a sus alertas y a la configuración.

**Por qué se solicita el nivel 15.** Es un flujo compuesto que coordina varios estados
persistidos: elegibilidad de ventana, `no_data` por métrica, ciclo de vida de alertas,
comparabilidad de la referencia y agrupación por configuración/modelo. Además tiene caso
normal y casos borde/fallo reproducibles:

| Caso | Dónde se verifica | Resultado |
|---|---|---|
| Normal: C2 vs C1 vs referencia | `scripts/verify_dashboard.py`: cada valor y estado de la API contra `windows.jsonl`, `metrics.jsonl` y `alerts.jsonl` (fuente independiente de SQLite) | 256 comprobaciones, 0 diferencias |
| Recorrido: selección, clic en franja, clic en punto | Mismo script, Chromium headless → `evidencias/tablero/01…04-*.png` | Llega a la alerta y a la ventana correctas |
| Vacío (sin selección) y error (ejecución inexistente, HTTP 404; API 404) | Mismo script, sobre la base real → `05-estado-vacio.png`, `06-estado-error.png` | ok |
| Ventana insuficiente, métrica `no_data` como hueco, ejecución sin ventanas, más de 3 ejecuciones, configuraciones distintas, base inexistente (503) | `tests/test_dashboard.py` (base SQLite sintética) | 6 pruebas pasan |

**Límite declarado.** Las ejecuciones reales actuales no tienen ventanas insuficientes ni
métricas `no_data`, así que esos casos borde se acreditan con la base sintética de las
pruebas. Si el evaluador no los acepta para el nivel 15, el flujo cumple el nivel 10:
consulta parametrizada, persistencia pertinente y verificación de resultados y de estados
vacíos/erróneos.

**Sin doble conteo.** No reemplaza ni renombra vistas base: `/eventos` y `/alertas` siguen
siendo las vistas mínimas. El tablero solo **muestra** las métricas base G1–G7 y no reclama
ninguna métrica adicional. No modifica el pipeline ni las ejecuciones C1/C2.

**Código:** commit `be11d68`. **Evidencia:** generada sobre ese commit, sin modificar `src/`.

**Reproducir.**

```bash
python -m pytest -q tests/test_dashboard.py
python scripts/verify_dashboard.py --run-id c2-baja-confianza-20261112T162525Z \
  --run-id c1-normal-20261112T162444Z --run-id reference-20261112T162358Z
uvicorn monitor.portal.app:app --port 8000   # http://127.0.0.1:8000/tablero
```
