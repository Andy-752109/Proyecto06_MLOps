# Métricas adicionales (M1–M3)

No son métricas base: la métrica base de cada grupo G1–G7 sigue siendo la de
[`metricas.md`](metricas.md). Se calculan por ventana **después** de la ejecución
(`src/monitor/extra_metrics.py`, `scripts/extra_metrics.py`), a partir de `events.jsonl`,
`windows.jsonl` y la referencia. No cambian el pipeline, y por eso se aplican también a las
ejecuciones base sin volver a correrlas. El recálculo independiente está en
`scripts/recalc_extra.py` (pandas/numpy, sin importar el módulo).

Regla común: sin observaciones, `null` con estado `no_data` (nunca 0).

| ID | Grupo | Indicador | Distinta de la base porque… |
|---|---|---|---|
| `m1_e2e_ms_p95` | G1 | p95 de la latencia de extremo a extremo | G1 base mide solo la llamada al modelo; M1 incluye la espera en cola y el resto del procesamiento |
| `m2_delivery_ratio` | G2 | Frames entregados / frames esperados | G2 base mide el ritmo de procesamiento; M2 mide cuántos de los frames que la fuente debía entregar llegaron |
| `m3_score_psi` | G4 | PSI de la distribución de puntuaciones vs. la referencia | G4 base es la proporción bajo un umbral; M3 compara la distribución completa (9 intervalos) |

## M1 · Latencia de extremo a extremo p95 (`m1_e2e_ms_p95`)

- **M1 · Definición**: el p95 (rango más cercano) de `e2e_ms`, que va de la lectura del frame
  en el hilo de captura (`perf_counter`) al fin de la inferencia. Población: eventos válidos
  (`ok`, `no_detections`) de la ventana. Se excluyen los `error` y los `source_gap`, que no
  tienen inferencia completa. `detail` guarda los p50 de `queue_ms`, `inference_ms` y `e2e_ms`.
- **M2 · Adquisición**: `pipeline._process` registra `queue_ms` (lectura → salida de la cola),
  `inference_ms` (solo `model.predict`) y `e2e_ms` (lectura → fin de la inferencia) con el
  mismo reloj monotónico.
- **M3 · Cálculo**: el valor en la posición `ceil(0.95·n)` de los `e2e_ms` ordenados. Sin
  eventos válidos da `null` (`no_data`).
- **M4 · Trazabilidad**: cada valor sale de los `e2e_ms` de los eventos de la ventana.
- **M5 · Verificación**: el recálculo independiente coincide. Además, en todas las
  ejecuciones se cumple `e2e ≥ cola + inferencia` en cada evento (las etapas son coherentes).

**Hallazgo.** En la ventana 0 de todas las ejecuciones M1 vale 422–535 ms, contra 43–51 ms en
el resto. G1 no lo ve (44–55 ms en w000): la primera inferencia tarda unos 600 ms (arranque en
frío) y los frames siguientes esperan en la cola. Con 20 observaciones, el p95 por rango más
cercano es el segundo valor más alto, así que el máximo de G1 queda fuera, pero la espera en
cola del frame siguiente sí aparece en M1. Límite: depende del equipo, igual que G1.

## M2 · Tasa de entrega de frames (`m2_delivery_ratio`)

- **M1 · Definición**: frames entregados / frames esperados en la ventana. Cada frame
  entregado "esperaba" `(frame_index − frame_index del frame entregado anterior) / sample_every`
  frames, contando el suyo; el primero de la ejecución espera 1. Un salto mayor que
  `sample_every` significa frames que la fuente no entregó: corte, saturación de la cola o
  fallo de lectura. Población: eventos con frame (todos menos `source_gap`).
- **M2 · Adquisición**: `frame_index` de cada evento (índice del frame en el archivo, asignado
  por la fuente) y `sample_every` del `manifest.json`.
- **M3 · Cálculo**: `entregados / Σ esperados`. `detail` guarda `delivered`, `expected`,
  `lost` y los `gap_events` de la ventana. Una ventana sin frames entregados (solo huecos) da
  `null` (`no_data`).
- **M4 · Trazabilidad**: cada pérdida se puede ubicar en el par de eventos consecutivos con
  el salto.
- **M5 · Verificación**: recálculo independiente con `diff()` de pandas. Además se cruza con
  otras dos fuentes de la misma ejecución.

**Supuestos y límites.**

- La pérdida se atribuye a la ventana donde **se detecta**, es decir, la del primer frame
  después del salto. En S1 los 80 frames perdidos aparecen en w006 (entrega 0.111) y las
  ventanas w003–w005, que solo tienen huecos, quedan en `no_data`. Durante el corte se
  observan con los `source_gap` del watchdog.
- Supone un archivo con índices consecutivos. Para una cámara real haría falta un número de
  secuencia o un timestamp de la fuente.

**Caso de cambio controlado (S1).** La pérdida por saltos (80) coincide con los huecos que
registró el watchdog (80) y con el descarte `outage` de la fuente (159 frames / 2 = 79.5;
±1 por el redondeo del muestreo). Son tres registros independientes de la misma pérdida. En
C1, C2, S2 y la referencia la entrega es 1.0 en todas las ventanas, y la fuente no registró
descartes por saturación ni por corte.

## M3 · PSI de puntuaciones vs. referencia (`m3_score_psi`)

- **M1 · Definición**: el índice de estabilidad poblacional entre la distribución de
  puntuaciones de la ventana y la de la referencia:
  `PSI = Σ_b (p_b − q_b) · ln(p_b / q_b)`.
  - Usa los 9 intervalos de `config/reference.json → score_histogram` ([0.1, 0.2) … [0.9, 1.0]).
    El 1.0 cae en el último intervalo.
  - `p_b` es la proporción de detecciones de la ventana en el intervalo b, y `q_b` la de la
    referencia.
  - Las proporciones vacías se fijan en `1e-4` para evitar `log(0)`.
  - Población: detecciones puntuadas de los frames válidos.
- **M2 · Adquisición**: las puntuaciones crudas de `events.detections[].score`; el histograma
  de la referencia (frames 0–399, misma configuración y modelo).
- **M3 · Cálculo**:
  - Exige al menos 30 detecciones y una ventana elegible, la misma política que las reglas.
    Si no, da `null` (`insufficient`).
  - Sin detecciones da `no_data`.
  - Sin referencia da `no_reference`.
- **M4 · Trazabilidad**: la ventana, sus detecciones y el SHA-256 de la referencia
  registrado en el `manifest.json`.
- **M5 · Verificación**: recálculo independiente con `np.histogram` (mismos bordes).

**Supuestos y límites.**

- Una ventana tiene entre 44 y 164 detecciones repartidas en 9 intervalos, así que el PSI
  por ventana es ruidoso. Las propias ventanas de la referencia, comparadas con su histograma
  agregado, dan 0.073–0.254, y C1 da 0.087–0.839 (su ventana 3 tiene muy pocas detecciones
  bajas).
- Por eso **no se usa el umbral convencional de 0.25** y M3 no alimenta ninguna regla de
  alerta: es un indicador descriptivo.
- Como la confianza, el PSI no confirma pérdida de calidad.

**Caso de cambio controlado (S2).** En S2 las ventanas desenfocadas (w002–w007) dan PSI de
4.06 a 7.34 y las normales (w000, w001, w008, w009) de 0.105 a 0.549. El mínimo con desenfoque
supera al máximo normal por un factor de 7. En C2, todo desenfocado, el PSI va de 4.06 a 7.34.
