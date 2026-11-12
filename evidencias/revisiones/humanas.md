# Revisiones humanas de capturas (F3)

Generado con `python scripts/summarize_reviews.py` sobre la base real `evidencias/revisiones.db`. Estas revisiones las hizo la autora en el portal (`/capturas`); son distintas de la demostración automatizada de [`recorrido.md`](recorrido.md), que usa otra base (`demo.db`).

Las etiquetas describen lo que ve una persona en la imagen. No se usan como métrica de calidad ni cambian eventos, métricas o alertas.

**15 revisiones de 14 capturas, 1 con historial. 8 comprobaciones, 0 fallas.**

## Etiqueta vigente por ejecución

| Ejecución | Etiqueta | Capturas |
|---|---|---|
| `c2-baja-confianza-20261112T162525Z` | imagen_degradada | 10 |
| `s3-error-inferencia-20261112T205403Z` | confirma | 2 |
| `s3-error-inferencia-20261112T205403Z` | falso_positivo | 1 |
| `s3-error-inferencia-20261112T205403Z` | omision | 1 |

## Comprobaciones

| Comprobación | Esperado | Observado | Resultado |
|---|---|---|---|
| cada revisión apunta a un evento existente de su ejecución | 15 | 15 | ok |
| la imagen guardada es la del evento y el archivo existe | 15 | 15 | ok |
| las alertas guardadas con cada revisión son las que citan ese evento (alerts.jsonl) | 15 | 15 | ok |
| etiquetas dentro del catálogo y quien revisa identificado | 15 con etiqueta de ['confirma', 'falso_positivo', 'omision', 'imagen_degradada', 'dudosa'] | 15 | ok |
| registros de solo inserción: id y momento crecen juntos | orden creciente | creciente | ok |
| /api/revisiones devuelve las mismas revisiones en el mismo orden | 15 | 15 | ok |
| el resumen de revisión de cada alerta coincide con las revisiones vigentes | ['10 de 26', '10 de 26', '1 de 22'] | ['10 de 26', '10 de 26', '1 de 22'] | ok |
| historial de e00020: 2 revisiones y la vigente es la última | 2, vigente imagen_degradada | 2 | ok |

## Revisiones (`revisiones.db`)

| # | Momento (UTC) | Ejecución | Evento | Motivo de captura | Etiqueta | Revisa | Nota | Alertas del evento |
|---|---|---|---|---|---|---|---|---|
| 1 | `2026-11-12T21:25:44.017Z` | `c2-baja-confianza` | `e00019` | alerta (ok) | imagen_degradada | Andrea | — | a01, a02 |
| 2 | `2026-11-12T21:25:52.948Z` | `c2-baja-confianza` | `e00020` | muestra_normal (ok) | imagen_degradada | andrea | — | a01, a02 |
| 3 | `2026-11-12T21:26:07.131Z` | `c2-baja-confianza` | `e00020` | muestra_normal (ok) | imagen_degradada | Andrea | — | a01, a02 |
| 4 | `2026-11-12T21:26:16.518Z` | `c2-baja-confianza` | `e00021` | duda (ok) | imagen_degradada | Andrea | — | a01, a02 |
| 5 | `2026-11-12T21:26:26.447Z` | `c2-baja-confianza` | `e00024` | duda (ok) | imagen_degradada | Andrea | — | a01, a02 |
| 6 | `2026-11-12T21:26:33.832Z` | `c2-baja-confianza` | `e00027` | duda (ok) | imagen_degradada | Andrea | — | a01, a02 |
| 7 | `2026-11-12T21:26:44.629Z` | `c2-baja-confianza` | `e00030` | duda (ok) | imagen_degradada | Andrea | — | a01, a02 |
| 8 | `2026-11-12T21:26:52.263Z` | `c2-baja-confianza` | `e00033` | duda (ok) | imagen_degradada | Andrea | — | a01, a02 |
| 9 | `2026-11-12T21:27:01.766Z` | `c2-baja-confianza` | `e00036` | duda (ok) | imagen_degradada | Andrea | — | a01, a02 |
| 10 | `2026-11-12T21:29:49.952Z` | `c2-baja-confianza` | `e00039` | duda (ok) | imagen_degradada | Andrea | — | a01, a02 |
| 11 | `2026-11-12T21:30:01.924Z` | `c2-baja-confianza` | `e00040` | muestra_normal (ok) | imagen_degradada | Andrea | — | a01, a02 |
| 12 | `2026-11-12T21:41:02.792Z` | `s3-error-inferencia` | `e00099` | alerta (error) | omision | Andrea | — | a01 |
| 13 | `2026-11-12T21:41:18.936Z` | `s3-error-inferencia` | `e00100` | muestra_normal (ok) | confirma | Andrea | — | — |
| 14 | `2026-11-12T21:41:31.862Z` | `s3-error-inferencia` | `e00110` | muestra_normal (ok) | falso_positivo | Andrea | — | — |
| 15 | `2026-11-12T21:41:39.095Z` | `s3-error-inferencia` | `e00120` | muestra_normal (ok) | confirma | Andrea | — | — |

## Capturas

| Captura | Ruta | HTTP | Qué muestra |
|---|---|---|---|
| `humanas-01-galeria-revisadas.png` | `/capturas?review=confirma` | 200 | Galería filtrada por la etiqueta vigente de la última revisión |
| `humanas-02-historial.png` | `/capturas/c2-baja-confianza-20261112T162525Z-e00020` | 200 | Captura con más de una revisión: historial y vigente |
| `humanas-03-alerta.png` | `/alertas/c2-baja-confianza-20261112T162525Z-a01` | 200 | Resumen de revisión dentro de la alerta |
