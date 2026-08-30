# Changelog

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
