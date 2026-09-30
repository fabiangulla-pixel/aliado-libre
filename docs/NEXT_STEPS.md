# NEXT_STEPS — Aliado Libre

Estado al 29-sep-2026. El cruce completo con el documento de recomendaciones
externas está en `docs/RECOMENDACIONES_TRIAGE.md`.

## Bloqueado en Fabián

1. ~~Elegir licencia~~: AGPL-3.0 + CC BY-SA 4.0 (29-sep).
2. **Revisar las 47 abstenciones** (`finetune/eval/revision_abstenciones.html`,
   se regenera con `revisar_abstenciones.py`). Decide el umbral de abstención,
   que hoy mide coincidencia léxica y no relevancia. **Es lo que más mueve la
   cobertura**: el corpus ya tiene la respuesta en casos donde la app calla.
3. **Revisión humana de 20 casos** (`finetune/eval/revision_humana.html`),
   pendiente desde el 7-sep.
4. **CSV del Planificador de Palabras Clave de Google Ads** (interfaz web,
   ubicación Colombia) con las 1.276 consultas cosechadas.
5. **Autorizar el push** de los commits locales.

## Siguiente tarea técnica

1. **Medir la guarda de vigencia de punta a punta**: repetir el piloto de 100
   consultas con `correr_piloto.py --ejecutar` (~0,43 USD con Haiku 4.5; pedir
   confirmación). El prompt cambió el 29-sep (línea de vigencia y delimitadores
   `<documento>`): las cifras del 12-sep ya no describen el sistema.
2. ~~Ingerir por demanda~~: la Ley 142 de 1994 y la 1328 de 2009 YA estaban;
   el 0/37 es recuperación + umbral. Hecho en cambio: 273 leyes recientes
   (29-sep). Corpus vigente `1199645cc8a5a1ce`.
3. **Troceo por artículo** como experimento de una sola variable, sobre el
   corpus `e422ffbae7186cb8`.
4. ~~Recompilar el .exe~~: hecho el 29-sep, verificado abriendo el PYZ.
5. **Publicar el índice ampliado** en HF si se va a desplegar el servidor.

## Mantenimiento

- Reconstruir la tabla de vigencia tras cualquier reindexado o cada mes:
  `scripts/descargar_suin_vigencias.py` y luego `python -m index.build_vigencia`.
