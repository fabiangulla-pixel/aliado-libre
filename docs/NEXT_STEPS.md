# NEXT_STEPS — Aliado Libre

Estado al 14-nov-2026. El cruce con el documento de recomendaciones externas
está en `docs/RECOMENDACIONES_TRIAGE.md` (histórico, 29-sep).

## Bloqueado en Fabián

1. **Revisar las 47 abstenciones** (`finetune/eval/revision_abstenciones.html`,
   se regenera con `revisar_abstenciones.py`). Decide el umbral de abstención,
   que hoy mide coincidencia léxica y no relevancia. **Es lo que más mueve la
   cobertura**: el corpus ya tiene la respuesta en casos donde la app calla.
2. **Revisión humana de 20 casos** (`finetune/eval/revision_humana.html`),
   pendiente desde el 7-sep.
3. **Términos y privacidad** (`gui/static/terminos.html`, `privacidad.html`):
   siguen siendo borradores; idealmente con abogado.
4. **Licencia de los normogramas de Avance Jurídico** (ver `docs/fuentes.md`,
   14-nov): afecta a la DIAN ya indexada y a los conceptos de MinTrabajo.
5. Enlace de aporte (`ALIADO_ENLACE_PAGO`), prueba desde el celular con datos
   móviles y pasar el índice de Hugging Face a acceso con registro.
6. CSV del Planificador de Palabras Clave de Google Ads (1.276 consultas).

## En curso (14-nov)

- Descargas completas en segundo plano, reanudables, logs en `_run/crawl_*_14nov.log`:
  Superfinanciera (~17 h), Corte Suprema Laboral+Civil (días; progreso por año
  en `data/raw/corte_suprema_progreso.json`). Relanzar el mismo comando si se
  cortan: no repiten trabajo.
- Tras cada tanda: `scripts/anonimizar_raw.py sic supersociedades superfinanciera`
  y `reindexar_con_gpu.py --ampliar`, luego `python -m index.resolver_citas --construir`
  y `python -m index.build_vigencia`.

## Siguiente tarea técnica

1. Cuando terminen las descargas: reindexado final, recompilar el `.exe` y
   publicar el índice ampliado en HF (decidir antes el acceso con registro).
2. **Troceo por artículo** como experimento de una sola variable.
3. Consejo de Estado: localizar el buscador nuevo (ago-2026).
4. **Destilado CERRADO**, no retomar sin una idea nueva.

## Mantenimiento

- Reconstruir la tabla de vigencia tras cualquier reindexado o cada mes:
  `scripts/descargar_suin_vigencias.py` y luego `python -m index.build_vigencia`.
- Comprobar cada tanto los totales de cada fuente contra lo ingerido: dos veces
  ya un tope de descarga cortó una fuente sin avisar.
