# Revisión manual de capturas (F3) · recorrido

Generado con `python scripts/demo_reviews.py --c2 c2-baja-confianza-20261112T162525Z`. Base de revisiones de demostración `evidencias/revisiones/demo.db` (la real, `evidencias/revisiones.db`, no se toca).

> Demostración automatizada del flujo: C2 usa la entrada desenfocada (sigma=7) por construcción; no es una revisión humana.

**9 comprobaciones, 0 fallas.**

| Comprobación | Esperado | Observado | Resultado |
|---|---|---|---|
| guardar sin etiqueta se rechaza y no se guarda | No se guardó | No se guardó | ok |
| revisiones guardadas = envíos aceptados | 5 | 5 | ok |
| orden y etiquetas guardadas = enviadas | [['c2-baja-confianza-20261112T162525Z-e00000', 'imagen_degradada'], ['c2-baja-confianza-20261112T162525Z-e00003', 'imagen_degradada'], ['c2-baja-confianza-20261112T162525Z-e00006', 'imagen_degradada'], ['c2-baja-confianza-20261112T162525Z-e00009', 'imagen_degradada'], ['c2-baja-confianza-20261112T162525Z-e00000', 'dudosa']] | [['c2-baja-confianza-20261112T162525Z-e00000', 'imagen_degradada'], ['c2-baja-confianza-20261112T162525Z-e00003', 'imagen_degradada'], ['c2-baja-confianza-20261112T162525Z-e00006', 'imagen_degradada'], ['c2-baja-confianza-20261112T162525Z-e00009', 'imagen_degradada'], ['c2-baja-confianza-20261112T162525Z-e00000', 'dudosa']] | ok |
| resumen de la alerta = revisiones vigentes de sus capturas | 4 de 26 | 4 de 26 | ok |
| cada revisión conserva image_ref y las alertas del evento | True | True | ok |
| evento sin captura → 409 | 409 | 409 | ok |
| etiqueta desconocida → 422 | 422 | 422 | ok |
| evento inexistente → 404 | 404 | 404 | ok |
| la base de monitoreo no cambia (solo lectura) | 0 | 0 | ok |

## Revisiones guardadas (`/api/revisiones`)

| # | Evento | Etiqueta | Revisa | Alertas del evento |
|---|---|---|---|---|
| 1 | `e00000` | imagen_degradada | demo-automatizada | a01, a02 |
| 2 | `e00003` | imagen_degradada | demo-automatizada | a01, a02 |
| 3 | `e00006` | imagen_degradada | demo-automatizada | a01, a02 |
| 4 | `e00009` | imagen_degradada | demo-automatizada | a01, a02 |
| 5 | `e00000` | dudosa | demo-automatizada | a01, a02 |

## Capturas

| Captura | Ruta | Qué muestra |
|---|---|---|
| `01-galeria-sin-revisar.png` | `/capturas?run_id=c2-baja-confianza-20261112T162525Z&review=sin_revisar` | Galería de capturas de C2 sin revisar |
| `02-error-sin-etiqueta.png` | `/capturas/c2-baja-confianza-20261112T162525Z-e00000/revision` | Intento sin etiqueta: se rechaza (HTTP 422) y no se guarda nada |
| `03-guardado-y-siguiente.png` | `/capturas/c2-baja-confianza-20261112T162525Z-e00003?guardado=1` | Tras guardar, el portal abre la siguiente captura sin revisar |
| `04-historial.png` | `/capturas/c2-baja-confianza-20261112T162525Z-e00000?guardado=1` | La misma captura re-etiquetada: historial con 2 revisiones; vigente la última |
| `05-alerta-con-revisiones.png` | `/alertas/c2-baja-confianza-20261112T162525Z-a01` | La alerta resume cuántas de sus capturas están revisadas y con qué etiqueta |
| `06-galeria-filtrada.png` | `/capturas?run_id=c2-baja-confianza-20261112T162525Z&review=imagen_degradada` | Galería filtrada por etiqueta vigente imagen_degradada |
