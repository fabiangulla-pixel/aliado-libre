# NEXT_STEPS — Aliado Libre

Estado al 23-nov-2026. El cruce con el documento de recomendaciones externas
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
4. **Dominio**: comprarlo (Cloudflare, ~30 USD/año) y luego
   `scripts/configurar_dominio.ps1 -Dominio <dominio>`. La compra la hace Fabián.
5. Enlace de aporte (`ALIADO_ENLACE_PAGO`), prueba desde el celular con datos
   móviles y pasar el índice de Hugging Face a acceso con registro.
6. CSV del Planificador de Palabras Clave de Google Ads (1.276 consultas).
7. **Adjudicar respuestas válidas** (`finetune/eval/revision/adjudicar_piloto.csv`,
   138 filas, y `adjudicar_prueba_afirmaciones.csv`, 10 pares): marcar "si/no" en *sirve*. El banco anota UNA respuesta por
   pregunta y hay "fallos" que son respuestas correctas; sin esto no se sabe
   cuánto de la distancia a la meta (90% en el puesto 1) es error del sistema.
8. **~20 preguntas reales** (de personas, no de IA): las preguntas del banco y
   las sintéticas las escribió una IA y pueden parecerse de más.
9. **Servidor**: el enrutador de norma necesita un LLM local (gemma4:26b en
   GPU). ¿El servidor público tendrá GPU? Si no, ver el resultado de los
   modelos chicos en CPU (qwen3:4b, gemma3:4b).

## Corte Suprema / OJEADOR (23-nov)

Hecho en la rama `feat/ojeador-suprema` (ver `docs/OJEADOR.md`). Siguiente:

1. **Pedir a la Corte autorización o un acceso oficial** para ingerir desde OJEADOR.
   El buscador antiguo dejó de recibir en abril de 2026. Sin eso, el índice no
   tendrá 2026 ni tutelas ni autos, y no conviene descargar en masa un servicio
   no documentado.
2. Si se autoriza: ampliar `ingest/fuentes/corte_suprema.py` a tutelas y autos
   y a la Sala Penal, con checkpoint, y medir si mejoran las respuestas antes de
   reindexar todo.
3. ~~Citas antiguas por fecha y radicado~~ HECHO (23-nov, tarde): resolvedor
   y relaciones (6.900 relaciones antiguas confirmadas en el corpus).
4. ~~Ficha del lado del servidor~~ HECHO (23-nov, tarde): falta subir
   `catalogo_suprema.json` al servidor cuando se despliegue
   (`docs/DESPLIEGUE_INDICE.md`).
5. El catálogo (`index/catalogo_suprema.json`, `relaciones_suprema.db`) no se
   versiona: reconstruirlo con `python -m index.providencias --construir`
   (~2 min) tras cualquier cambio en `data/raw/corte_suprema*.json`. El 23-nov
   no existía en disco: la GUI no mostraba fichas.

## Meta de precisión (actualizado 22-nov)

Meta: la norma correcta en el puesto 1 en 9 de cada 10 preguntas coloquiales.
Acordado con Fabián el 22-nov: **afirmar una norma solo cuando acierta >= 9 de
10, y presentar opciones en el resto** (implementado, ver CHANGELOG 22-nov).

**La verificación única en prueba_200 NO confirmó la mejora de dev**: fusión +
gemma 12,0% #1 frente a 17,5% de lo desplegado; confianza alta 2/25 estricta.
Los defectos no cambian. banco_prueba_200 ya se miró: **no se puede volver a
usar para elegir**. Siguiente, en orden:

1. **Fabián adjudica** `adjudicar_prueba_afirmaciones.csv` (10 pares, ~20 min)
   y `adjudicar_piloto.csv`. Con eso, `python finetune/precision_afirmacion.py
   fusion_enr prueba` dice si la confianza alta cumple el 90% de verdad.
2. **Un banco de prueba nuevo** de preguntas ciudadanas, apartado antes de
   mirar nada: idealmente las ~20 preguntas reales de personas (ítem 8) más
   un banco generado con el mismo método que piloto. Si se genera con API de
   pago: estimar costo y confirmar antes.
3. Atacar el fallo medido en los dos bancos: el enrutador nombra la ley
   general en vez del decreto u oficio específico. **Ya descartadas con datos
   en dev**: pedir al LLM la norma "más específica" (elección 25,3%, prompt v2
   34,7% frente a 44,2%) y no promover cuando el #1 de la búsqueda ya cita la
   ley (33,7-38,9%, pierde 5-11 casos; `_run/exp_no_promover.py`, 23-nov). En
   piloto la promoción acierta; el fallo es de prueba_200 (respuestas ancladas
   a oficios). Sin banco nuevo no hay cómo elegir la siguiente idea.
4. Afinar e5 con las preguntas sintéticas (BSARD: el denso afinado gana).

## Estado al 20-nov

- **Etapa 3 indexada (19-nov)**: etapa 2 + las sentencias de la Corte Suprema
  por OCR (`data/raw/corte_suprema_ocr.json`, 17.647; 260 sin archivo en el
  servidor). 242.298 documentos, **3.296.273 fragmentos**. Recall@5 en el
  banco de 200: **31,5%** (etapa 2: 32,5%; 2 casos, no se detecta diferencia).
  Corte Suprema: 6% del top-5. Se indexó desde `_run/raw_etapa3` (enlaces
  duros a `data/raw` **sin** `consejo_estado.json`).
- **Consejo de Estado aplazado (19-nov)**: con él, el corpus daba 7,1 M
  fragmentos (×2,2), 37 GB de RAM solo para cargar, índice >100 GB y ~30 GB de
  RAM para servir los vectores: descarta el servidor sin GPU y aprieta el PC.
  Propuesta: indexar un subconjunto (unificación + Sala de Consulta, o los
  últimos 10 años). Decide Fabián.
- OCR de la Corte Suprema **terminado** (17-nov… 19-nov 14:08); la tarea
  AliadoLibre-OCR ya no hace nada (`_terminado`), se puede quitar con
  `scripts/ocr_cs_tarea.ps1 -Quitar`.

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

## OCR de la Corte Suprema (TERMINADO el 19-nov e indexado en la etapa 3; histórico)

Pendiente solo de Fabián: quitar la tarea programada, que ya no hace nada
(`powershell -ExecutionPolicy Bypass -File scripts\ocr_cs_tarea.ps1 -Quitar`).

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

1. **Tope de sentencias en el top-k: HECHO (15-nov)** (`index/buscar.py`,
   `limitar_sentencias`, 40% del top-k). Sin cambio de recall en dev ni prueba.
   Con eso queda libre sumar Consejo de Estado y el OCR: **un solo reindexado
   con `--ampliar` cuando el OCR termine** (`_terminado`), después de
   `ocr_cs_integrar.py`. No antes: reindexado (~9 GB) + 2 procesos de OCR
   (~14 GB) no caben juntos en los 16 GB de la GPU. Luego volver a medir con
   `_run/medir_etapa2.py` y `_run/exp_diversidad.py`.
2. **¿Servir sin GPU? (plan acordado con Fabián el 15-nov).** Con el túnel, la
   web depende de que el PC esté prendido. Fase 1: piloto desde el PC con el
   dominio. Fase 2: medir cuánta calidad se pierde con el reordenador en CPU
   (`finetune/medir_reordenador_cpu.py`: bge-m3 con 60/20/10 candidatos, int8,
   mMiniLM; 4 hilos; elegir en piloto_100, comprobar una vez en prueba_200).
   Si la pérdida es pequeña, servidor sin GPU de ~30-80 USD/mes.
   **Medido en dev el 20-nov** (piloto, 95, máquina quieta, 4 hilos; pools de
   la etapa 3): sin reordenar 24,2%; bge 60 26,3% a 41 s/consulta; bge 20
   int8 25,3% a 6,4 s; **mMiniLM 60 26,3% a 4,3 s**. Entre la mejor y nada, 2
   casos de 95: no se detecta diferencia con esta muestra. **Comprobación única
   en prueba_200 (23-nov): sin reordenar 25,5% = mMiniLM 25,5% (16 y 16).**
   Conclusión: servidor sin GPU y sin reordenador es viable para la búsqueda.
   Ojo: el enrutador de norma (gemma4:26b) sí pide GPU, pero está apagado y
   sin confirmar. **Decide Fabián** el hosting.
3. Recompilar el `.exe` y publicar el índice ampliado en HF (decidir antes el
   acceso con registro).
4. **Troceo por artículo** como experimento de una sola variable.
5. **Destilado CERRADO**, no retomar sin una idea nueva.

## Mantenimiento

- Reconstruir la tabla de vigencia tras cualquier reindexado o cada mes:
  `scripts/descargar_suin_vigencias.py` y luego `python -m index.build_vigencia`.
- Comprobar cada tanto los totales de cada fuente contra lo ingerido: dos veces
  ya un tope de descarga cortó una fuente sin avisar.
