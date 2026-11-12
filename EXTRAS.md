# Adicionales reclamados

La base (C1, C2, una métrica base por grupo, vistas mínimas de eventos y alertas) no se
presenta como adicional. Tampoco las funciones que ya formaban parte de ella: filtros simples
de eventos y alertas, vistas de detalle de ventana y ejecución, `p50` y `cpu_percent`
informativos, y la regla `evidencia-insuficiente-v1`.

| ID | Tipo | Descripción | Nivel solicitado | Evidencia |
|---|---|---|---|---|
| F1 | F (funcionalidad) | Tablero histórico por ventana: gráficas de las métricas base G1–G7 con comparación de ejecuciones | 15 | [`evidencias/tablero/verificacion.md`](evidencias/tablero/verificacion.md) |
| S1 | S (escenario) | Interrupción del stream: corte de 15 s, diagnóstico por watchdog, reconexión con reintentos, recuperación y verificación posterior contra C1 | 10 | [`evidencias/escenarios/s1-interrupcion.md`](evidencias/escenarios/s1-interrupcion.md) |
| S2 | S (escenario) | Cambio sostenido de confianza: normal → desenfocado → normal, con apertura y resolución de `cambio-sostenido-v1` | 8 | [`evidencias/escenarios/s2-cambio-sostenido.md`](evidencias/escenarios/s2-cambio-sostenido.md) |

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
| Normal y borde con datos reales: S1 vs C1 vs C2 | `scripts/verify_dashboard.py`: cada valor y estado de la API contra `windows.jsonl`, `metrics.jsonl` y `alerts.jsonl` (fuente independiente de SQLite). S1 aporta 5 ventanas insuficientes y 14 métricas `no_data` reales | 257 comprobaciones, 0 diferencias |
| Recorrido: selección, clic en franja, clic en punto | Mismo script, Chromium headless → `evidencias/tablero/01…04-*.png` | Llega a la alerta y a la ventana correctas |
| Vacío (sin selección) y error (ejecución inexistente, HTTP 404; API 404) | Mismo script, sobre la base real → `05-estado-vacio.png`, `06-estado-error.png` | ok |
| S1 en el tablero junto a C1 | `scripts/verify_s1.py` → [`evidencias/escenarios/s1-05-tablero.png`](evidencias/escenarios/s1-05-tablero.png) | Ventanas 2–6 huecas, ✕ en G1/G2/G4/G6 durante el corte, franja de `evidencia-insuficiente-v1` resuelta |
| Ejecución sin ventanas, más de 3 ejecuciones, configuraciones distintas, base inexistente (503) | `tests/test_dashboard.py` (base SQLite sintética: no ocurren en las ejecuciones reales) | 6 pruebas pasan |

**Sin doble conteo.** No reemplaza ni renombra vistas base: `/eventos` y `/alertas` siguen
siendo las vistas mínimas. El tablero solo **muestra** las métricas base G1–G7 y no reclama
ninguna métrica adicional. No modifica el pipeline ni las ejecuciones C1/C2.

**Código:** commit `be11d68`, más la indicación de casos borde reales en `2205d42`. **Evidencia:**
regenerada sobre `2205d42` con S1, C1 y C2.

**Reproducir.**

```bash
python -m pytest -q tests/test_dashboard.py
python scripts/verify_dashboard.py --run-id s1-interrupcion-20261112T175603Z \
  --run-id c1-normal-20261112T162444Z --run-id c2-baja-confianza-20261112T162525Z
uvicorn monitor.portal.app:app --port 8000   # http://127.0.0.1:8000/tablero
```

## S1 · Interrupción y recuperación del stream (`s1-interrupcion`)

**Entrada.** El mismo tramo que C1 (`vtest.avi`, frames 400–794, 10 fps, muestreo 1/2), con la
misma configuración (`cfg-517d02606b3e`) y el mismo modelo. Lo único distinto es la fuente
(`config/scenarios.yaml → s1-interrupcion`), que declara:

- un corte inyectado en el frame 500 que dura 15 s, con reintentos cada 2 s;
- un watchdog que, tras 1 s sin frames, registra cada frame esperado (cada 0.2 s) como evento
  `source_gap`.

**Ejecución.** `s1-interrupcion-20261112T175603Z`, commit `07e0e17`, `git_dirty=false`.

| Etapa | Qué pasa (observado) | Registro |
|---|---|---|
| 1 · Antes | w000–w001 elegibles, `low_prop` 0.148 / 0.156, sin alertas | `windows.jsonl` |
| 2 · Fallo | `connection_lost` en el frame 500. Ningún frame entre 500 y 659 llega al modelo | `source_events.jsonl` |
| 3 · Diagnóstico | El primer hueco se registra 1.07 s después del último frame. Hay 80 `source_gap` (≈ 16.1 s / 0.2 s), sin frame, inferencia ni imagen. w002–w006 quedan **insuficientes**; las reglas de confianza dan `insufficient_evidence`, no "normal". `evidencia-insuficiente-v1` (info) se abre en w004, la 3.ª ventana insuficiente seguida | `events.jsonl`, `rule_evaluations.jsonl`, `alerts.jsonl` |
| 4 · Reacción | 7 reintentos fallidos cada 2.00–2.06 s y `reconnected` en el 8.º, en la posición en vivo (frame 659). 159 frames perdidos = descarte `outage` | `source_events.jsonl`, `manifest.json` |
| 5 · Recuperación | La alerta se resuelve en w007, la primera ventana elegible tras reconectar | `alerts.jsonl → observed.resolved_by` |
| 6 · Verificación posterior | w007–w009 elegibles, `low_prop` 0.110 / 0.089 / 0.104 (< 0.40) y ninguna alerta abierta al final. Los 118 frames inferidos tienen **exactamente las mismas puntuaciones que en C1** para el mismo `frame_index` | `scripts/verify_s1.py` |

**Esperado y observado.** `scripts/verify_s1.py` comprueba 19 expectativas derivadas de la
configuración declarada (frame del corte, periodo del watchdog, intervalo de reintento,
persistencia de la regla) contra los JSONL: **19 de 19 se cumplen**. El recálculo
independiente (`evidencias/recalculo/s1-interrupcion-20261112T175603Z.md`) da 114
comprobaciones y 0 diferencias. Incluye la apertura y resolución de `evidencia-insuficiente-v1`.

**Portal.** `evidencias/escenarios/s1-01…05-*.png`:

- la ejecución, con la falla inyectada y los eventos de conexión;
- la lista de huecos y el detalle de un hueco;
- la alerta;
- el tablero junto a C1.

**Por qué se solicita el nivel 10.** Es una secuencia compuesta con fallo (corte), diagnóstico
(watchdog → huecos → ventanas insuficientes → alerta), reacción (reintentos de reconexión),
recuperación (alerta resuelta) y verificación posterior (ventanas elegibles e igualdad con
C1). Cada etapa conserva su registro y se reproduce con los comandos de abajo.

**Sin doble conteo.**

- La regla `evidencia-insuficiente-v1` ya existía en la base como tratamiento de datos
  insuficientes. Aquí no se reclama la regla, sino el escenario que la ejercita con un fallo
  real de la fuente.
- No es la "baja confianza" de C2: aquí no cambia ninguna puntuación.
- S1 se reclama como un solo escenario. "Recuperación" no se cuenta aparte.
- El watchdog y los huecos tampoco se reclaman como métrica adicional.

**Límite declarado.** El corte es simulado dentro de la fuente (la reconexión reabre el mismo
archivo y salta a la posición en vivo). Así el evaluador lo reproduce sin red ni cámara. Los
eventos de conexión llevan `simulated: true`. Al reproducirlo, los instantes y el número exacto
de huecos varían en ±1 por la planificación del sistema operativo; las expectativas lo toleran.

**Reproducir.**

```bash
python -m pytest -q tests/test_source_gap.py
python -m monitor.pipeline --scenario s1-interrupcion            # ~40 s
python scripts/recalc_metrics.py --run-id <id-s1>
python scripts/verify_s1.py --run-id <id-s1> --c1 c1-normal-20261112T162444Z
```

## S2 · Cambio sostenido: normal → desenfocado → normal (`s2-cambio-sostenido`)

**Entrada.** El mismo tramo, la misma configuración, el mismo modelo y la misma referencia
que C1/C2. Entre los frames 480 y 719 la fuente entrega el frame del mismo índice del video
desenfocado de C2 (`config/scenarios.yaml → source.switch`). Ese tramo son exactamente las
ventanas 2–7, así que ninguna ventana mezcla entradas.

**Esperado antes de ejecutar.** C1 y C2 ya observaron esos frames, así que cada ventana de S2
debe repetir la del mismo índice de C1 (normal) o de C2 (desenfocada). `scripts/verify_s2.py`
aplica las reglas con una implementación propia (no `monitor.rules`) a esas ventanas
predichas:

| Regla | Abre en | Se resuelve en |
|---|---|---|
| baja-confianza-v1 | w002 | w003 |
| baja-confianza-v1 | w004 | w008 |
| cambio-sostenido-v1 (Δ ≥ 0.15 vs. referencia 0.183, 3 ventanas) | w006 | w008 |

**Observado.** `s2-cambio-sostenido-20261112T181053Z`, commit `257712f`, `git_dirty=false`.

| Etapa | Ventanas | Qué pasa |
|---|---|---|
| Normal | w000–w001 | `low_prop` 0.148 / 0.156, sin alertas |
| Transición | w002 | `switch_on` en el frame 480. `low_prop` 0.583 (Δ +0.401): abre `baja-confianza-v1` (a01); la regla sostenida acumula 1/3 |
| Variación transitoria | w003 | `low_prop` 0.289 (Δ +0.107 < 0.15). a01 se resuelve y la racha sostenida se reinicia: un cambio breve no basta para la regla sostenida |
| Persistencia | w004–w007 | `low_prop` 0.614–0.724. Abre a02 (baja confianza); la regla sostenida acumula 1/3 y 2/3 y abre **a03 (`cambio-sostenido-v1`, high)** en w006; ambas siguen en w007 |
| Recuperación | w008 | `switch_off` en el frame 720. `low_prop` 0.089: a02 y a03 se resuelven en la primera ventana normal |
| Verificación posterior | w008–w009 | Elegibles, por debajo de 0.40, sin alertas abiertas al terminar |

`scripts/verify_s2.py` comprueba 21 expectativas, y **las 21 se cumplen**:

- Las 10 ventanas tienen `n_valid`, `n_dets`, `n_low`, `low_prop` y estado idénticos a los de
  la ventana correspondiente de C1 o C2.
- Los 198 frames inferidos tienen las mismas puntuaciones que el mismo frame de C1
  (normales) o de C2 (desenfocados).
- Las alertas se abren y se resuelven donde lo predice la derivación independiente, y la
  regla sostenida acumula 1/3 y 2/3 antes de abrirse.
- Las capturas vinculadas existen.

El recálculo independiente (`evidencias/recalculo/s2-cambio-sostenido-20261112T181053Z.md`)
da 114 comprobaciones y 0 diferencias.

**Portal.** `evidencias/escenarios/s2-01…04-*.png`:

- la ejecución, con los cambios de entrada;
- las alertas, todas resueltas;
- el detalle de la alerta sostenida, con el Δ por ventana y sus capturas;
- el tablero con S2 entre C1 y C2: S2 sigue a C1, sube con C2 y vuelve a C1.

**Por qué se solicita el nivel 8.** Es una secuencia temporal adicional con transición
(normal → desenfocado), persistencia (la regla sostenida exige 3 ventanas e ignora la
variación transitoria de w003) y recuperación (vuelta a normal y resolución). Los registros
están vinculados y las expectativas se verificaron de antemano. No se solicita el nivel 10:
no hay un fallo técnico con reacción automática, solo un cambio de condiciones.

**Sin doble conteo.**

- C2 ya abre `cambio-sostenido-v1`, pero nunca vuelve a la normalidad: su alerta a04 sigue
  abierta al final. S2 aporta lo que C2 no demuestra: entrada desde operación normal,
  persistencia frente a una variación breve y resolución al recuperarse.
- No se reclama de nuevo la baja confianza aislada de C2.
- S2 no comparte evidencia de etapa con S1.

**Reproducir.**

```bash
python -m pytest -q tests/test_source_switch.py
python -m monitor.pipeline --scenario s2-cambio-sostenido        # ~40 s
python scripts/recalc_metrics.py --run-id <id-s2>
python scripts/verify_s2.py --run-id <id-s2> --c1 c1-normal-20261112T162444Z \
  --c2 c2-baja-confianza-20261112T162525Z
```
