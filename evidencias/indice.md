# Índice de evidencias · Proyecto 6

**Estudiante:** Andrea Lizeth Arevalo Solis (752109) · **Repositorio:** https://github.com/Andy-752109/Proyecto06_MLOps

## Revisiones Git y relación con las evidencias

| Commit | Contenido | Ejecuciones hechas sobre él |
|---|---|---|
| `6b84820` | Todo el código, la configuración, el modelo, los videos y la documentación base | `reference-20261112T162358Z` |
| `872e7c5` | Agrega `config/reference.json` y la justificación de umbrales, generados por la ejecución de referencia. **No cambia código** | `c1-normal-20261112T162444Z`, `c2-baja-confianza-20261112T162525Z` |
| `0c66e90` | Agrega las ejecuciones C1/C2, el recálculo, las capturas del portal y este índice. **No cambia** `src/`, `config/`, `scripts/` ni `modelo/` | — |
| `07e0e17` | Adicional S1 (cambia código) | `s1-interrupcion-20261112T175603Z` |
| `257712f` | Adicional S2 (cambia código) | `s2-cambio-sostenido-20261112T181053Z` |
| `e244ed1` | Adicionales F2–F4 (cambia código) | `s1-interrupcion-20261112T185945Z` (evidencia de la vista en vivo) |
| `84b576a` | Adicional S3 (`619618b`), portal rediseñado y adicional F5 (cambian código) | `s3-error-inferencia-20261112T205403Z` |

Las demás revisiones posteriores (F1, M1–M3 y correcciones menores) agregan código o
evidencia, pero no generan ejecuciones nuevas; el detalle de cada adicional está en
[`EXTRAS.md`](../EXTRAS.md). Tras rediseñar el portal (`84b576a`) se volvieron a ejecutar las
verificaciones con capturas de pantalla (recorrido base, F1, F2, F3, S1, S2), así que sus
imágenes muestran la interfaz actual con los mismos resultados (0 fallas). Las capturas de la
vista en vivo (F4) son anteriores al rediseño: regenerarlas exige una ejecución nueva.

Cada `manifest.json` registra `git_commit` y `git_dirty`. Todas las ejecuciones versionadas
tienen `git_dirty = false`, porque se hicieron con `src/ config/ scripts/ modelo/` sin cambios
pendientes. El código de la base que generó C1/C2 es `872e7c5`
(`git diff 872e7c5 HEAD -- src config scripts modelo` muestra solo lo que agregaron los
adicionales). Para comprobar que esos cambios no alteran la base, C1 y C2 se volvieron a
ejecutar con el código de `004cd03` en una copia aparte: los 198 eventos de cada una tienen las
mismas detecciones, puntuaciones y zonas, y las ventanas y alertas coinciden (C1: 0, C2: 4).

Identidad común a las tres ejecuciones:

- `config_ref = cfg-517d02606b3e`
- modelo `yolov8n@sha256:f59b3d833e2f` (SHA-256 completo `f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36`)
- entorno: Python 3.12.16, torch 2.15.0, ultralytics 8.4.211, CPU, macOS arm64

## Ejecuciones

| Run | Escenario | Fuente (frames) | Eventos | Detecciones | low / doubt / accepted | low_prop | Sin detecciones | Capturas | Alertas |
|---|---|---|---|---|---|---|---|---|---|
| [`reference-20261112T162358Z`](runs/reference-20261112T162358Z/) | referencia | `vtest.avi` 0–399 | 200 | 1446 | 264 / 183 / 999 | 0.183 | 0 | 20 | (reglas no evaluadas) |
| [`c1-normal-20261112T162444Z`](runs/c1-normal-20261112T162444Z/) | C1 | `vtest.avi` 400–794 | 198 | 1220 | 111 / 107 / 1002 | 0.091 | 0 | 20 | 0 |
| [`c2-baja-confianza-20261112T162525Z`](runs/c2-baja-confianza-20261112T162525Z/) | C2 | `vtest_blur7.avi` 400–794 | 198 | 841 | 510 / 317 / 14 | 0.606 | 3 | 82 | 4 |

Archivos de cada run: `manifest.json` (comando, commit, fuente con SHA-256, modelo, entorno,
referencia, resumen), `config.snapshot.json`, `events.jsonl`, `detections.jsonl`,
`windows.jsonl`, `metrics.jsonl`, `rule_evaluations.jsonl`, `alerts.jsonl`,
`resources.jsonl` y `capturas/*.jpg`. La base consultada por el portal es `evidencias/monitor.db`.

## C1 · Operación normal

- **Entrada**: `data/videos/vtest.avi` (SHA-256 `45cddc94…16cf`), frames 400–794, a 10 fps
  nativos con muestreo 1 de cada 2. Se leyeron 395 frames, 198 se infirieron y 197 se
  descartaron por muestreo (0 por saturación).
- **Comando**: `python -m monitor.pipeline --scenario c1-normal`
- **Esperado**: inferencias reales, la mayoría de las detecciones aceptadas, eventos
  persistidos, métricas coherentes y ninguna alerta que la regla no justifique.
- **Observado**: 198 eventos `ok`. Las 1220 detecciones se reparten en 82 % aceptadas, 9 %
  de duda y 9 % bajas. `low_prop` por ventana va de 0.026 a 0.156 (umbral de alerta 0.40;
  referencia 0.183). Las 10 ventanas son elegibles. Las 30 evaluaciones de reglas dieron
  `not_met` (`rule_evaluations.jsonl`), así que no hay alertas porque **la regla no se
  cumplió**, y no por falta de datos. Las métricas base de C1 están abajo.
- **Portal**: [02-c1-eventos](portal/02-c1-eventos.png), [03-c1-evento](portal/03-c1-evento.png),
  [04-c1-ejecucion](portal/04-c1-ejecucion.png), [05-c1-alertas](portal/05-c1-alertas.png).
- **Recálculo**: [recalculo/c1-normal-20261112T162444Z.md](recalculo/c1-normal-20261112T162444Z.md), 113 comprobaciones y 0 diferencias.

## C2 · Baja confianza

- **Entrada**: `data/videos/vtest_blur7.avi` (SHA-256 `d625c3a9…1ad1861`). Es el mismo
  tramo de C1 con desenfoque gaussiano σ=7, generado por `scripts/prepare_inputs.py` para
  simular una lente desenfocada. **Las puntuaciones salen del modelo y no se modifican.**
  Los umbrales (0.40/0.70) y las reglas se fijaron en `872e7c5`, antes de ejecutar C2.
- **Comando**: `python -m monitor.pipeline --scenario c2-baja-confianza`
- **Esperado**: la política clasifica las detecciones en la zona baja, conserva capturas y
  eventos, y `baja-confianza-v1` se dispara en cuanto una ventana elegible tiene `low_prop ≥ 0.40`.
- **Observado**: 61 % de las detecciones quedan en zona baja, 38 % en duda y 2 % aceptadas.
  Hay 3 frames `no_detections`, registrados aparte y sin puntuación. Hubo 82 capturas:
  56 de duda, 8 de baja confianza, 14 de muestra normal, 3 de alerta y 1 sin detecciones.

| Alerta | Regla | Severidad | Abre en | Resuelve en | Estado final |
|---|---|---|---|---|---|
| [`…-a01`](portal/09-c2-alerta.png) | `baja-confianza-v1` | warning | w000 (`low_prop` 22/34 = 0.647) | w003 (0.289 < 0.40) | resolved |
| `…-a02` | `cambio-sostenido-v1` | high | w002 (deltas +0.464, +0.350, +0.401 sobre 0.183 en w000–w002) | w003 | resolved |
| `…-a03` | `baja-confianza-v1` | warning | w004 (0.614) | — | open al terminar |
| `…-a04` | `cambio-sostenido-v1` | high | w006 (w004–w006) | — | open al terminar |

- **Portal**: [06-c2-eventos-baja](portal/06-c2-eventos-baja.png), [07-c2-evento](portal/07-c2-evento.png),
  [08-c2-alertas](portal/08-c2-alertas.png), [09-c2-alerta](portal/09-c2-alerta.png),
  [10-c2-ventana](portal/10-c2-ventana.png), [11-c2-ejecucion](portal/11-c2-ejecucion.png).
  El recorrido completo está en [portal/recorrido.md](portal/recorrido.md).
- **Recálculo**: [recalculo/c2-baja-confianza-20261112T162525Z.md](recalculo/c2-baja-confianza-20261112T162525Z.md), 113 comprobaciones y 0 diferencias. Incluye la comprobación de que `baja-confianza-v1` debía abrirse exactamente en w000 y w004.

## Cadena de una muestra (C2)

1. **Frame**: `video-vtest-blur7-f00406`, índice 406 de `vtest_blur7.avi`, capturado a las `2026-11-12T16:25:26.541Z`.
2. **Inferencia → evento** `c2-baja-confianza-20261112T162525Z-e00003`: `status ok`, una
   detección `…-e00003-d00` de clase `person` con `score 0.1095` → zona **low**, `config_ref cfg-517d02606b3e`.
3. **Captura**: `evidencias/runs/c2-baja-confianza-20261112T162525Z/capturas/c2-baja-confianza-20261112T162525Z-e00003.jpg`,
   motivo `baja_confianza`.
4. **Ventana** `…-w000`: 20 frames válidos (3 sin detecciones), 34 detecciones, 22 bajas,
   `low_prop 0.647059`, estado `eligible`.
5. **Alerta** `c2-baja-confianza-20261112T162525Z-a01` (`baja-confianza-v1`, warning). Lista
   `e00003` en `event_ids` y la imagen en `image_refs`. El portal la muestra en [07-c2-evento](portal/07-c2-evento.png) y [09-c2-alerta](portal/09-c2-alerta.png).

Recálculo manual de esa ventana desde los datos primarios:

```bash
python -c "
import json
W='c2-baja-confianza-20261112T162525Z-w000'
ev=[json.loads(l) for l in open('evidencias/runs/c2-baja-confianza-20261112T162525Z/events.jsonl')]
v=[e for e in ev if e['window_id']==W and e['status'] in ('ok','no_detections')]
s=[d['score'] for e in v for d in e['detections']]
print(len(v), len(s), sum(x<0.40 for x in s), round(sum(x<0.40 for x in s)/len(s),6), sum(e['status']=='no_detections' for e in v))"
# → 20 34 22 0.647059 3   (frames válidos, detecciones, bajas, low_prop, frames sin detecciones)
```

## Métricas base (G1–G7): resultados por ventana

Las definiciones están en [docs/metricas.md](../docs/metricas.md). Cada valor está en
`runs/<run>/metrics.jsonl` y se recalcula en `recalculo/<run>.md`.

| Grupo | Métrica base | C1 (mín–máx en 10 ventanas) | C2 (mín–máx en 10 ventanas) |
|---|---|---|---|
| G1 | `g1_inference_ms_p95` (ms) | 44.2 – 50.1 | 43.7 – 50.7 |
| G2 | `g2_processing_fps` (frames/s) | 4.98 – 5.89 | 4.98 – 5.95 |
| G3 | `g3_rss_mb_max` (MiB) | 438.6 – 455.0 | 217.5 – 436.2 |
| G4 | `g4_low_conf_prop` | 0.026 – 0.156 | 0.289 – 0.724 |
| G5 | `g5_trace_coverage` | 1.000 en todas | 1.000 en todas |
| G6 | `g6_model_version_match` | 1.000 en todas | 1.000 en todas |
| G7 | `g7_active_alerts` | 0 en todas | 0 – 2 |

La primera ventana de cada run supera los 5 fps nominales porque los frames que se acumularon
en la cola durante el arranque del modelo se procesan seguidos. Todas las métricas tienen
`status = ok` en C1/C2.

## Mapa de criterios

| Criterio | Evidencia |
|---|---|
| R1.1 Stream y muestreo | `src/monitor/source.py`; `config/scenarios.yaml` (`playback`, `sample_every`, `queue_maxsize`); `manifest.json → summary.source` (frames leídos, seleccionados y descartados por motivo) |
| R1.2 Inferencia real | `src/monitor/detector.py`; `events.jsonl → detections[]` con puntuaciones crudas; `model_sha256` en cada evento |
| R1.3 Identidad del modelo | README (tabla y procedencia); `config/monitor.yaml → model`; `docs/politica.md §1`; `manifest.json → model_ref, model_sha256, environment` |
| R2 Métricas | `docs/metricas.md`; `metrics.jsonl`; `scripts/recalc_metrics.py`; `recalculo/*.md` |
| R3.1 Umbrales justificados | `config/monitor.yaml → policy`; `referencia/justificacion-umbrales.md`; `runs/reference-…/` |
| R3.2 Tres zonas | `src/monitor/policy.py`; `detections[].zone`; estados `no_detections`/`error` aparte; piso 0.10 y NMS en `docs/politica.md §1–2` |
| R3.3 Referencia y regla sostenida | `config/reference.json`; `windows` (20, mín. 15 frames y 30 detecciones); `cambio-sostenido-v1`; `insufficient_evidence` en `src/monitor/rules.py` y en las pruebas |
| R4.1 Eventos | `events.jsonl`; esquema en `docs/politica.md §7` |
| R4.2 Persistencia y portal | `evidencias/monitor.db`; `/eventos`, `/eventos/{id}`; [portal/](portal/) |
| R4.3 Capturas | `docs/politica.md §6`; `runs/*/capturas/`; G5 = 1.0 (todas las `image_ref` resuelven) |
| R5.1 Reglas | `config/monitor.yaml → alerts`; `docs/politica.md §4–5` |
| R5.2 Alertas desde observaciones | `alerts.jsonl` (`window_ids`, `event_ids`, `observed`, `config_ref`); `rule_evaluations.jsonl` |
| R5.3 Alertas en el portal | `/alertas`, `/alertas/{id}`; [08-c2-alertas](portal/08-c2-alertas.png) |
| R6.1 / R6.2 | Secciones C1 y C2 de este índice |
| R7.1 Reproducción | README (Instalación y Ejecución); `requirements.txt`; `pyproject.toml` |
| R7.2 Evidencias | Este índice; `recalculo/`; `portal/recorrido.md` |
| R7.3 Autoría | README (Autoría y componentes reutilizados) |
| Extras | [`EXTRAS.md`](../EXTRAS.md): F1–F5, S1–S3 y M1–M3, cada uno con su verificación |

## Cómo reproducir y verificar

Conviene hacerlo en una copia nueva del repositorio, para no mezclar ejecuciones nuevas con
las versionadas:

```bash
git clone https://github.com/Andy-752109/Proyecto06_MLOps.git p6 && cd p6
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .
python scripts/prepare_inputs.py                     # verifica SHA-256 de entradas y modelo
python -m pytest -q                                  # 59 pruebas
python scripts/recalc_metrics.py --run-id reference-20261112T162358Z \
  --run-id c1-normal-20261112T162444Z --run-id c2-baja-confianza-20261112T162525Z   # 0 diferencias
python -m monitor.pipeline --scenario c1-normal       # nueva ejecución C1 (≈40 s)
python -m monitor.pipeline --scenario c2-baja-confianza
uvicorn monitor.portal.app:app --port 8000            # consultar /eventos y /alertas
```

En CPU, las puntuaciones son deterministas para el mismo modelo, entrada y versiones:
`reference` produjo exactamente las mismas cifras en dos ejecuciones durante el desarrollo.
Los tiempos y la memoria dependen del equipo.
