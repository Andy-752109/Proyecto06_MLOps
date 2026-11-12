# Proyecto 6 · Centro de monitoreo de computer vision

**Autora:** Andrea Lizeth Arevalo Solis · Expediente 752109 · ITESO
**Materia:** Integración de Servicios de Aprendizaje Automático (MLOps) · entrega **individual**

El sistema monitorea un detector de personas que recibe un stream de video. Cada frame
inferido genera un evento con sus detecciones, zonas de confianza y configuración. Algunos
frames se capturan como imagen según una política declarada. Las reglas de alerta se evalúan
por ventana, y un portal web permite consultar eventos y alertas y seguir sus vínculos hasta
la evidencia.

| | |
|---|---|
| Tarea | Detección de objetos: clase `person` (COCO id 0) |
| Fuente | Archivo de video reproducido como stream a su ritmo nativo (10 fps), con muestreo 1 de cada 2 (5 fps inferidos) |
| Modelo | YOLOv8n preentrenado (Ultralytics), `modelo/yolov8n.pt`, SHA-256 `f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36` |
| Ejecución | Local, CPU. macOS 27.2 arm64 (Apple M4), Python 3.12, torch 2.15.0, ultralytics 8.4.211 |
| Persistencia | SQLite (`evidencias/monitor.db`) + JSONL por ejecución + JPEG |
| Portal | FastAPI + Jinja2: vistas de eventos y alertas, con detalle de evento, alerta, ventana, ejecución y configuración. Adicional: tablero histórico `/tablero` (ver [`EXTRAS.md`](EXTRAS.md)) |
| Escenarios base | **C1** operación normal · **C2** baja confianza (desenfoque óptico real de la entrada) |
| Escenarios adicionales | **S1** interrupción del stream con reconexión y recuperación · **S2** cambio sostenido normal → desenfocado → normal (ver [`EXTRAS.md`](EXTRAS.md)) |

**Índice de evidencias y mapa de criterios:** [`evidencias/indice.md`](evidencias/indice.md)

## Arquitectura

```
 data/videos/*.avi
       │  hilo de captura: ritmo nativo 10 fps, muestreo 1/2,
       ▼  cola acotada (4) → descartes por motivo (sampling / saturation)
 VideoStreamSource ──Frame(frame_index, captured_at)──▶ PersonDetector (YOLOv8n, CPU)
                                                          │ detecciones s ≥ 0.10 tras NMS
                                                          ▼
                                    política: zonas low / doubt / accepted por detección
                                                          │
                     evento (+ captura JPEG según política) ── búfer de la ventana (20 frames)
                                                          │ al cerrar la ventana
                                                          ▼
                   estado eligible/insufficient → RuleEngine (3 reglas) → alertas
                   métricas base G1–G7 → metric_values
                                                          │
                     SQLite + JSONL (evidencias/runs/<run_id>/) + capturas/
                                                          │
                     Portal FastAPI: /eventos  /alertas  /eventos/{id}  /alertas/{id}
                                     /ventanas/{id}  /ejecuciones/{id}  /config/{ref}
                                     /tablero (F1)  /exportar/eventos.{csv,jsonl} (F2)
                                     /capturas (F3)  /en-vivo (F4, con --live)
```

| Módulo | Responsabilidad |
|---|---|
| `src/monitor/source.py` | Reproduce el video como stream y cuenta lecturas, fallos y descartes. En S1: corte inyectado, reconexión y watchdog de huecos. En S2: cambio a un archivo alineado en un tramo |
| `src/monitor/detector.py` | Carga el modelo, verifica su SHA-256 y mide el tiempo de inferencia |
| `src/monitor/policy.py` | Asigna las tres zonas y resume cada frame |
| `src/monitor/rules.py` | Estado de la ventana, reglas y ciclo de vida de las alertas |
| `src/monitor/metrics.py` | Métricas base por ventana (una por grupo) |
| `src/monitor/store.py` | Esquema SQLite y escritura dual SQLite/JSONL |
| `src/monitor/pipeline.py` | Orquesta la ejecución de un escenario y escribe el `manifest.json` |
| `src/monitor/portal/` | Portal de consulta; `dashboard.py` arma el tablero histórico (adicional F1) |
| `scripts/` | Preparación de entradas, referencia, recálculo independiente y recorrido del portal |

Documentación detallada:

- [`docs/politica.md`](docs/politica.md): umbrales, zonas, referencia, ventanas, reglas, captura y contratos.
- [`docs/metricas.md`](docs/metricas.md): inventario G1–G7 con la definición M1–M5 de cada métrica base.
- [`evidencias/referencia/justificacion-umbrales.md`](evidencias/referencia/justificacion-umbrales.md): elección de umbrales con observaciones.
- [`docs/metricas-adicionales.md`](docs/metricas-adicionales.md): métricas adicionales M1–M3 (no base).
- [`EXTRAS.md`](EXTRAS.md): adicionales reclamados.

## Instalación

Requisitos: Python ≥ 3.10 (se usó 3.12) y unos 2 GB libres para torch.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .                       # instala el paquete monitor (src/)
python scripts/prepare_inputs.py       # verifica los SHA-256 del video y el modelo; genera el video C2 si falta
python -m playwright install chromium  # solo para scripts/capture_portal.py
```

El video, el video de C2 y los pesos ya están versionados en el repositorio.
`prepare_inputs.py` verifica sus SHA-256 y, si faltan, los descarga o regenera.

## Ejecución

```bash
# 0) Pruebas de lógica y del portal (datos sintéticos; complementan C1/C2, no los sustituyen)
python -m pytest -q

# 1) Referencia (frames 0–399 del video original), sin evaluar reglas
python -m monitor.pipeline --scenario reference --run-id <id-referencia>
python scripts/build_reference.py --run-id <id-referencia>
#    → config/reference.json y evidencias/referencia/justificacion-umbrales.md

# 2) C1 · operación normal (frames 400–794 del video original)
python -m monitor.pipeline --scenario c1-normal

# 3) C2 · baja confianza (frames 400–794 del mismo video con desenfoque gaussiano σ=7)
python -m monitor.pipeline --scenario c2-baja-confianza

# 4) Recálculo independiente de métricas, ventanas y alertas desde los JSONL
python scripts/recalc_metrics.py --run-id <id-c1> --run-id <id-c2>

# 5) Portal
uvicorn monitor.portal.app:app --port 8000      # http://127.0.0.1:8000

# 6) Recorrido del portal con capturas de pantalla (evidencia)
python scripts/capture_portal.py --c1 <id-c1> --c2 <id-c2>

# 7) Adicional S1: interrupción del stream (~40 s) y verificación por etapas contra C1
python -m monitor.pipeline --scenario s1-interrupcion
python scripts/recalc_metrics.py --run-id <id-s1>
python scripts/verify_s1.py --run-id <id-s1> --c1 <id-c1>

# 8) Adicional S2: cambio sostenido normal → desenfocado → normal (~40 s)
python -m monitor.pipeline --scenario s2-cambio-sostenido
python scripts/recalc_metrics.py --run-id <id-s2>
python scripts/verify_s2.py --run-id <id-s2> --c1 <id-c1> --c2 <id-c2>

# 9) Adicionales M1–M3: métricas por ventana sobre las ejecuciones ya hechas + recálculo independiente
python scripts/extra_metrics.py --run-id <id-referencia> --run-id <id-c1> --run-id <id-c2> --run-id <id-s1> --run-id <id-s2>
python scripts/recalc_extra.py  --run-id <id-referencia> --run-id <id-c1> --run-id <id-c2> --run-id <id-s1> --run-id <id-s2>

# 10) Adicionales F2–F4: exportación, revisión de capturas y vista en vivo
python scripts/verify_export.py --run-id <id-c2> --run-id <id-s1>
python scripts/demo_reviews.py --c2 <id-c2>          # base de demostración aparte
python scripts/demo_live.py --scenario s1-interrupcion  # crea una ejecución nueva con --live
#    Uso manual de la vista en vivo: en una terminal el portal y en otra
#    python -m monitor.pipeline --scenario c1-normal --live   → http://127.0.0.1:8000/en-vivo

# 11) Adicional F1: verificación del tablero contra los JSONL + recorrido en el navegador
python scripts/verify_dashboard.py --run-id <id-c2> --run-id <id-c1> --run-id <id-referencia>
```

Cada ejecución dura unos 40 s porque respeta el ritmo nativo del video. Lo que produce:

- Una carpeta nueva `evidencias/runs/<run_id>/`. Las ejecuciones nunca se sobrescriben.
- Dentro de ella: `manifest.json`, `config.snapshot.json`, `events.jsonl`,
  `detections.jsonl`, `windows.jsonl`, `metrics.jsonl`, `rule_evaluations.jsonl`,
  `alerts.jsonl`, `resources.jsonl` y `capturas/`.
- Filas nuevas en `evidencias/monitor.db`.

Para reproducir sin tocar las evidencias versionadas, trabaja en una copia del repositorio.
También puedes usar otra base con `MONITOR_DB=/ruta/otra.db` para el portal. El pipeline
siempre escribe en la base configurada en `config/monitor.yaml → storage`.

## Configuración

- Revisiones manuales de capturas: `evidencias/revisiones.db` (otra ruta con `REVIEW_DB`).
  El portal sigue abriendo la base de monitoreo en solo lectura.
- `config/monitor.yaml`: modelo, umbrales (0.40 / 0.70), ventanas (20 frames, mínimos 15 frames
  y 30 detecciones), reglas de alerta, política de captura y almacenamiento. Su hash es el `config_ref`.
- `config/scenarios.yaml`: fuente de cada escenario (ruta, SHA-256, tramo de frames,
  muestreo, cola). C1 y C2 comparten el `config_ref` y solo difieren en la fuente. S1 también
  lo comparte; su fuente declara además la falla inyectada y el watchdog.
- `config/reference.json`: referencia generada a partir de observaciones reales.

## Autoría, aportación propia y componentes reutilizados

**Aportación propia** (Andrea Lizeth Arevalo Solis): diseño e implementación de todo el código
de `src/monitor/` (stream, integración del modelo, política de zonas, reglas y ciclo de vida
de alertas, métricas, persistencia y portal), de los scripts de `scripts/`, de las pruebas,
de la configuración, de la documentación y de la generación de evidencias.

**Componentes reutilizados (sin modificar):**

| Componente | Procedencia | Licencia | Uso |
|---|---|---|---|
| `modelo/yolov8n.pt` | [ultralytics/assets v8.3.0](https://github.com/ultralytics/assets/releases/tag/v8.3.0), preentrenado en COCO por Ultralytics. **No se reentrenó.** | AGPL-3.0 | Detector |
| `ultralytics` (8.4.211) | PyPI | AGPL-3.0 | Preprocesamiento, inferencia y NMS |
| `data/videos/vtest.avi` | [opencv/opencv · samples/data/vtest.avi](https://github.com/opencv/opencv/blob/4.x/samples/data/vtest.avi) | Licencia del repositorio OpenCV (Apache-2.0) | Fuente visual (peatones, 795 frames, 768×576, 10 fps) |
| `data/videos/vtest_blur7.avi` | Derivado de `vtest.avi` con `scripts/prepare_inputs.py` (desenfoque gaussiano σ=7, MJPG) | — | Entrada de C2 |
| FastAPI, Jinja2, OpenCV, psutil, pandas, PyYAML, Playwright | PyPI | Varias (MIT/BSD/Apache) | Portal, captura, recursos, recálculo y capturas de pantalla |

No se reutiliza código del Proyecto 5. No se usó el carrito: la fuente es un archivo de video
para que el evaluador pueda reproducir exactamente las mismas condiciones sin hardware.

## Límites conocidos

- Hay una sola fuente local y un solo modelo. Las métricas G6 y G7 se calculan, pero en este
  alcance sus valores son poco variados (versión única, pocas alertas).
- El desenfoque de C2 se aplica al archivo de entrada antes de la inferencia. Las puntuaciones
  bajas salen del modelo y no se modifican.
- No se evalúa calidad predictiva: no hay etiquetas. Las zonas y alertas describen la
  confianza del modelo, no aciertos.
- Los tiempos (G1, G2) y la memoria (G3) dependen del equipo. Los valores reportados
  corresponden al entorno descrito arriba.
- `vtest_blur7.avi` se versiona tal cual. Otra versión de OpenCV podría codificar un archivo con
  bytes distintos al regenerarlo, y `prepare_inputs.py` avisa si eso ocurre.
