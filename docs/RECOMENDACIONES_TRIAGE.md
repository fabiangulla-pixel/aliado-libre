# Triaje de "Aliado Libre: recomendaciones de mejora" (29-sep-2026)

El documento propone doce prioridades y un plan de tres a cuatro meses. Aquí se
cruza cada una con lo que el repositorio **ya midió**, porque varias ya se
hicieron, y alguna se probó y **empeoraba** el resultado. Cuatro estados:
✅ hecho hoy · ☑ ya existía · ⛔ descartado con datos (no repetir sin un hecho nuevo) ·
⏳ pendiente, con su dueño.

## P1 — Recuperación híbrida

- ☑ BM25/FTS5 + denso (e5-large) fusionados por RRF: existe desde el 3-sep.
- ⛔ **Reranker cross-encoder**: medido el 12-sep sobre 44 consultas de desarrollo,
  27% sin reordenar, 23% con ventana 40 y 20% con 120. Sacaba el Código Civil del top-5
  y metía un decreto de 1938. Apagado por defecto (`ALIADO_RERANKER_ACTIVO=1`). Los +10
  puntos del 7-sep se midieron con consultas redactadas a partir del fragmento.
- ⛔ Peso de la fusión RRF (plano entre 0 y 1,5), puente de vocabulario (tres formas),
  reescritura al registro jurídico, HyDE (32,5 → 19,5%).
- ✅ **Filtro de vigencia** como etapa entre la recuperación y la generación
  (`index/vigencia.py`). No filtra, **etiqueta y decide**: una norma derogada puede ser
  la respuesta correcta a "¿qué decía…?", así que se muestra marcada en vez de ocultarse.
- ⛔ Extracción de entidades jurídicas de la consulta (ley N de AAAA, artículo):
  **7 de 1.276 consultas reales (0,5%)** y 6 de 100 del piloto citan una norma por
  número. Mejoraría a quien ya acierta (abogado_junior, 67%), no a quien falla.

## P2 — Modelo normativo y vigencia

- ✅ Estados: derogada, inexequible, revocada, nula, suspendida, incierta y "sin nota",
  con alcance **documento** o **parcial**. "Sin nota" no se presenta nunca como vigente.
- ✅ Dos fuentes combinadas: la nota oficial dentro del texto (607 documentos) y el
  catálogo de SUIN-Juriscol en datos.gov.co (8.310 normas con estado negativo).
  **8.194 documentos marcados.**
- ⛔ **El "Vigente" de SUIN no sirve como dato**: lo lleva la Ley 1943 de 2018
  (inexequible entera, C-481-19) y 29.250 de los decretos anteriores a 1960. Es el valor
  por omisión del catálogo. Tampoco "Compilado" (lo lleva el Código Sustantivo del
  Trabajo). Protegido por prueba.
- ⏳ Grafo de relaciones (deroga, modifica, reglamenta). Gestor Normativo lo trae
  nativo para 2.381 normas; no se ingiere como grafo. Claude.

## P3 — Documento y artículo

- ☑ La métrica ya cuenta acierto por `documento_id`.
- ⏳ Artículo como metadato del fragmento. Requiere reindexar: va junto con P4.

## P4 — Troceo por artículo

- ⏳ Un experimento, **una variable**, sobre el corpus congelado `e422ffbae7186cb8`.
  Coste: ~2 h de GPU por troceo. La guarda de huella impide mezclar índices. Claude.
- Nota: el troceo del 12-sep por párrafos y el anterior por tamaño dieron fragmentos
  casi idénticos (1% y 6% de diferencia). El troceo por artículo sí sería distinto.

## P5 — Banco de evaluación

- ☑ Banco piloto de 100 anclas independientes con tipos (responde, trampa_derogada,
  no_cubierto…), validado antes de medir; 1.276 consultas reales para cobertura.
- ✅ Recall@1/@10 y MRR@10 en `lab_recuperacion.py --linea-base`. **Línea base del
  29-sep** (producción: RRF, BM25 0,8, sin reordenar; 95 anclas): recall@1 13,7%,
  @5 27,4%, @10 31,6%, MRR@10 0,197. Dev y test coinciden (27,3 / 27,5%).
  Que @10 casi no supere a @5 dice que ensanchar la ventana no es la palanca: cuando
  el documento no está entre los cinco primeros, casi nunca está entre los diez.
  nDCG no aporta con una sola ancla por consulta (se reduce a MRR con otro descuento).
- ⏳ **Revisión humana de 20 casos** (`finetune/eval/revision_humana.html`), pendiente
  desde el 7-sep. **Fabián.** Sin ella no hay cifra de utilidad publicable.

## P6 — Pipeline y contrato de respuesta

- ☑ Etapas deterministas: recuperar → enrutar (abstención calibrada) → redactar →
  verificar anclaje. ✅ Ahora con la vigencia entre recuperar y redactar, y la guarda de
  vigencia después.
- ☑ La GUI no presenta como fundamentada una respuesta sin respaldo (`hay_respaldo`).

## P7 — Abstención

- ☑ Por falta de evidencia (umbral calibrado).
- ✅ Por **solo encontrar normas que no rigen**, diciendo qué se encontró y qué buscar.
- ⏳ Por conflicto entre fuentes o por consulta que exige asesoría individual: no hay
  detector y no se inventa uno sin casos reales.

## P8 — Local / nube / híbrido

- ✅ README: tabla con "qué sale de tu equipo" y "costo por consulta" por modo, y la
  aclaración de que el piloto midió la **redacción por nube**.
- ⛔ Cambiar de SLM ahora: coincide con el documento, primero la recuperación. Ya se
  midió que a 1,5B el ajuste fino está agotado (33% frente a 93% de Haiku).

## P9 — MCP

- ✅ `buscar_normativa` con vigencia y límites; nuevas `verificar_vigencia` y
  `leer_fragmento`, con ids validados con lista blanca. Ninguna herramienta genérica.
- ⏳ `comparar_normas`, `explicar_con_evidencia`: esperar a que haya un uso que las pida.

## P10 — Seguridad

- ✅ `SECURITY.md` con el modelo de amenazas, cada control con su prueba.
- ✅ Corpus delimitado en el prompt como datos, no instrucciones.
- ⏳ Escaneo de secretos automatizado antes del push (gitleaks o similar). Claude.

## P11 — Reproducibilidad

- ☑ Huella del corpus y del troceo en los metadatos; el indexador rechaza reanudar un
  índice incompatible (4 guardas con prueba negativa, 12-sep).
- ⏳ Manifiesto completo (licencias por fuente, commit, modelo, dimensión) en un archivo
  junto al índice. Claude.

## P12 — Publicación

- ✅ `SECURITY.md`.
- ⏳ **`LICENSE`: no existe.** Un proyecto "libre" sin licencia es, legalmente, de
  todos los derechos reservados. La elección (MIT, Apache-2.0, AGPL-3.0…) es de
  **Fabián**. Si el objetivo es que nadie cierre un derivado como servicio de pago,
  la AGPL-3.0 es la que lo impide.
- ⏳ `CONTRIBUTING.md`, `CITATION.cff`, `v0.1.0-alpha`: después de la licencia.
- ⏳ El nombre: `docs/NOMBRE.md` recomienda "Norma Abierta"; falta confirmar. **Fabián.**

## Lo que el documento no dice y los datos sí

1. El documento da por supuesto que el reranker ayuda. Aquí se midió que perjudica con
   consultas reales.
2. El 81% de los "fallos" de recall@5 respondían bien con otra norma que cita lo mismo:
   la métrica por ancla subestima. La propuesta del 12-sep (¿dio una norma con cita
   literal que existe en el contexto?) está en 80/100.
3. El hueco más grande no es técnico: servicios públicos y consumo financiero están en
   0/37 y 1/11 frente a la demanda real. Es corpus, no algoritmo.
