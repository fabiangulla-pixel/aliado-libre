# NEXT_STEPS — Aliado Libre

Estado al 29-sep-2026. El cruce completo con el documento de recomendaciones
externas está en `docs/RECOMENDACIONES_TRIAGE.md`.

## Bloqueado en Fabián

1. **Elegir licencia.** No hay `LICENSE`: hoy el código es legalmente de todos
   los derechos reservados. AGPL-3.0 si se quiere impedir que alguien lo cierre
   como servicio de pago; MIT/Apache-2.0 si se prefiere la máxima adopción.
2. **Revisión humana de 20 casos** (`finetune/eval/revision_humana.html`),
   pendiente desde el 7-sep.
3. **CSV del Planificador de Palabras Clave de Google Ads** (interfaz web,
   ubicación Colombia) con las 1.276 consultas cosechadas.
4. **Autorizar el push** de los commits locales.

## Siguiente tarea técnica

1. **Medir la guarda de vigencia de punta a punta**: repetir el piloto de 100
   consultas con `correr_piloto.py --ejecutar` (~0,43 USD con Haiku 4.5; pedir
   confirmación). El prompt cambió el 29-sep (línea de vigencia y delimitadores
   `<documento>`): las cifras del 12-sep ya no describen el sistema.
2. **Ingerir por demanda**: servicios públicos domiciliarios (0/37) y consumo
   financiero (1/11).
3. **Troceo por artículo** como experimento de una sola variable, sobre el
   corpus `e422ffbae7186cb8`.
4. **Recompilar el .exe**: lleva `index/vigencia_documentos.json` desde el 29-sep.

## Mantenimiento

- Reconstruir la tabla de vigencia tras cualquier reindexado o cada mes:
  `scripts/descargar_suin_vigencias.py` y luego `python -m index.build_vigencia`.
