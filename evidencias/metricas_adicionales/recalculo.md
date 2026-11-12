# Recálculo independiente de M1–M3

Generado con `python scripts/recalc_extra.py --run-id reference-20261112T162358Z --run-id c1-normal-20261112T162444Z --run-id c2-baja-confianza-20261112T162525Z --run-id s1-interrupcion-20261112T175603Z --run-id s2-cambio-sostenido-20261112T181053Z --run-id s3-error-inferencia-20261112T205403Z`.
Implementación aparte con pandas/numpy (`np.histogram` para M3, `diff` de `frame_index` para M2); tolerancia 1e-3 (los valores guardados están redondeados).

| Ejecución | Comprobaciones | Diferencias |
|---|---|---|
| `reference-20261112T162358Z` | 30 | 0 |
| `c1-normal-20261112T162444Z` | 30 | 0 |
| `c2-baja-confianza-20261112T162525Z` | 30 | 0 |
| `s1-interrupcion-20261112T175603Z` | 30 | 0 |
| `s2-cambio-sostenido-20261112T181053Z` | 30 | 0 |
| `s3-error-inferencia-20261112T205403Z` | 30 | 0 |

**Total: 180 comprobaciones, 0 diferencias.**
