# Referencia y justificación de umbrales

Generado por `scripts/build_reference.py --run-id reference-20261112T162358Z` a partir de
`evidencias/runs/reference-20261112T162358Z/events.jsonl` y `windows.jsonl` (datos primarios).

- Referencia: `config/reference.json` (SHA-256 `4a67f430ccf542d08bd6fa318e9415949f6ed98807b133f7dc6db977f1f744a0`)
- Ejecución: `reference-20261112T162358Z` · commit `6b84820b06b922a495a422ea42b01d811b93811b` · cfg-517d02606b3e
- Fuente: `data/videos/vtest.avi` frames 0–400 (exclusivo),
  muestreo 1 de cada 2 a 10.0 fps nativos
- Modelo: `yolov8n@sha256:f59b3d833e2f` · piso de salida 0.1 · NMS IoU 0.45 · imgsz 640
- Unidad de análisis: **detección candidata**; población: detecciones candidatas (s >= conf_floor tras NMS) en frames con inferencia válida.
- Observaciones: 200 frames válidos, 1446 detecciones, 10 ventanas de 20 frames.

## Distribución de puntuaciones en la referencia

| Intervalo | Detecciones | Fracción |
|---|---|---|
| [0.1,0.2) | 204 | 0.141 |
| [0.2,0.3) | 41 | 0.028 |
| [0.3,0.4) | 19 | 0.013 |
| [0.4,0.5) | 25 | 0.017 |
| [0.5,0.6) | 28 | 0.019 |
| [0.6,0.7) | 130 | 0.090 |
| [0.7,0.8) | 567 | 0.392 |
| [0.8,0.9) | 429 | 0.297 |
| [0.9,1.0) | 3 | 0.002 |

Percentiles (rango más cercano): p5=0.120, p10=0.151, p25=0.651, p50=0.764, p75=0.810, p90=0.842, p95=0.858.

| Condición | Fracción de detecciones |
|---|---|
| s < 0.20 | 0.141 |
| s < 0.30 | 0.169 |
| s < 0.35 | 0.180 |
| s < 0.40 | 0.183 |
| s < 0.45 | 0.192 |
| s < 0.50 | 0.200 |
| s < 0.60 | 0.219 |
| s < 0.70 | 0.309 |
| s < 0.80 | 0.701 |

## Elección de umbrales (fijados antes de C1/C2)

La distribución es **bimodal**: un grupo de candidatas débiles cerca del piso de salida
(0.10–0.30) y la masa principal entre 0.70 y 0.90, con un valle entre ambos.

- **Umbral inferior = 0.4**: cae en el valle. La fracción bajo el umbral casi no cambia
  entre 0.30 y 0.50 (0.169 → 0.200), así que la zona baja aísla
  las candidatas débiles sin depender del valor exacto.
- **Umbral superior = 0.7**: inicio de la masa principal (p25 = 0.651).
  En la referencia, 0.691 de las detecciones son aceptadas por la política.
- Resultado: zona baja 264 (0.183), duda
  183, aceptada 999.
- Las zonas describen la puntuación, no aciertos: no hay etiquetas reales.

## Ventanas de la referencia

| Ventana | Frames válidos | Detecciones | Bajas | low_prop | Estado |
|---|---|---|---|---|---|
| reference-20261112T162358Z-w000 | 20 | 97 | 25 | 0.258 | eligible |
| reference-20261112T162358Z-w001 | 20 | 134 | 29 | 0.216 | eligible |
| reference-20261112T162358Z-w002 | 20 | 149 | 29 | 0.195 | eligible |
| reference-20261112T162358Z-w003 | 20 | 183 | 33 | 0.180 | eligible |
| reference-20261112T162358Z-w004 | 20 | 156 | 15 | 0.096 | eligible |
| reference-20261112T162358Z-w005 | 20 | 157 | 24 | 0.153 | eligible |
| reference-20261112T162358Z-w006 | 20 | 183 | 45 | 0.246 | eligible |
| reference-20261112T162358Z-w007 | 20 | 144 | 23 | 0.160 | eligible |
| reference-20261112T162358Z-w008 | 20 | 126 | 13 | 0.103 | eligible |
| reference-20261112T162358Z-w009 | 20 | 117 | 28 | 0.239 | eligible |

Proporción de baja confianza por ventana: media 0.185, desviación 0.054,
mínimo 0.096, máximo 0.258.

## Reglas derivadas

- `baja-confianza-v1`: alerta si `low_prop >= 0.4` en una ventana elegible.
  0.4 es mayor que el máximo de la referencia (0.258) y que la media + 3σ
  (0.347), así que la operación representativa no la dispara.
- `cambio-sostenido-v1`: alerta si `low_prop - 0.183 >= 0.15` durante
  3 ventanas elegibles consecutivas. 0.15 ≈ 2.8σ de la variación entre ventanas;
  exigir 3 ventanas (~12 s de stream) evita reaccionar a una sola ventana atípica.
- Mínimos por ventana: 15 frames válidos y 30 detecciones.
  La referencia tiene entre 97 y 183
  detecciones por ventana. Si no se alcanza el mínimo, la ventana es `insufficient`:
  no se evalúan las reglas de confianza y no se interpreta como normalidad.
