# Adicionales reclamados

La base (C1, C2, una métrica base por grupo, vistas mínimas de eventos y alertas) no se
presenta como adicional. Tampoco las funciones que ya formaban parte de ella: filtros simples
de eventos y alertas, vistas de detalle de ventana y ejecución, `p50` y `cpu_percent`
informativos, y la regla `evidencia-insuficiente-v1`. El rediseño visual del portal tampoco se
reclama por sí mismo; solo F5 (filtros avanzados), que es una funcionalidad nueva.

Total solicitado: F1 15 + F2 10 + F3 15 + F4 15 + F5 10 + S1 10 + S2 8 + S3 10 + M1 5 + M2 8 +
M3 8 = **114 puntos**, sujetos al nivel que el evaluador considere demostrado.

| ID | Tipo | Descripción | Nivel solicitado | Evidencia |
|---|---|---|---|---|
| F1 | F (funcionalidad) | Tablero histórico por ventana: gráficas de las métricas base G1–G7 con comparación de ejecuciones | 15 | [`evidencias/tablero/verificacion.md`](evidencias/tablero/verificacion.md) |
| S1 | S (escenario) | Interrupción del stream: corte de 15 s, diagnóstico por watchdog, reconexión con reintentos, recuperación y verificación posterior contra C1 | 10 | [`evidencias/escenarios/s1-interrupcion.md`](evidencias/escenarios/s1-interrupcion.md) |
| S2 | S (escenario) | Cambio sostenido de confianza: normal → desenfocado → normal, con apertura y resolución de `cambio-sostenido-v1` | 8 | [`evidencias/escenarios/s2-cambio-sostenido.md`](evidencias/escenarios/s2-cambio-sostenido.md) |
| F2 | F (funcionalidad) | Exportación de eventos a CSV/JSONL con los filtros de `/eventos` | 10 | [`evidencias/exportacion/verificacion.md`](evidencias/exportacion/verificacion.md) |
| F3 | F (funcionalidad) | Revisión manual de capturas: galería, etiquetas con historial, resumen por alerta | 15 | [`evidencias/revisiones/recorrido.md`](evidencias/revisiones/recorrido.md) |
| F4 | F (funcionalidad) | Vista en vivo del stream con cajas, ventana en curso, alertas abiertas y salud de la fuente | 15 | [`evidencias/en_vivo/recorrido.md`](evidencias/en_vivo/recorrido.md) |
| S3 | S (escenario) | Error de inferencia: la llamada al modelo falla 50 frames; diagnóstico por eventos `error` y ventanas insuficientes, reacción con recarga del modelo y verificación de SHA-256, recuperación y verificación posterior contra C1 | 10 | [`evidencias/escenarios/s3-error-inferencia.md`](evidencias/escenarios/s3-error-inferencia.md) |
| F5 | F (funcionalidad) | Filtros avanzados de eventos: rangos de puntuación y detecciones, intervalo de captura, ventana, motivo, vínculo con alertas, texto en el id y orden, compartidos por página, API y exportación | 10 | [`evidencias/filtros/verificacion.md`](evidencias/filtros/verificacion.md) |
| M1 | M (métrica) | `m1_e2e_ms_p95`: p95 de la latencia de extremo a extremo por ventana (cola + inferencia + resto) | 5 | [`evidencias/metricas_adicionales/resumen.md`](evidencias/metricas_adicionales/resumen.md) |
| M2 | M (métrica) | `m2_delivery_ratio`: frames entregados / esperados según `frame_index`, cruzada con watchdog y fuente | 8 | ídem |
| M3 | M (métrica) | `m3_score_psi`: PSI de la distribución de puntuaciones de la ventana contra la referencia | 8 | ídem |

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

## M1–M3 · Métricas adicionales por ventana

Las definiciones M1–M5, los supuestos y los límites están en
[`docs/metricas-adicionales.md`](docs/metricas-adicionales.md). Las tres métricas se calculan
sobre las 5 ejecuciones (referencia, C1, C2, S1 y S2) a partir de los registros guardados,
sin volver a correr nada. Código en el commit `381873b`.

- **Resultados y expectativas:** [`evidencias/metricas_adicionales/resumen.md`](evidencias/metricas_adicionales/resumen.md)
  da 13 expectativas y 0 fallas. Los valores por ventana están en `<run_id>.jsonl`.
- **Recálculo independiente:** [`evidencias/metricas_adicionales/recalculo.md`](evidencias/metricas_adicionales/recalculo.md)
  se hace con pandas/numpy, sin importar el módulo, y da 150 comprobaciones y 0 diferencias.
- **Pruebas:** `tests/test_extra_metrics.py` (5 pruebas con datos sintéticos).

| ID | Por qué es distinta de la base | Nivel solicitado y justificación |
|---|---|---|
| M1 `m1_e2e_ms_p95` | G1 base mide solo `model.predict`; M1 suma la espera en cola y el resto | **5**: cálculo por ventana con población (frames válidos), exclusiones (`error`, `source_gap`), `no_data` y recálculo. Además, en cada evento se cumple `e2e ≥ cola + inferencia`. Revela el arranque en frío (w000: 422–535 ms contra 43–51 ms) que G1 no muestra. No hay un caso de cambio controlado de latencia, así que no se pide 8 |
| M2 `m2_delivery_ratio` | G2 base es el ritmo de procesamiento; M2 mide cuántos frames esperados llegaron | **8**: correlaciona tres registros independientes de la misma pérdida (saltos de `frame_index`, huecos del watchdog y descarte `outage` de la fuente). En el caso controlado S1 los tres dan 80 / 80 / 79.5 frames muestreados, y en C1, C2, S2 y la referencia la entrega es 1.0. Supuestos y límites documentados: atribución a la ventana de detección e índices consecutivos |
| M3 `m3_score_psi` | G4 base es una proporción bajo un umbral; M3 compara la distribución completa con la referencia | **8**: compara distribuciones con la referencia. Supuestos (9 intervalos, piso 1e-4, mínimo 30 detecciones y ventana elegible) y límites (variación propia de la referencia 0.073–0.254, sin umbral ni alerta). Caso controlado S2: ventanas desenfocadas 4.06–7.34 contra normales 0.105–0.549 |

**Sin doble conteo.**

- Ninguna sustituye a la métrica base de su grupo.
- El tablero F1 no las muestra; se entregan como datos y reporte propios.
- Los escenarios S1 y S2 solo se usan como caso controlado y no se reclaman de nuevo.

## F2 · Exportación de eventos (`/exportar/eventos.{csv,jsonl}`)

**Qué hace.** Descarga todos los eventos que cumplen los mismos filtros que `/eventos`
(ejecución, estado, zona del frame, solo con captura), sin paginar. La vista `/eventos`
enlaza la descarga con los filtros activos.

- Cada fila conserva la trazabilidad completa: `config_ref`, `model_ref`, `model_sha256`,
  `window_id`, `image_ref`, tiempos y detecciones con puntuación, zona y caja.
- Las cabeceras `X-Export-Count`, `X-Export-Filters`, `X-Export-Generated-At` y
  `X-Export-Source` describen la descarga.

**Verificación.** `scripts/verify_export.py` exporta 8 combinaciones de filtros en los dos
formatos y las compara con los eventos esperados, calculados filtrando
`evidencias/runs/*/events.jsonl` (no SQLite). Coinciden ids, orden, conteo y todos los
campos.

Los estados vacío y de error dan:

| Caso | Respuesta |
|---|---|
| Formato no soportado | 404 |
| Estado o zona desconocidos | 422 |
| Ejecución inexistente | 404 |
| Filtro válido sin resultados | 200 con solo el encabezado |

Resultado: 13 de 13 comprobaciones. Incluye un ejemplo exportado y la descarga desde el
navegador. Pruebas: `tests/test_portal.py::test_export_matches_query_and_rejects_bad_filters`.

**Nivel 10.** Consulta parametrizada, persistencia pertinente (lee la base de monitoreo) y
verificación de resultados y de estados vacíos y erróneos. No se pide 15: no coordina estados
nuevos.

**Corrección de la base hecha en el mismo commit.** Los enlaces de paginación de `/eventos`
enviaban `captured=` vacío y respondían 422 si no se marcaba "solo con captura". Ahora
omiten los filtros vacíos (`tests/test_portal.py::test_pagination_links_do_not_send_empty_filters`).
No se reclama como adicional.

## F3 · Revisión manual de capturas (`/capturas`)

**Qué hace.**

- **Galería** de capturas, filtrable por ejecución, motivo de captura y estado de revisión
  (sin revisar o cada etiqueta).
- **Página de revisión** con la imagen y sus cajas, y 5 etiquetas descriptivas: `confirma`,
  `falso_positivo`, `omision`, `imagen_degradada` y `dudosa`. Lleva nota y nombre de quien
  revisa, y el botón "Guardar y siguiente sin revisar".
- **Historial**: cada revisión es un registro nuevo y la vigente es la más reciente.
- **Resumen en la alerta**: cada alerta muestra cuántas de sus capturas están revisadas y
  con qué etiqueta.
- **API**: `GET /api/revisiones` y `POST /api/capturas/{id}/revision`.

**Persistencia y trazabilidad.**

- Base propia (`evidencias/revisiones.db`, o `REVIEW_DB`). La base de monitoreo sigue en solo
  lectura.
- Cada revisión guarda `event_id`, `run_id`, `image_ref` y las alertas del evento en ese
  momento.
- Las etiquetas describen lo que ve una persona; no se usan como métrica de calidad.

**Verificación.** `scripts/demo_reviews.py` hace el flujo en Chromium sobre una base de
demostración (`evidencias/revisiones/demo.db`):

1. Intento sin etiqueta: se rechaza y no se guarda nada.
2. Cuatro capturas de la alerta a01 de C2 con "Guardar y siguiente".
3. Re-etiquetado de la primera, que deja un historial de 2 revisiones.
4. Resumen en la alerta: "4 de 26".
5. Galería filtrada por etiqueta.
6. Por API: evento sin captura → 409, etiqueta desconocida → 422, evento inexistente → 404.

Resultado: 9 de 9 comprobaciones. Pruebas: `tests/test_reviews.py`, con validaciones,
historial y estado vigente.

**Honestidad de la demostración.** Las revisiones van firmadas como `demo-automatizada` y
solo usan etiquetas verdaderas por construcción (las capturas de C2 vienen de la entrada
desenfocada). La nota de cada una lo declara. No son revisiones humanas. La base real
`evidencias/revisiones.db` queda vacía para la autora.

**Nivel 15.** Flujo compuesto que coordina estados: la revisión vigente frente al historial,
la siguiente captura sin revisar y el resumen por alerta. Tiene persistencia propia,
trazabilidad (evento, imagen y alertas) y casos normal, borde y fallo reproducibles.

## F4 · Vista en vivo del stream (`/en-vivo`)

**Qué hace.** `python -m monitor.pipeline --scenario … --live` publica en `evidencias/live/`
el último frame y un `status.json`. La escritura es atómica (archivo temporal y `os.replace`)
y se repite en cada evento, frame o hueco. El estado incluye:

- último evento con sus detecciones;
- ventana en curso y avance frente a los mínimos;
- última ventana cerrada;
- alertas abiertas;
- conteos y descartes de la fuente.

`/en-vivo` lo consulta cada 0.5 s, dibuja las cajas por zona y deriva la **salud**:

| Salud | Cuándo |
|---|---|
| `en_curso` | Llegan frames |
| `hueco_fuente` | El último evento es un `source_gap`; la imagen anterior queda velada |
| `detenido` | Más de 3 s sin actualizaciones y sin haber terminado |
| `terminada` | La ejecución terminó |
| `sin_ejecucion` | No hay estado publicado |
| `error` | El estado es ilegible |

Sin `--live` el pipeline no escribe nada nuevo, así que C1, C2, S1 y S2 no cambian.
`storage.live_dir` no forma parte de `config_ref`.

**Verificación con una ejecución real.** `scripts/demo_live.py --scenario s1-interrupcion`
levanta el portal, corre S1 con `--live`
(`s1-interrupcion-20261112T185945Z`, commit `e244ed1`, `git_dirty=false`) y consulta
`/api/en-vivo` cada 0.25 s.

- **Secuencia de estados:** `sin_ejecucion → en_curso → hueco_fuente → en_curso → terminada`,
  tal como se esperaba.
- **Capturas:** 7 en total. Durante el corte se ve `evidencia-insuficiente-v1` abierta y,
  tras la recuperación, la alerta sale de la lista.
- **Último estado publicado frente a lo guardado:** coinciden eventos (198), huecos (80),
  frames ok (118), alertas (1) y alertas abiertas (0).

Resultado: 6 de 6 comprobaciones. Los estados `detenido` y `error` están en
`tests/test_live.py` con estados sintéticos.

**Nivel 15.** Integración adicional entre pipeline y portal mediante un estado publicado,
coordinación de estados (salud derivada, ventana en curso, alertas abiertas), trazabilidad
(enlaces a ejecución, ventana y alertas, y el estado final contrastado con lo guardado) y
casos normal y de fallo reproducibles.

**Sin doble conteo.**

- La ejecución `s1-interrupcion-20261112T185945Z` solo es la evidencia de F4. El escenario
  S1 se acredita con `s1-interrupcion-20261112T175603Z` y no se reclama otra vez.
- F2, F3 y F4 son flujos distintos entre sí y distintos de las vistas base y del tablero F1.

## S3 · Error de inferencia con reacción y recuperación (`s3-error-inferencia`)

**Entrada.** El mismo tramo que C1 (`vtest.avi`, frames 400–794, 10 fps, muestreo 1/2). La
fuente entrega todos los frames; lo que falla es la llamada al modelo para los frames 500–599
(`source.fault_injection.inference_error`), que lanza `InjectedInferenceError`. Es una condición
distinta de S1: en S1 no llegan frames (eventos `source_gap`, sin imagen); aquí el frame existe,
se captura y se conserva, pero no hay puntuación.

**Etapas y evidencia** (`s3-error-inferencia-20261112T205403Z`, commit `84b576a`,
`git_dirty=false`):

1. **Antes:** ventanas 0–1 elegibles, sin alertas.
2. **Fallo:** los 50 eventos con índice en [500, 600) quedan con estado `error`, frame, modelo
   y detalle, sin detecciones, `inference_ms` ni `max_score`. No hay huecos ni descartes.
3. **Diagnóstico:** `inference_failed` en la línea de tiempo del detector; 17 capturas con
   motivo `error`; ventanas 2–4 insuficientes; G1 y G4 sin datos (null, no 0) donde todo es
   error; G5 y G6 siguen en 1.0 (los errores son trazables y la versión no cambió); se abre
   `evidencia-insuficiente-v1` en la ventana 4.
4. **Reacción** (`config/monitor.yaml → recovery.reload_after_errors: 20`): el monitor recarga
   el modelo tras 20 y 40 errores consecutivos y comprueba su SHA-256 (`detector_reloaded`,
   `sha256_match=true`). Así descarta un artefacto cambiado o dañado.
5. **Recuperación:** `inference_recovered` en el frame 600, tras 50 errores y 2 recargas; la
   alerta se resuelve en la ventana 5.
6. **Verificación posterior:** ventanas 5–9 elegibles con `low_prop` < 0.40; cada uno de los
   148 frames inferidos tiene las mismas puntuaciones que en C1, antes y después de las
   recargas; mismo `config_ref` y modelo que C1.

Verificación: [`evidencias/escenarios/s3-error-inferencia.md`](evidencias/escenarios/s3-error-inferencia.md)
(21 expectativas, 0 fallas), recálculo independiente
[`evidencias/recalculo/s3-error-inferencia-20261112T205403Z.md`](evidencias/recalculo/s3-error-inferencia-20261112T205403Z.md)
(114 comprobaciones, 0 diferencias), pruebas `tests/test_inference_fault.py` y capturas
`evidencias/escenarios/s3-*.png`.

**Sin doble conteo.** La regla `evidencia-insuficiente-v1` es base y no se reclama; lo que se
acredita es la secuencia fallo → diagnóstico → reacción → recuperación → verificación con una
condición de aceptación distinta de S1 (frames presentes, inferencia ausente, recarga del
modelo).

## F5 · Filtros avanzados de eventos (`/eventos`, `/api/eventos`, `/exportar/eventos.*`)

**Qué hace.** Además de los filtros básicos de la base (ejecución, estado, zona, con captura),
`/eventos` ofrece un panel de filtros avanzados que se combinan entre sí:

- rango de **máxima puntuación** del frame (`score_min`, `score_max`, en [0, 1]); excluye los
  eventos sin puntuación, que no equivalen a confianza 0;
- rango de **número de detecciones** (`dets_min`, `dets_max`);
- **intervalo de captura** en UTC (`since`, `until`, ISO 8601);
- **ventana** por índice (`window`), **motivo de captura** (`reason`) y **texto en el id** (`q`);
- **solo eventos que sustentan alguna alerta** (`in_alert`), resuelto contra `alerts.event_ids`;
- **orden**: por ejecución y secuencia, puntuación ↑/↓, detecciones, tiempo de inferencia,
  extremo a extremo o más recientes; los nulos siempre van al final.

La consulta vive en la URL (se comparte y se recarga igual), se muestra como etiquetas que se
quitan una a una, y es la misma para la página, `/api/eventos` y la exportación F2. Un filtro
inválido (rango invertido, número fuera de rango o no numérico, fecha inválida, orden
desconocido) responde **422** con la causa en la página, la API y la exportación; una consulta
válida sin resultados muestra el estado vacío.

**Evidencia.** [`evidencias/filtros/verificacion.md`](evidencias/filtros/verificacion.md):
14 consultas cuyo resultado y orden se recalculan en Python desde `events.jsonl` y
`alerts.jsonl` (sin SQLite) y coinciden con la API (todas las páginas), el CSV y el conteo de
la página; que agregar filtros solo reduce el resultado; que cada etiqueta quita solo su
filtro; 7 casos de error y 2 vacíos. **25 comprobaciones, 0 fallas.** Pruebas en
`tests/test_filters.py` y capturas `evidencias/filtros/*.png`.

**Sin doble conteo.** Los filtros básicos son base y la descarga es F2; F5 acredita solo los
filtros y el orden nuevos. El rediseño visual del portal no se reclama.
