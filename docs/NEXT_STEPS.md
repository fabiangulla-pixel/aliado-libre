# NEXT_STEPS — Aliado Libre

Estado al 15-nov-2026. El cruce con el documento de recomendaciones externas
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

## Estado al 15-nov

- **Etapa 2 indexada**: 224.651 documentos, 2.648.958 fragmentos (corpus
  `5e645d4fab605628`), con Corte Suprema Laboral+Civil digital. Recall@5 en el
  banco de 200: **32,5%** (línea base 13-oct: 34,5%; 4 casos sobre 200, dentro
  del ruido: no se detecta diferencia con esta muestra). Corte Suprema ocupa el
  7% del top-5. Ojo: "unión libre, derechos si nos separamos" devuelve 4
  sentencias laborales de pensión de compañera permanente.
- **Consejo de Estado descargado** (`data/raw/consejo_estado.json`, 121.844
  providencias) pero SIN indexar: ~2 M fragmentos más. No indexar sin antes
  resolver el desplazamiento de arriba (p. ej. pesos o cupos por fuente) y
  medir.

## OCR de la Corte Suprema (en curso desde el 15-nov)

17.907 sentencias publicadas que no teníamos (casi todas Laboral 2013-2020,
PDF escaneados; también ~440 de 2024 cuyo .docx no existe en el servidor y sí
el .pdf). Corre solo en la GPU:

- `scripts/ocr_cs_listar.py` (hecho) → `data/ocr_corte_suprema/pendientes.jsonl`.
- `scripts/ocr_cs_trabajador.py` en `C:\dev\venv-paddle` → `resultados_p*.jsonl`.
  Lo relanza la tarea programada **AliadoLibre-OCR** (al iniciar sesión y cada
  15 min; `scripts/ocr_cs_tarea.ps1 -Quitar` la elimina). Sobrevive a apagones
  y cierres de sesión: cada sentencia se escribe con fsync y la línea a medias
  se corta al arrancar. Logs: `_run/ocr_cs_trabajador_p*.log`.
- **Pausar** (p. ej. para reindexar o servir la web con la GPU libre): crear
  `data/ocr_corte_suprema/PAUSA`; reanudar: borrarlo. También se pausa solo en
  batería y no arranca mientras corre `reindexar_con_gpu`.
- Procesos en paralelo: `data/ocr_corte_suprema/_partes`.
- Al terminar (aparece `_terminado`): `scripts/ocr_cs_integrar.py` →
  `data/raw/corte_suprema_ocr.json`, y reindexar con `--ampliar` **solo después
  de resolver el desplazamiento** (ver arriba).
- Calidad medida contra la capa de texto de PDF digitales de la Corte: recall de
  palabras 99,0% a 200 dpi. El texto de OCR queda marcado en metadata
  (`ocr`, `confianza_ocr`).

## Siguiente tarea técnica

1. **Diversidad por fuente en el top-k** antes de sumar Consejo de Estado y el
   OCR: medir con el banco de 200 y con las consultas de demostración.
2. Recompilar el `.exe` y publicar el índice ampliado en HF (decidir antes el
   acceso con registro).
3. **Troceo por artículo** como experimento de una sola variable.
4. **Destilado CERRADO**, no retomar sin una idea nueva.

## Mantenimiento

- Reconstruir la tabla de vigencia tras cualquier reindexado o cada mes:
  `scripts/descargar_suin_vigencias.py` y luego `python -m index.build_vigencia`.
- Comprobar cada tanto los totales de cada fuente contra lo ingerido: dos veces
  ya un tope de descarga cortó una fuente sin avisar.
