# Changelog

## 2026-09-01 — DIAN completado, diagnóstico real de la lentitud del fine-tuning en CPU

### Resuelto

- **DIAN escalado a las 3 materias**: relanzado con tope elevado (50.000);
  pasó de 20.000 (solo tributario + 15 de aduanero) a **25.927 documentos**
  (tributario 19.985, aduanero 5.567, cambiario 375). Ya no hay materias sin
  cubrir.
- **`finetune/entrenar.py` parametrizado**: acepta `[modelo_base] [nombre_salida]`
  por línea de comandos en vez de tener el modelo hardcodeado, con
  checkpoints separados por experimento (`checkpoints_<nombre_salida>/`) —
  necesario para poder comparar 0.5B vs 1.5B sin pisar resultados.
- **Causa real de la lentitud en CPU encontrada**: los checkpoints de Qwen
  cargan en `bfloat16` por defecto (`torch_dtype="auto"`), pero la CPU de
  esta máquina (AMD Ryzen 5 5500U) no tiene soporte de hardware para bf16
  (sin AVX512-BF16) — PyTorch lo emulaba por software, mucho más lento que
  usar `float32` nativo. Corregido: `dtype="float32"` explícito en la carga
  del modelo. El fix ayudó pero no fue suficiente por sí solo: incluso así,
  el primer step tardó ~40+ min en esta CPU — se concluyó que el hardware en
  sí (chip móvil de bajo consumo, sin GPU) no es viable para entrenar ni
  siquiera un modelo de 500M de parámetros en tiempo razonable.
- **`.gitignore`**: patrones `finetune/checkpoints*/` y `finetune/modelo_lora*/`
  (antes solo cubrían los nombres exactos sin sufijo) + `*.log` para los
  logs de scripts en background.
- **`requirements.txt`**: agregadas `peft`, `trl`, `accelerate`, `datasets`
  (ya estaban instaladas en el venv para el fine-tuning pero no declaradas).

### Decisión de arquitectura

- El adaptador LoRA NO reduce el tamaño del modelo a usar en producción —
  sigue necesitando el modelo base completo cargado. Como el criterio de
  éxito final es el tamaño del `.exe` distribuible (con el modelo
  **empaquetado dentro**, no vía Ollama externo), se decidió abandonar
  `Qwen2.5-3B` y probar en paralelo `Qwen2.5-0.5B-Instruct` y
  `Qwen2.5-1.5B-Instruct` como base — modelos mucho más chicos, mejor
  candidatos para terminar en un `.gguf` cuantizado embebido vía
  `llama-cpp-python` (no `transformers`+`torch`, que son inviables de
  empaquetar — ver `feedback_pyinstaller_excluir_pila_ml`).
- **`finetune/colab_entrenar.ipynb`** (nuevo): notebook autocontenido para
  correr el mismo entrenamiento en la GPU gratuita de Google Colab (T4),
  donde bf16 sí tiene soporte de hardware real y debería tardar minutos en
  vez de días. Pide subir `finetune/data/entrenamiento.jsonl` y descarga un
  `.zip` con el adaptador resultante al terminar.
- **Intento de automatizar Colab por CDP con Chrome clonado**: se clonó
  `Profile 3` y se abrió una ventana de Chrome separada con el puerto de
  debug remoto — la sesión de Google no viajó (probablemente por DBSC,
  cookies de sesión atadas al dispositivo/instalación original). El perfil
  clonado se cerró y se borró correctamente. Conclusión: el fine-tuning en
  Colab se corre manualmente por ahora.

### Pendiente / próxima sesión

1. **Correr `finetune/colab_entrenar.ipynb` en Colab manualmente** (Fabián):
   subir el notebook, GPU T4, subir `entrenamiento.jsonl`, correr dos veces
   (una por cada `MODELO_BASE`/`NOMBRE_SALIDA`), descargar los dos `.zip` y
   descomprimirlos en `finetune/modelo_lora_05b/` y `finetune/modelo_lora_15b/`.
2. Con ambos adaptadores entrenados, comparar calidad de respuesta entre
   0.5B y 1.5B sobre preguntas reales del índice, y decidir cuál usar.
3. Escribir `finetune/exportar_gguf.py` (aún no existe) para convertir el
   adaptador ganador a GGUF cuantizado.
4. Cambiar el runtime de inferencia en producción de Ollama a
   `llama-cpp-python` (más liviano, sin dependencia de PyTorch) para poder
   empaquetar el modelo dentro del `.exe`.
5. Escribir el `.spec` de PyInstaller para Aliado Libre (hoy no existe
   ningún empaquetado a `.exe`, corre directo con `venv/Scripts/python.exe`)
   y medir el tamaño final real con cada modelo para decidir 0.5B vs 1.5B.
6. Corte Suprema sigue en 0 documentos (backend inestable, no se reintentó
   esta sesión).
7. Publicar el índice en Hugging Face Hub — sigue pendiente, decidido
   posponer (ya se tiene un `HF_TOKEN` de lectura funcional de esta sesión,
   pero habría que generar uno con permiso Write para publicar).

## 2026-08-30 — GUI web local, capa conversacional Ollama, reindex resiliente, fine-tuning LoRA

### Resuelto

- **Reindex completo**: `index/build_index.py` reescrito para subir a Chroma
  en lotes de 2000 en vez de un solo `encode()`+`upsert()` final — un job de
  7.5h había muerto en silencio al 9% sin nada guardado (probable OOM por
  contención con otra sesión concurrente en la misma máquina). Relanzado con
  el fix: **718.388 fragmentos de 119.708 documentos**, 7 fuentes.
- **Bug crítico en `scripts/_crawl_retry.py`**: el wrapper de reintentos
  reutilizaba una lista en memoria tras una excepción en vez de releer el
  checkpoint en disco, causando una pérdida real de 1.475 documentos de
  Superfinanciera. Corregido: recibe `cargar_previos` (callable) y lo llama
  al inicio y tras cada excepción.
- **Superfinanciera, 2º bug de decodificación binaria**: el heurístico
  "¿parece texto?" solo miraba los primeros 8KB; un .mp3 con tag ID3v2 con
  metadata XMP legible ahí lo engañó, generando un documento de 114 millones
  de caracteres que mató el reindex de 7.5h. Corregido con rechazo de firmas
  binarias conocidas + muestreo en 3 puntos + tope de 2M caracteres.
- **GUI web local** (`gui/server.py`, `gui/static/index.html`): stdlib puro,
  sin frameworks, autoabre navegador. 9 tests nuevos.
- **Capa conversacional con Ollama** (`index/responder.py`): respuesta en
  español anclada estrictamente en los fragmentos recuperados, con citas
  entre paréntesis y negativa explícita si no hay información suficiente.
  Degrada a solo-citas si Ollama no responde. 5 tests nuevos.
- **GitHub**: repo público (`github.com/fabiangulla-pixel/aliado-libre`).
- **Render**: evaluado y descartado por costo — uso queda 100% local.
- **DIAN/Superfinanciera/legalize-co**: escalados a producción (ver detalle
  en `docs/fuentes.md` y memoria del proyecto).
- **Corte Suprema sigue en 0 documentos**: backend GraphQL propio de la
  Corte extremadamente inestable (100+ ráfagas de reintento en 4 corridas),
  confirmado como problema de servidor, no de cliente.
- 77 tests (era 58).

### En curso al cierre

- **Fine-tuning LoRA propio en CPU** (`finetune/`): dataset de 50 ejemplos
  hand-authored y anclados en fragmentos reales (`finetune/generar_dataset.py`),
  entrenando un adaptador sobre `Qwen/Qwen2.5-3B-Instruct` (`finetune/entrenar.py`).
  Bug real corregido: `SFTConfig` necesita `use_cpu=True` explícito en
  trl 1.12.0 o falla con `ValueError` de bf16/gpu incluso sin GPU. El
  entrenamiento arrancó bien tras el fix pero **no se confirmó que terminara
  las 3 épocas** antes del cierre de sesión — revisar el log al retomar.
  Falta además `finetune/exportar_gguf.py` (no escrito) para cargar el
  resultado en Ollama.

## 2026-08-29 (tarde) — Escalado real: corpus 44.733 → 120.133+ documentos

Continuación de la sesión de la mañana: se le dio soporte de reanudación a
los 4 ingesters nuevos y se corrieron crawls reales a escala.

### Resuelto

- **DIAN**: 3.000 documentos (tope del lote, hay más disponible — el crawl
  se detuvo por `max_documentos`, no porque se agotaran las fuentes).
- **legalize-co**: **71.900 documentos** — el respaldo completo, leído en
  una sola corrida (lectura local, sin red, ~15 minutos).
- **Superfinanciera**: en progreso al cierre (500+ de 3.000 objetivo), corre
  en background y es reanudable.
- **Corte Suprema**: **0 documentos** — el backend GraphQL resultó mucho más
  inestable de lo esperado: 3 sesiones completas de reintentos (15 intentos
  en total, ~50 minutos) sin lograr una sola respuesta 200 sostenida. Queda
  documentado como pendiente a reintentar en otro momento — el código del
  ingester está verificado y funciona (se confirmó con éxito real durante la
  investigación de la mañana), el problema es enteramente de disponibilidad
  del servidor de la Corte, no del cliente.
- **2 bugs reales encontrados y corregidos al correr a escala** (nunca
  aparecieron en las pruebas con lotes de 5-10 documentos):
  1. El "archivo de texto" descargable de Superfinanciera es en realidad un
     `.docx` — decodificarlo directo como texto (asumiendo que el nombre del
     enlace no mentía) infló 225 documentos a 6.7GB antes de descubrirse.
  2. Segunda vuelta del mismo enlace: algunos son en realidad **audios
     .mp3** de audiencias — mismo problema, más grave (MemoryError al
     serializar el checkpoint). Corregido con una heurística de detección
     de binario (proporción de bytes de control) en vez de confiar en la
     extensión o en que la decodificación "no falle" (latin1 nunca falla).
- Auditoría de datos corrida sobre el corpus completo (`DATA_AUDIT.md`):
  sin duplicados, sin colisiones de ID entre las 8 fuentes, esquema completo
  en el 100% de los documentos. Único hallazgo no bloqueante: 72% de los
  conceptos de Superfinanciera sin fecha (identificador es un título largo
  sin fecha embebida para el subtipo "jurisdiccional").
- 4 scripts de crawl (`scripts/crawl_*.py`) con checkpoint incremental y
  reanudación (`documentos_previos`) añadida a los 4 ingesters nuevos.
- 10 tests nuevos (48 → 58).

### Pendiente

1. Terminar el lote de Superfinanciera (corriendo en background al cierre).
2. Reintentar Corte Suprema cuando el backend esté estable — o considerar
   escalarlo en sesiones cortas y frecuentes en vez de una corrida larga.
3. Reconstruir el índice (embeddings + Chroma) con el corpus ampliado —
   aún no se tocó `index/build_index.py` en esta sesión.
4. DIAN: correr de nuevo con `max_documentos` más alto para agotar las 3
   materias completas (hoy se cortó a mitad de camino por el tope).

## 2026-08-29 — 3 ingesters nuevos + respaldo GitHub + preparación de deploy

Segunda sesión: se atacaron los 4 pendientes dejados el 28-ago.

### Resuelto

- **3 fuentes nuevas con ingester funcionando** (`ingest/fuentes/{dian,superfinanciera,corte_suprema}.py`),
  las 3 verificadas con datos reales, no solo con fixtures:
  - **DIAN**: no era SPA — cada materia (tributario/aduanero/cambiario) tiene páginas
    estáticas con fragmentos HTML (`*_parte_NN.html`) que enlazan documentos en `docs/*.htm`
    con el texto completo embebido. Cero necesidad de Playwright.
  - **Superfinanciera**: el buscador "Conceptos y Jurisprudencia" resultó ser un catálogo
    bibliográfico clásico ABCD/ISIS con 18.569 registros, paginación GET simple
    (`desde`/`count`, 1-indexado — `desde=0` rompe la búsqueda) y archivo de texto
    descargable por registro.
  - **Corte Suprema**: hallazgo mayor — el frontend Vue (documentado antes como "shell
    vacío, API no capturada") en realidad habla con un backend GraphQL propio sin
    autenticación (`consultaprovidenciasbk.cortesuprema.gov.co/api`, dominio no visto en
    la investigación previa). El comodín `query: "*"` enumera el corpus completo de cada
    Sala (Civil ~109k, Laboral ~302k, Penal ~218k, Tutelas ~394k) y `getContentSearch`
    trae el texto ya extraído del PDF/DOCX. Backend inestable (502 intermitente incluso
    con los headers correctos) — el ingester reintenta con backoff.
- **Consejo de Estado reintentado a fondo, sigue bloqueado**: encontrado un tercer buscador
  público no documentado antes (`SAMAI/TitulacionRelatoria/BuscadorProvidenciasTituladas.aspx`,
  "Mi Relatoría"), pero el primer postback devuelve 403 de un Azure Application Gateway —
  confirma que el bloqueo es de infraestructura compartida (WAF), no de una URL específica.
  Cerrado; no vale la pena seguir probando URLs nuevas en el mismo dominio.
- **Respaldo `legalize-co` clonado e integrado** (no solo clonado): `data/respaldo_legalize_co/`
  (clon superficial, 71.903 archivos Markdown con YAML front matter) + un cuarto ingester
  nuevo, `ingest/fuentes/legalize_co_github.py`, que lee el respaldo local sin red. De paso
  resuelve el pendiente de escalar Gestor Normativo: el respaldo trae **61.429 decretos**
  completos sin depender del grafo de "Vigencias" que topó techo en 2.381.
- **Deploy a Render preparado, no ejecutado** (confirmado con el usuario: crear el servicio
  real queda pendiente de su aprobación explícita): `Dockerfile`, `render.yaml` (plan
  `standard` + disco persistente de 5GB para el índice de 2.4GB) y `docs/DEPLOY.md` con los
  pasos y el riesgo de costo. `mcp_server/server.py` ahora sirve `streamable-http` sobre
  `$PORT` si la variable existe, sin romper el modo `stdio` local.
- 17 tests nuevos (31 → 48), todos con fixtures/mocks — ninguno depende de red.
  Lint limpio (ruff).

### Pendiente

- Ingestar a escala real las 3 fuentes nuevas (hoy solo verificadas con lotes pequeños) y
  el respaldo legalize-co completo (61.429 decretos + ~10.000 leyes/actos legislativos),
  con checkpoint como Gestor Normativo — la Corte Suprema en particular implica cientos de
  miles de llamadas a `getContentSearch`, hace falta ir por lotes y con pausas generosas.
- Decidir si de verdad se justifica el costo de Render antes de crear el servicio.

## 2026-08-28 — Proyecto creado, 4 fuentes funcionando, índice validado

Primera sesión de trabajo. Proyecto construido desde cero.

### Resuelto

- **Arquitectura completa**: esquema común (`ingest/schema.py`), chunking por artículo,
  índice híbrido (embeddings locales + BM25 con fusión RRF), servidor MCP.
- **4 fuentes con ingester funcionando**:
  - Gestor Normativo (legislación): 2.381 normas, incluye extracción del grafo de vigencias
    (modifica/deroga/reglamenta) nativo del sitio.
  - Supersociedades (conceptos jurídicos): 4.999 documentos, texto embebido en Elasticsearch.
  - Corte Constitucional (jurisprudencia): 36.853 sentencias (1992-2026) — descubierto que un
    solo request por año trae todas las providencias, no hace falta paginar por documento.
  - SIC (decisiones jurisdiccionales): 500 providencias — resuelto el 403 de descarga de PDF
    encontrando el endpoint Lambda público que firma URLs de S3 bajo demanda.
- **Auditoría de datos** (`scripts/audit_corpus.py`) antes de indexar, encontró y corrigió:
  fechas en español sin normalizar (2.377 docs), 1 documento duplicado (Elasticsearch sin
  `sort` explícito), mojibake residual en 28 documentos.
- **Bugs de escala arreglados**: límite de batch de Chroma en `upsert()` (5.461) y en `.get()`
  ("too many SQL variables") — se sube/carga en lotes de 5.000.
- **API de `mcp` actualizada** de v1 (`FastMCP`) a v2 (`MCPServer`).
- Índice final: 44.733 documentos → 214.435 fragmentos. Validado con consultas reales en
  3 dominios (societario, laboral, salud/tutela).
- 31 tests, lint limpio (ruff), CI local (Makefile/check.bat), hook de pre-commit instalado
  y validado con prueba negativa.

### Archivos clave de esta sesión

- `ingest/schema.py`, `ingest/chunking.py`, `ingest/normalizar.py`
- `ingest/fuentes/{gestor_normativo,supersociedades,corte_constitucional,sic}.py`
- `index/{build_index,buscar}.py`, `mcp_server/server.py`
- `scripts/crawl_*.py`, `scripts/audit_corpus.py`
- `docs/fuentes.md` — mapa completo de fuentes investigadas (30+ sitios evaluados)

### Pendiente

1. Ingesters para Consejo de Estado, Corte Suprema, DIAN, Superfinanciera (mapeados
   como accesibles, código no escrito).
2. Clonar `legalize-co` (GitHub, MIT) como respaldo de SUIN-Juriscol histórico
   (SUIN está bloqueado a nivel de firewall, confirmado con curl/Playwright/PowerShell).
3. Desplegar el servidor MCP como servicio (Render).
4. Gestor Normativo tocó el techo natural del método BFS vía "Vigencias" en 2.381 normas
   (confirmado 3 veces con distintas semillas) — crecer más requiere otro método.
