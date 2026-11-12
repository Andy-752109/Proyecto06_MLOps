# Política de confianza, reglas, captura y contratos

Toda la configuración vive en `config/monitor.yaml`, y su identidad es `config_ref`
(`cfg-` seguido del SHA-256 canónico de las secciones model, policy, windows, reference,
alerts y capture). C1 y C2 usan **el mismo `config_ref`**; lo único que cambia entre ellos
es la fuente (`source_ref`). Cada ejecución guarda la configuración completa en
`evidencias/runs/<run_id>/config.snapshot.json` y en la tabla `configs`, que el portal
muestra en `/config/<config_ref>`.

## 1. Detector y salida observable

| Parámetro | Valor | Efecto |
|---|---|---|
| Modelo | `modelo/yolov8n.pt`, SHA-256 `f59b3d83…3b36` | Pesos COCO preentrenados (Ultralytics assets v8.3.0) |
| Clases | `{0: person}` | Se pasa `classes=[0]` a la inferencia |
| Tamaño de entrada | `imgsz=640` | Letterbox de Ultralytics: 768×576 → 640×480 (+ relleno), normalización 0–1, BGR→RGB |
| Piso de salida | `conf_floor=0.10` | Se reportan las candidatas con s ≥ 0.10. Queda por debajo del umbral inferior para que **las zonas baja y de duda se puedan observar** (la configuración rechaza un piso mayor que `lower`) |
| NMS | IoU 0.45, `max_det=100` | NMS de Ultralytics por clase |
| Dispositivo | CPU | Se usa CPU por reproducibilidad (MPS no es determinista) |

Por cada frame procesado se guarda **un evento** con el contexto del frame y la lista de
detecciones candidatas: `det_id`, clase, puntuación, zona y caja.

## 2. Dos umbrales y tres zonas (unidad: detección)

| Zona | Condición | Significado |
|---|---|---|
| `low` | s < 0.40 | Baja confianza: se registra y cuenta para las reglas |
| `doubt` | 0.40 ≤ s < 0.70 | Duda: se registra y el frame puede capturarse |
| `accepted` | s ≥ 0.70 | Aceptada **por la política**; no implica que la detección sea correcta |

La igualdad con el umbral inferior cae en duda y la igualdad con el superior cae en aceptada
(ver `tests/test_logic.py::test_zone_boundaries`).

Estados del evento, que van aparte de las zonas:

- `ok`: hubo al menos una detección candidata.
- `no_detections`: el modelo corrió pero no devolvió candidatas ≥ piso. **No se le asigna
  puntuación** (`max_score = null`), no aporta al denominador de baja confianza y se cuenta
  aparte (`windows.n_no_detections`). Puede ser una escena vacía o una omisión del modelo.
- `error`: falló la inferencia. Queda con `error` y sin puntuación, y se excluye de las
  métricas de inferencia.

`frame_zone` es la zona de la detección con mayor puntuación del frame. Sirve como resumen
para filtrar en el portal y decidir capturas. Las reglas usan la unidad **detección**.

La justificación de 0.40 y 0.70 con observaciones de referencia está en
[`evidencias/referencia/justificacion-umbrales.md`](../evidencias/referencia/justificacion-umbrales.md).

## 3. Referencia

- Escenario `reference`: frames 0–399 del video original, con el mismo modelo, preprocesamiento
  y configuración. Los escenarios C1/C2 usan los frames 400–794, así que la referencia no
  comparte observaciones con ellos.
- `scripts/build_reference.py` genera `config/reference.json` a partir de los JSONL de esa
  ejecución. El archivo contiene la distribución de puntuaciones, los percentiles,
  `low_prop` de referencia y la variación entre ventanas.
- Cada ejecución C1/C2 registra en `manifest.json` la ruta y el SHA-256 de la referencia
  usada. Cada evaluación de `cambio-sostenido-v1` guarda `ref_low_prop` y `delta`.

## 4. Ventanas y mínimo de observaciones

- Ventanas consecutivas de **20 frames procesados**, unos 4 s a 5 fps.
- Una ventana es **elegible** si tiene ≥ 15 frames válidos **y** ≥ 30 detecciones puntuadas.
  Si no, es **insuficiente**.
- Una ventana insuficiente **no es normalidad**: no abre, no extiende y no resuelve alertas de
  confianza, y no reinicia ni suma a la racha sostenida. Su evaluación queda como
  `insufficient_evidence`. Si se repite, dispara la regla `evidencia-insuficiente-v1`.

## 5. Reglas de alerta (evaluadas al cerrar cada ventana)

| Regla | Severidad | Condición | Persistencia | Datos insuficientes |
|---|---|---|---|---|
| `baja-confianza-v1` | warning | `low_prop ≥ 0.40` | 1 ventana elegible | No se evalúa (`insufficient_evidence`) |
| `cambio-sostenido-v1` | high | `low_prop − low_prop_ref ≥ 0.15` | 3 ventanas elegibles consecutivas | No se evalúa y no rompe la racha. Sin referencia: `no_reference` |
| `evidencia-insuficiente-v1` | info | ventana insuficiente | 3 ventanas consecutivas | Es la regla que avisa de la falta de evidencia |

**Ciclo de vida**: la alerta se abre (`open`) al cumplirse la condición. Mientras la
condición siga cumpliéndose no se duplica: se extiende y agrega ventanas y eventos. Se
resuelve (`resolved`, con `resolved_at`) en la primera ventana elegible que no cumple. Si una
alerta sigue abierta al terminar la ejecución, queda `open`.

**Vínculos de cada alerta**: `rule_id`, `condition`, `config_ref`, `model_ref`, `source_id`,
`window_ids`, `event_ids` (todos los eventos de esas ventanas), `image_refs` (sus capturas) y
`observed` (`n_valid`, `n_dets`, `n_low`, `low_prop` y, si aplica, `ref_low_prop` y `delta` por
ventana, además de la ventana que la resolvió). También guarda `reason` y `suggested_action`
en texto.

Cada evaluación queda en `rule_evaluations` (SQLite y `rule_evaluations.jsonl`), con su resultado: `fired`,
`continuing`, `resolved`, `not_met`, `accumulating`, `insufficient_evidence` o `no_reference`.

La confianza no mide calidad ni confirma drift. Las alertas abren una investigación y no
implican reentrenar.

## 6. Captura y conservación de imágenes

Se guarda un JPEG (calidad 85) del frame original en
`evidencias/runs/<run_id>/capturas/<event_id>.jpg`. La ruta relativa queda en
`events.image_ref` junto con el motivo (`capture_reason`):

| Motivo | Cuándo |
|---|---|
| `muestra_normal` | 1 de cada 10 frames procesados (`seq % 10 == 0`) |
| `baja_confianza` / `duda` | El frame tiene `frame_zone` low/doubt (como máximo 1 cada 3 frames, prioridad sobre la muestra) |
| `sin_detecciones` / `error` | El estado del evento (mismo límite de 1 cada 3 frames) |
| `alerta` | Último frame de la ventana que abre una alerta, si no se había capturado |

No se guardan todos los frames. **No hay expiración automática**: ningún componente borra
capturas, y las imágenes se versionan en Git junto con los eventos. La métrica G5 y el
recálculo comprueban que cada `image_ref` resuelve a un archivo.

## 7. Correspondencia con los contratos de ejemplo de la guía

| Guía (evento) | Este proyecto |
|---|---|
| `event_id`, `run_id`, `frame_id`, `timestamp` | `event_id`, `run_id`, `frame_id`, `captured_at` (+ `inferred_at`) |
| `source_id`, `task`, `model_ref`, `status` | Iguales. `model_sha256` agrega la versión reportada |
| `prediction{class_id,score}` | `detections[]` con `class_id`, `class_name`, `score`, `zone`, `bbox_xyxy`, `det_id` |
| `confidence_zone` | `zone` por detección y `frame_zone` como resumen del frame |
| `config_ref`, `image_ref` | Iguales. Además `capture_reason`, `window_id`, `inference_ms`, `queue_ms`, `e2e_ms` |

| Guía (alerta) | Este proyecto |
|---|---|
| `alert_id`, `rule_id`, `timestamp`, `severity` | `alert_id`, `rule_id`, `opened_at` (+ `resolved_at`, `status`), `severity` |
| `event_ids`, `config_ref` | `event_ids`, `window_ids`, `config_ref`, `image_refs`, `observed` |
| `reason`, `suggested_action` | Iguales, más `condition` |

## 8. Escenario adicional S1: interrupción de la fuente

Esta sección solo aplica al escenario adicional `s1-interrupcion`. C1, C2 y la referencia no
declaran `watchdog` ni `fault_injection`, así que se comportan igual que antes.

- **Falla inyectada** (`config/scenarios.yaml → source.fault_injection.outage`): en el frame
  500 la fuente libera la conexión. Reintenta cada 2 s; los intentos fallan mientras no
  pasen 15 s. Al reconectar retoma en la posición en vivo, y los frames emitidos durante el
  corte se cuentan como descarte `outage`. Cada transición (`connection_lost`,
  `reconnect_failed`, `reconnected`) queda en la tabla `source_events` y en
  `source_events.jsonl`.
- **Watchdog** (`source.watchdog.gap_after_s: 1.0`): si pasan más de 1 s sin frames, cada
  frame esperado (cada `sample_every / fps` = 0.2 s), incluidos los del periodo de gracia, se
  registra como evento `source_gap`. Un `source_gap` no lleva frame, inferencia, puntuación ni
  imagen, y sí el detalle del silencio en `error`.
- **Ventanas**: siguen siendo de 20 eventos. Un hueco ocupa un lugar pero no es un frame
  válido, así que una ventana con huecos tiene menos de 15 frames válidos y queda
  **insuficiente**. Las reglas de confianza no se evalúan (`insufficient_evidence`) y, tras 3
  ventanas insuficientes, se abre `evidencia-insuficiente-v1`. La alerta se resuelve en la
  primera ventana elegible después de reconectar.
- **Captura**: un hueco no tiene imagen. Si la ventana que abre una alerta termina en un hueco,
  no se adjunta un frame anterior como si fuera de ese momento.
- La falla y el watchdog forman parte de la fuente (`source_ref`), no de la configuración
  de monitoreo: S1 comparte `config_ref` con C1/C2 y su resultado es comparable con C1.

## 9. Escenario adicional S2: cambio de entrada alineado

Esta sección solo aplica a `s2-cambio-sostenido` (`config/scenarios.yaml → source.switch`).
La fuente abre `vtest.avi` y `vtest_blur7.avi` y los lee en paralelo. Entre los frames 480 y
719 entrega el frame del mismo índice del archivo desenfocado y fuera de ese tramo, el
original. Los cambios quedan como `switch_on` / `switch_off` en `source_events`.
El tramo coincide con las ventanas 2–7, así que ninguna ventana mezcla entradas y cada una
se puede comparar con la ventana del mismo índice de C1 o de C2. La configuración, el modelo
y la referencia son los de C1/C2.

## 10. Escenario adicional S3: error de inferencia y recarga del modelo

Esta sección solo aplica a `s3-error-inferencia` (`config/scenarios.yaml →
source.fault_injection.inference_error`). La fuente entrega los frames con normalidad; para
los frames con índice en [500, 600) la llamada al modelo lanza `InjectedInferenceError`.

- **Evento**: estado `error`, con frame, `model_sha256` y el detalle en `error`, sin
  detecciones, `inference_ms` ni `max_score`. No es confianza 0 y no entra en G1 ni en G4.
  La política de captura lo trata como frame señalado (motivo `error`, máx. 1 cada 3).
- **Ventanas**: un error ocupa un lugar pero no es un frame válido; con menos de 15 frames
  válidos la ventana queda insuficiente y aplica lo de la §5.
- **Reacción** (`config/monitor.yaml → recovery.reload_after_errors`, fuera de `config_ref`
  porque no cambia política, ventanas ni reglas; se guarda en el manifest): cada 20 errores
  consecutivos el monitor recarga el modelo desde disco y comprueba su SHA-256
  (`detector_reloaded`). El primer error y la recuperación quedan como `inference_failed` e
  `inference_recovered`. Estos registros van a la misma línea de tiempo que los de la fuente
  (`source_events`).
- S3 comparte `config_ref` y modelo con C1/C2; los frames inferidos son comparables con C1.
