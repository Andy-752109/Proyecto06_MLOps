# Filtros avanzados de eventos (F5) · verificación

Generado con `python scripts/verify_filters.py --c2 c2-baja-confianza-20261112T162525Z --s3 s3-error-inferencia-20261112T205403Z`.
Lo esperado se calcula filtrando y ordenando `evidencias/runs/*/events.jsonl` y `alerts.jsonl` en Python, sin consultar SQLite; se compara con `/api/eventos` (todas las páginas), `/exportar/eventos.csv` y el conteo que muestra `/eventos`.

**25 comprobaciones, 0 fallas.**

## Resultados y orden

| Consulta | Filtros | Esperados (JSONL) | API | CSV | Página | Mismos ids y orden | Primeros | Resultado |
|---|---|---|---|---|---|---|---|---|
| rango de puntuación en zona de duda | `{"run_id": "c2-baja-confianza-20261112T162525Z", "score_min": 0.4, "score_max": 0.7}` | 158 | 158 | 158 | 158 | sí | e00000, e00010, e00012 | ok |
| puntuación ≥ 0.8 en todas las ejecuciones, orden ↓ | `{"score_min": 0.8, "sort": "score_desc"}` | 790 | 790 | 790 | 790 | sí | e00046, e00007, e00127 | ok |
| puntuación baja ↑ (los eventos sin puntuación no entran) | `{"score_max": 0.3, "sort": "score_asc"}` | 13 | 13 | 13 | 13 | sí | e00003, e00007, e00041 | ok |
| frames concurridos: ≥ 8 detecciones, orden por detecciones | `{"dets_min": 8, "sort": "dets_desc"}` | 308 | 308 | 308 | 308 | sí | e00072, e00073, e00085 | ok |
| pocas detecciones en C2 (0 a 1) | `{"run_id": "c2-baja-confianza-20261112T162525Z", "dets_min": 0, "dets_max": 1}` | 10 | 10 | 10 | 10 | sí | e00001, e00002, e00003 | ok |
| intervalo de captura (ventanas 2–3 de C2) | `{"since": "2026-11-12T16:25:33.938Z", "until": "2026-11-12T16:25:41.741Z"}` | 40 | 40 | 40 | 40 | sí | e00040, e00041, e00042 | ok |
| hasta la mitad de C2, más recientes primero | `{"run_id": "c2-baja-confianza-20261112T162525Z", "until": "2026-11-12T16:25:45.738Z", "sort": "recent"}` | 100 | 100 | 100 | 100 | sí | e00099, e00098, e00097 | ok |
| ventana 3 de S3 (solo errores) | `{"run_id": "s3-error-inferencia-20261112T205403Z", "window": 3}` | 20 | 20 | 20 | 20 | sí | e00060, e00061, e00062 | ok |
| motivo de captura 'error' | `{"reason": "error"}` | 17 | 17 | 17 | 17 | sí | e00050, e00053, e00056 | ok |
| eventos que sustentan alguna alerta en C2 | `{"run_id": "c2-baja-confianza-20261112T162525Z", "in_alert": true}` | 178 | 178 | 178 | 178 | sí | e00000, e00001, e00002 | ok |
| id contiene e0004 | `{"run_id": "c2-baja-confianza-20261112T162525Z", "q": "e0004"}` | 10 | 10 | 10 | 10 | sí | e00040, e00041, e00042 | ok |
| inferencia más lenta primero (nulos al final) | `{"run_id": "s3-error-inferencia-20261112T205403Z", "sort": "inference_desc"}` | 198 | 198 | 198 | 198 | sí | e00000, e00127, e00100 | ok |
| extremo a extremo más lento primero | `{"run_id": "c2-baja-confianza-20261112T162525Z", "sort": "e2e_desc"}` | 198 | 198 | 198 | 198 | sí | e00000, e00001, e00002 | ok |
| combinada: C2, baja, con captura, en alerta, 2–6 detecciones, ↓ | `{"run_id": "c2-baja-confianza-20261112T162525Z", "zone": "low", "captured": true, "in_alert": true, "dets_min": 2, "dets_max": 6, "sort": "score_desc"}` | 12 | 12 | 12 | 12 | sí | e00180, e00040, e00009 | ok |
| agregar filtros solo reduce el resultado (C2 → baja → captura → alerta → s ≤ 0.35) | `{"run_id": "c2-baja-confianza-20261112T162525Z", "zone": "low", "captured": true, "in_alert": true, "score_max": 0.35}` | [198, 25, 13, 13, 8] | [198, 25, 13, 13, 8] | — | — | sí | — | ok |
| cada etiqueta × quita solo su filtro | `{"run_id": "c2-baja-confianza-20261112T162525Z", "zone": "low", "captured": true}` | [['run_id'], ['zone'], ['captured']] | [['run_id'], ['zone'], ['captured']] | — | 3 | sí | — | ok |

## Estados vacío y de error

| Caso | Ruta | Parámetros | HTTP esperado | HTTP | Texto esperado | Resultado |
|---|---|---|---|---|---|---|
| rango de puntuación invertido (página) | `/eventos` | `{"score_min": 0.9, "score_max": 0.1}` | 422 | 422 | `es mayor que` | ok |
| puntuación fuera de [0, 1] (API) | `/api/eventos` | `{"score_min": 1.5}` | 422 | 422 | `fuera del rango` | ok |
| puntuación no numérica (exportación) | `/exportar/eventos.csv` | `{"score_max": "alta"}` | 422 | 422 | `no es un número` | ok |
| fecha inválida (página) | `/eventos` | `{"since": "ayer"}` | 422 | 422 | `fecha inválida` | ok |
| intervalo invertido (API) | `/api/eventos` | `{"since": "2026-11-12T16:25:41.741Z", "until": "2026-11-12T16:25:33.938Z"}` | 422 | 422 | `es mayor que` | ok |
| orden desconocido (API) | `/api/eventos` | `{"sort": "azar"}` | 422 | 422 | `orden desconocido` | ok |
| detecciones negativas (página) | `/eventos` | `{"dets_min": -1}` | 422 | 422 | `fuera del rango` | ok |
| consulta válida sin resultados (página) | `/eventos` | `{"run_id": "c2-baja-confianza-20261112T162525Z", "status": "error"}` | 200 | 200 | `Ningún evento coincide` | ok |
| consulta válida sin resultados (API) | `/api/eventos` | `{"score_min": 0.99}` | 200 | 200 | `"total":0` | ok |

## Capturas

| Captura | Ruta | HTTP | Qué muestra |
|---|---|---|---|
| `01-inicio.png` | `/` | 200 | Inicio rediseñado: indicadores, una tarjeta por ejecución con low_prop por ventana y últimas alertas |
| `02-filtros-avanzados.png` | `/eventos?run_id=c2-baja-confianza-20261112T162525Z&zone=low&captured=true&in_alert=true&dets_min=2&dets_max=6&sort=score_desc` | 200 | Consulta combinada con el panel avanzado abierto, etiquetas de filtros activos y orden por puntuación |
| `03-error-rango.png` | `/eventos?score_min=0.9&score_max=0.1` | 422 | Rango invertido: HTTP 422 con explicación, sin resultados |
| `04-vacio.png` | `/eventos?run_id=c2-baja-confianza-20261112T162525Z&status=error` | 200 | Consulta válida sin resultados: estado vacío |
| `05-ventana-s3.png` | `/eventos?run_id=s3-error-inferencia-20261112T205403Z&window=3` | 200 | Ventana 3 de S3: todos los eventos con error de inferencia |
| `06-alertas.png` | `/alertas?severity=high` | 200 | Alertas filtradas por severidad alta |
