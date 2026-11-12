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
