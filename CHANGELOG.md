# Changelog

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
