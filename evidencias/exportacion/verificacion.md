# Exportación de eventos (F2) · verificación

Generado con `python scripts/verify_export.py --run-id c2-baja-confianza-20261112T162525Z --run-id s1-interrupcion-20261112T175603Z`.
Lo esperado se calcula filtrando `evidencias/runs/*/events.jsonl`, sin consultar SQLite.

**13 comprobaciones, 0 fallas.**

## Contenido exportado vs. esperado

| Filtros | Esperados (JSONL) | CSV | JSONL | `X-Export-Count` | Mismos ids y orden | Mismos campos | Resultado |
|---|---|---|---|---|---|---|---|
| `(sin filtros)` | 1388 | 1388 | 1388 | 1388 | sí | sí | ok |
| `{'run_id': 'c2-baja-confianza-20261112T162525Z'}` | 198 | 198 | 198 | 198 | sí | sí | ok |
| `{'run_id': 's1-interrupcion-20261112T175603Z'}` | 198 | 198 | 198 | 198 | sí | sí | ok |
| `{'run_id': 'c2-baja-confianza-20261112T162525Z', 'zone': 'low', 'captured': True}` | 13 | 13 | 13 | 13 | sí | sí | ok |
| `{'status': 'no_detections'}` | 3 | 3 | 3 | 3 | sí | sí | ok |
| `{'status': 'source_gap'}` | 160 | 160 | 160 | 160 | sí | sí | ok |
| `{'zone': 'accepted', 'captured': True}` | 89 | 89 | 89 | 89 | sí | sí | ok |
| `{'run_id': 's1-interrupcion-20261112T175603Z', 'status': 'source_gap'}` | 80 | 80 | 80 | 80 | sí | sí | ok |

## Estados vacío y de error

| Caso | Ruta | Parámetros | HTTP esperado | HTTP | Detalle | Resultado |
|---|---|---|---|---|---|---|
| formato no soportado | `/exportar/eventos.xml` | `{}` | 404 | 404 | formato no soportado: usa .csv o .jsonl | ok |
| estado desconocido | `/exportar/eventos.csv` | `{'status': 'perdido'}` | 422 | 422 | estado desconocido 'perdido'; opciones: ok, no_detections, error, source_gap | ok |
| zona desconocida | `/exportar/eventos.csv` | `{'zone': 'media'}` | 422 | 422 | zona desconocida 'media'; opciones: low, doubt, accepted | ok |
| ejecución inexistente | `/exportar/eventos.jsonl` | `{'run_id': 'no-existe'}` | 404 | 404 | ejecución inexistente: no-existe | ok |
| filtro válido sin resultados | `/exportar/eventos.csv` | `{'run_id': 'c2-baja-confianza-20261112T162525Z', 'status': 'error'}` | 200 | 200 | 0 eventos; 1 línea (encabezado) | ok |

## Ejemplos y capturas

- [`ejemplo-c2-baja-confianza-20261112T162525Z-low-captura.csv`](ejemplo-c2-baja-confianza-20261112T162525Z-low-captura.csv) y `.jsonl`: eventos de zona baja con captura. Cada fila conserva `config_ref`, `model_ref`, `model_sha256`, `window_id`, `image_ref` y las detecciones con puntuación, zona y caja.
- `01-eventos-con-exportar.png`: Vista /eventos filtrada; el enlace CSV descargó «eventos-c2-baja-confianza-20261112T162525Z-low-captura.csv»
