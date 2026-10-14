# NEXT_STEPS — Aliado Libre

Estado al 13-oct-2026. El cruce completo con el documento de recomendaciones
externas está en `docs/RECOMENDACIONES_TRIAGE.md` (histórico, 29-sep).

## Bloqueado en Fabián

1. ~~Elegir licencia~~: código AGPL-3.0; datos gratis para personas y de pago para uso comercial o a escala (29-sep).
2. **Revisar las 47 abstenciones** (`finetune/eval/revision_abstenciones.html`,
   se regenera con `revisar_abstenciones.py`). Decide el umbral de abstención,
   que hoy mide coincidencia léxica y no relevancia. **Es lo que más mueve la
   cobertura**: el corpus ya tiene la respuesta en casos donde la app calla.
3. **Revisión humana de 20 casos** (`finetune/eval/revision_humana.html`),
   pendiente desde el 7-sep.
4. **CSV del Planificador de Palabras Clave de Google Ads** (interfaz web,
   ubicación Colombia) con las 1.276 consultas cosechadas.
5. ~~Autorizar el push~~: hecho el 13-oct (15 commits, hasta `af94ce9`).

## Siguiente tarea técnica

1. **Ingerir las 191 sentencias de la Corte que faltan** (2023: 118, 2026: 68;
   ver banner del 13-oct en `docs/PROJECT_STATE.md`): crawl acotado
   (`ingest/fuentes/corte_constitucional.py:crawl(anio_inicio=2023)`), fusionar
   con el corpus y **reindexar con GPU** — es trabajo de horas, confirmar que
   no hay otra sesión usando el índice antes de lanzarlo.
2. **Destilado CERRADO, no retomar** sin una idea nueva de por qué no gana al
   bge sin afinar (confirmado dos veces, dos jueces independientes).
3. **Troceo por artículo** como experimento de una sola variable, sobre el
   corpus vigente.
4. Recompilar el `.exe` si se va a distribuir: lleva 15 commits de cambios
   desde la última verificación (7-oct, índice reinstalado) sin recompilar.
5. **Publicar el índice ampliado** en HF si se va a desplegar el servidor
   (el actual del 7-oct ya incluye Corte con texto completo + Superservicios).

## Mantenimiento

- Reconstruir la tabla de vigencia tras cualquier reindexado o cada mes:
  `scripts/descargar_suin_vigencias.py` y luego `python -m index.build_vigencia`.
