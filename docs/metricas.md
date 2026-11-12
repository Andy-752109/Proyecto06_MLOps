# Inventario de métricas G1–G7

**Los 7 grupos aplican** a esta arquitectura: una fuente de video local, un detector y un
portal con eventos y alertas, en un solo proceso. No se excluye ningún grupo. Hay una
**métrica base** por grupo y ningún indicador es base de dos grupos. Por ahora no se
reclaman métricas adicionales (ver [`EXTRAS.md`](../EXTRAS.md)).

Reglas comunes a todas las métricas:

- **Ventana**: bloque consecutivo y sin traslape de `windows.size_frames = 20` **frames
  procesados**. Son unos 4 s de stream: 10 fps nativos con muestreo 1 de cada 2. La última
  ventana de una ejecución puede tener menos frames, y su tamaño real queda en `n_events`.
- **Unidades**: *frame procesado* es un frame seleccionado por el muestreo y entregado al
  modelo, y genera exactamente un evento. *Detección* es una caja candidata del modelo
  (clase `person`, s ≥ piso 0.10, después de NMS). Frames y detecciones nunca se mezclan en
  un mismo denominador.
- **Frames válidos**: eventos con `status ∈ {ok, no_detections}`. Un evento con `status = error`
  es un fallo técnico y queda fuera de las métricas de inferencia y confianza.
- **Cero observaciones**: si no hay observaciones elegibles, el valor es `null` con `status = "no_data"`.
  Nunca se reporta 0. La métrica G4 además marca `insufficient` cuando no alcanza los
  mínimos de la ventana.
- **Almacenamiento**: cada valor queda en `metric_values` (SQLite) y en
  `evidencias/runs/<run_id>/metrics.jsonl`, con `window_id`, `n_obs`, `status` y `detail`.
- **Implementación**: `src/monitor/metrics.py` (`compute_window_metrics`).
- **Verificación**: `scripts/recalc_metrics.py` las recalcula con pandas desde los JSONL
  primarios, sin reutilizar el código del monitor, y las compara una por una. Los resultados
  están en `evidencias/recalculo/<run_id>.md`.

| Grupo | Aplica | Métrica base | ID | Unidad |
|---|---|---|---|---|
| G1 · Salud y rendimiento | Sí: hay procesamiento de inferencias (sin endpoint HTTP) | Tiempo de inferencia p95 | `g1_inference_ms_p95` | ms |
| G2 · Captura y stream | Sí: el video se reproduce como stream | FPS de procesamiento | `g2_processing_fps` | frames/s |
| G3 · Recursos | Sí: hay acceso a la memoria del proceso (sin GPU) | RSS máximo del proceso | `g3_rss_mb_max` | MB |
| G4 · Predicciones | Sí: el modelo entrega puntuaciones | Proporción de baja confianza | `g4_low_conf_prop` | proporción |
| G5 · Datos y trazabilidad | Sí: se registran eventos e imágenes | Cobertura de trazabilidad | `g5_trace_coverage` | proporción |
| G6 · Fuentes y versiones | Sí: hay una fuente y una versión de modelo | Versión esperada vs. reportada | `g6_model_version_match` | proporción |
| G7 · Alertas | Sí: existen alertas | Alertas activas | `g7_active_alerts` | alertas |

---

## G1 · Tiempo de inferencia p95 (`g1_inference_ms_p95`)

- **M1 · Definición**: el percentil 95 de la duración de la llamada al modelo por frame válido
  en la ventana. Se usa el método de rango más cercano: el valor en la posición
  `ceil(0.95·n)` de la lista ordenada. Incluye el preprocesamiento de Ultralytics (letterbox a
  640), el forward en CPU y el NMS. **Excluye** la lectura del frame, la espera en cola, la
  escritura de capturas y la persistencia. Población: frames válidos de la ventana. Los
  eventos `error` quedan fuera porque no tienen duración de inferencia completa. El p50 se
  guarda en `detail` como dato informativo y no cuenta como otra métrica.
- **M2 · Adquisición**: `time.perf_counter()` antes y después de `model.predict` en
  `src/monitor/detector.py` (`PersonDetector.predict`). Queda en el campo
  `events.inference_ms`.
- **M3 · Cálculo**: `percentile_nearest_rank` en `metrics.py`. Con n = 0 da `null` (`no_data`).
  Con n = 1, p95 es esa misma observación.
- **M4 · Trazabilidad**: `metric_values.window_id` → `windows.event_ids` → `events.inference_ms`
  de cada evento, en `events.jsonl`.
- **M5 · Verificación**: `recalc_metrics.py` ordena las duraciones de `events.jsonl` y aplica
  el mismo método. Tolerancia 1e-3 relativa, porque el valor guardado está redondeado a 3 decimales.

## G2 · FPS de procesamiento (`g2_processing_fps`)

- **M1 · Definición**: los frames inferidos por segundo dentro de la ventana:
  `(n − 1) / (t_n − t_1)`, donde `t_i` es `inferred_at`, el instante UTC en que termina la
  inferencia de cada frame válido. Se usa `n − 1` porque hay n−1 intervalos entre n
  terminaciones. Población: frames válidos de la ventana. Excluye los descartes por
  muestreo o saturación (no se infieren) y los errores. El valor nominal esperado es 5 fps:
  10 fps nativos con muestreo 1 de cada 2.
- **M2 · Adquisición**: `utc_now()` al terminar cada inferencia en `pipeline.py`
  (`Monitor._process`). Queda en `events.inferred_at`. Los descartes se cuentan en
  `source.py` (`SourceStats.dropped`) y se reportan en `manifest.json`.
- **M3 · Cálculo**: `compute_window_metrics`. Con n < 2 o un lapso de 0 da `null` (`no_data`).
- **M4 · Trazabilidad**: `window_id` → eventos → `inferred_at`. `detail.span_s` guarda el lapso usado.
- **M5 · Verificación**: el recálculo parsea `inferred_at` con pandas y repite la fórmula.
  Tolerancia 1e-3 relativa.

## G3 · RSS máximo del proceso (`g3_rss_mb_max`)

- **M1 · Definición**: la memoria residente máxima del **proceso monitor** (no del equipo
  completo), en MiB (2^20 bytes), entre las muestras tomadas en la ventana. Se toma una
  muestra por frame procesado, justo después de inferir. No hay GPU (Apple M4, ejecución en
  CPU), así que no se miden métricas de GPU.
- **M2 · Adquisición**: `psutil.Process().memory_info().rss` en `Monitor._process`. Va a
  `resource_samples` y a `resources.jsonl`, con `event_id` y `ts`. También se guarda
  `cpu_percent` como dato informativo, que no es métrica base.
- **M3 · Cálculo**: el máximo de `rss_mb` en la ventana. Si no hay muestras, da `null` (`no_data`).
- **M4 · Trazabilidad**: cada muestra lleva el `event_id` del frame en el que se tomó.
- **M5 · Verificación**: el recálculo filtra `resources.jsonl` por los `event_id` de la ventana
  y toma el máximo.

## G4 · Proporción de baja confianza (`g4_low_conf_prop`)

- **M1 · Definición**: `n_low / n_dets`, donde `n_dets` son las detecciones candidatas con
  puntuación de los frames válidos de la ventana y `n_low` las que tienen `s < lower`
  (0.40). **Unidad: detección**. Los frames sin detecciones no aportan al denominador y no
  reciben una confianza artificial de 0; se cuentan aparte en `windows.n_no_detections`.
  Los errores quedan excluidos. Es una señal sobre la salida del modelo, **no sobre aciertos**.
- **M2 · Adquisición**: las puntuaciones salen del detector (`detections[].score`) y la zona
  la asigna `policy.frame_summary`. Las dos quedan en `events.jsonl` y en la tabla `detections`.
- **M3 · Cálculo**: `n_low / n_dets`. Con `n_dets = 0` da `null` (`no_data`). Si
  `n_valid < 15` o `n_dets < 30`, el valor se informa pero con `status = insufficient`, y las
  reglas de confianza no se evalúan. Esto es lo que distingue *evidencia insuficiente* de *normalidad*.
- **M4 · Trazabilidad**: `window_id` → eventos → `detections[]` con su `score` y `zone`.
  Las alertas de baja confianza guardan `n_low`, `n_dets` y `low_prop` de cada ventana.
- **M5 · Verificación**: el recálculo **reasigna las zonas desde las puntuaciones crudas** con
  los umbrales de `config.snapshot.json` y recalcula la proporción y el estado de cada ventana.
  Después verifica en qué ventanas debió abrirse la alerta `baja-confianza-v1`.

## G5 · Cobertura de trazabilidad (`g5_trace_coverage`)

- **M1 · Definición**: los eventos trazables entre los eventos de la ventana (todos los
  estados). Un evento es **trazable** cuando:
  1. tiene todos los campos obligatorios (`event_id, run_id, frame_id, captured_at,
     inferred_at, source_id, task, model_ref, model_sha256, config_ref, status, window_id`);
  2. su `config_ref` existe en la tabla `configs`;
  3. su contenido es coherente con su estado: `ok` tiene al menos una detección con
     puntuación y zona, y `n_detections` igual al largo de la lista; `no_detections` tiene la
     lista vacía y `max_score = null`; `error` incluye el detalle del error;
  4. si tiene `image_ref`, ese archivo existe.
- **M2 · Adquisición**: se evalúa al cerrar cada ventana, cuando ya se guardaron sus
  capturas (`metrics.event_is_traceable`).
- **M3 · Cálculo**: trazables / eventos. Si no hay eventos, da `null` (`no_data`).
  `detail.untraceable` lista los eventos que fallan y por qué.
- **M4 · Trazabilidad**: identifica evento por evento cuáles fallan.
- **M5 · Verificación**: el recálculo vuelve a comprobar los campos, la coherencia y la
  existencia de cada imagen en disco, de forma independiente.

## G6 · Versión esperada vs. reportada (`g6_model_version_match`)

- **M1 · Definición**: la proporción de eventos de la ventana cuyo `model_sha256` reportado
  (el SHA-256 calculado sobre el archivo de pesos que **realmente se cargó**) coincide con el
  `model.sha256` esperado en la configuración. Población: eventos con `model_sha256`. Hay
  una sola fuente y una sola versión de modelo por ejecución. La métrica deja ver si se
  reemplazó el artefacto sin actualizar la configuración.
- **M2 · Adquisición**: `detector.file_sha256` al cargar el modelo. Cada evento lo reporta.
- **M3 · Cálculo**: coincidencias / eventos. Si no hay eventos, da `null` (`no_data`).
  `detail.mismatch` cuenta las discrepancias.
- **M4 · Trazabilidad**: `events.model_sha256` frente a `config.snapshot.json → model.sha256`.
- **M5 · Verificación**: el recálculo compara las dos columnas a partir de los JSONL.

## G7 · Alertas activas (`g7_active_alerts`)

- **M1 · Definición**: el número de alertas de la ejecución con estado `open` en el instante
  en que cierra la ventana (`windows.end_at`), ya evaluadas las reglas de esa ventana. Una
  alerta está activa desde `opened_at` hasta `resolved_at`, sin incluir este último, o hasta
  el final de la ejecución si nunca se resuelve. Cada ventana aporta una sola observación,
  así que el valor puede ser 0 de forma legítima.
- **M2 · Adquisición**: `RuleEngine.active_count` al cerrar la ventana.
- **M3 · Cálculo**: un conteo. En las ejecuciones donde no se evalúan reglas (la referencia)
  vale 0, y las ventanas de esa ejecución registran que no hubo evaluación.
- **M4 · Trazabilidad**: los intervalos `opened_at`/`resolved_at` de `alerts.jsonl`.
- **M5 · Verificación**: el recálculo cuenta, para cada `end_at`, las alertas con
  `opened_at ≤ end_at < resolved_at`.

## Exclusiones dentro del catálogo

No se usa ninguna métrica de calidad predictiva (accuracy, precision, recall, mAP, IoU)
porque no hay anotaciones reales. Tampoco se miden métricas de GPU, porque la ejecución es
en CPU. La disponibilidad tipo Blackbox no aplica porque el modelo no se expone como
servicio HTTP; el portal solo consulta la persistencia.
