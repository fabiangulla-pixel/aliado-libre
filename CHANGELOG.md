# Changelog

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
