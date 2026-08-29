# Aliado Libre

RAG legal colombiano libre y gratuito — alternativa abierta a ALI Cerebro Legal (aliado.pro).
Conecta asistentes de IA (vía MCP) a legislación y jurisprudencia colombiana con citas verificables.

Es la primera herramienta de [Suite Legal Libre](../suite-legal-libre) — 100% local por
diseño (solo hace búsqueda, no genera texto, no necesita el módulo `llm_dual` de la suite).

**Cobertura honesta**: este proyecto NO pretende cubrir "toda" la data jurídica de Colombia.
Cubre lo que tiene fuente abierta confirmada y documentada (ver `docs/fuentes.md`).
Cuando el índice no tiene algo, el servidor MCP debe decirlo explícitamente — nunca inventar.

## Estado (28-ago-2026)

**Índice final construido y validado con el corpus completo**: 44.733 documentos → 214.435
fragmentos → búsqueda híbrida → servidor MCP. Auditado con `/data-audit` antes de indexar
(0 problemas reales pendientes, ver `DATA_AUDIT.md`). Validado con consultas reales en varios
dominios (societario, laboral, salud/tutela) — todas devolvieron citas correctas y verificables
(sentencias reales de la Corte Constitucional, artículos exactos de leyes/decretos).

- ✅ **Gestor Normativo** (legislación nacional): 2.381 normas. Techo del método BFS confirmado
  (ver `docs/fuentes.md`) — para crecer más allá hace falta otro método, no solo más semillas.
  Incluye extracción del grafo de vigencias (modifica/deroga/reglamenta) nativo del sitio.
- ✅ **Supersociedades** (Tesauro, conceptos jurídicos): 4.999 conceptos. Texto embebido en
  Elasticsearch, sin depender de PDFs.
- ✅ **Corte Constitucional**: 36.853 sentencias (1992-2026). Un request por año trae todo el
  año (`maxprov` alto) — no hace falta paginar por documento.
- ✅ **SIC** (decisiones jurisdiccionales): 500 providencias. PDFs vía URL firmada de S3 pública
  (endpoint Lambda sin autenticación), texto extraído con `pypdf`.
- ✅ **Servidor MCP**: `buscar_normativa()` operativo (API `mcp` 2.x).
- ⏳ Consejo de Estado, Corte Suprema, DIAN, Superfinanciera: mapeados como accesibles,
  ingesters aún no escritos.
- 🔴 SUIN-Juriscol y jurisprudencia.ramajudicial.gov.co: bloqueados a nivel de firewall.
  Respaldo: repos GitHub `legalize-dev/legalize-co` y `scuervo91/leyes-colombianas` (MIT).

**Rendimiento**: ~75s de carga inicial (modelo + 214k fragmentos en memoria) una sola vez al
arrancar el servidor MCP, luego <1s por consulta. La carga es cara pero es costo único de
arranque, no de cada consulta — aceptable para un proceso de servidor de larga duración.

**Calidad**: 31 tests (`make test`), lint limpio (ruff), hook de pre-commit instalado.

## Arquitectura

```
ingest/          scrapers por fuente -> Documento (esquema común en ingest/schema.py)
  fuentes/
    gestor_normativo.py   (funcionando)
  chunking.py     corta documentos en fragmentos citables (por artículo cuando es posible)
data/raw/         JSON crudo por fuente
index/
  build_index.py  construye embeddings + índice Chroma a partir de data/raw/
  buscar.py        búsqueda híbrida (vectorial + BM25, fusión RRF)
mcp_server/
  server.py        expone buscar_normativa() como herramienta MCP
```

## Entorno

**IMPORTANTE**: usar el venv del proyecto (`venv/`, Python 3.12), NO el Python 3.14 del sistema.
PyTorch/sentence-transformers hacen segfault en Python 3.14 (muy reciente, sin soporte aún).

```
./venv/Scripts/python.exe index/build_index.py     # construir/actualizar índice
./venv/Scripts/python.exe index/buscar.py "consulta"  # probar búsqueda por CLI
./venv/Scripts/python.exe mcp_server/server.py      # levantar servidor MCP
```

## Próximos pasos

1. Escribir ingesters para Consejo de Estado, Corte Suprema, DIAN, Superfinanciera.
2. Clonar `legalize-co` como respaldo de SUIN histórico.
3. Desplegar el servidor MCP como servicio (Render).
