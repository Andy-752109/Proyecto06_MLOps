# Recorrido del portal

Generado con `python scripts/capture_portal.py --c1 c1-normal-20261112T162444Z --c2 c2-baja-confianza-20261112T162525Z`.
El script levanta `uvicorn monitor.portal.app:app`, visita cada URL con Chromium headless y guarda la página completa. Para repetirlo manualmente: `uvicorn monitor.portal.app:app --port 8000` y abrir las mismas rutas.

| Captura | Ruta | HTTP | Qué acredita |
|---|---|---|---|
| `01-inicio.png` | `/` | 200 | Ejecuciones (reference, C1, C2) y últimas alertas |
| `02-c1-eventos.png` | `/eventos?run_id=c1-normal-20261112T162444Z` | 200 | C1 · consulta de eventos |
| `03-c1-evento.png` | `/eventos/c1-normal-20261112T162444Z-e00020` | 200 | C1 · evento con captura de muestra normal, detecciones y zonas |
| `04-c1-ejecucion.png` | `/ejecuciones/c1-normal-20261112T162444Z` | 200 | C1 · ventanas, métricas base por ventana y alertas (ninguna) |
| `05-c1-alertas.png` | `/alertas?run_id=c1-normal-20261112T162444Z` | 200 | C1 · consulta de alertas (vacía conforme a la regla) |
| `06-c2-eventos-baja.png` | `/eventos?run_id=c2-baja-confianza-20261112T162525Z&zone=low&captured=true` | 200 | C2 · eventos de zona baja con captura |
| `07-c2-evento.png` | `/eventos/c2-baja-confianza-20261112T162525Z-e00003` | 200 | C2 · evento de baja confianza con captura y alerta vinculada |
| `08-c2-alertas.png` | `/alertas?run_id=c2-baja-confianza-20261112T162525Z` | 200 | C2 · alertas: momento, motivo, severidad, acción sugerida |
| `09-c2-alerta.png` | `/alertas/c2-baja-confianza-20261112T162525Z-a01` | 200 | C2 · alerta de baja confianza: regla, ventanas, capturas y eventos |
| `10-c2-ventana.png` | `/ventanas/c2-baja-confianza-20261112T162525Z-w000` | 200 | C2 · ventana que dispara la alerta: métricas y evaluación de reglas |
| `11-c2-ejecucion.png` | `/ejecuciones/c2-baja-confianza-20261112T162525Z` | 200 | C2 · ventanas, métricas base y alertas |
