# Aliado Libre

RAG legal colombiano libre y gratuito — alternativa abierta a ALI Cerebro Legal (aliado.pro).
Conecta asistentes de IA (vía MCP) a legislación y jurisprudencia colombiana con citas verificables.

**Cobertura honesta**: este proyecto NO pretende cubrir "toda" la data jurídica de Colombia.
Cubre lo que tiene fuente abierta confirmada y documentada (ver `docs/fuentes.md`).
Cuando el índice no tiene algo, el servidor MCP debe decirlo explícitamente — nunca inventar.

## Estado (28-ago-2026)

- ✅ **Gestor Normativo** (legislación nacional): ingester funcionando de punta a punta,
  incluyendo extracción del grafo de vigencias (modifica/deroga/reglamenta) nativo del sitio.
- ⚠️ **Corte Constitucional**: API JSON mapeada parcialmente (`buscador_new`); temporalmente
  bloqueada por WAF tras pruebas repetidas — reintentar con pausas largas entre requests.
- ⚠️ **SIC (relatoría)**: Elasticsearch público encontrado (`relatoria.sic.gov.co/sic-relatoria-idx/_search`,
  1.807 providencias), pero el texto completo vive en PDFs en S3 sin acceso público directo (403) —
  pendiente encontrar el endpoint de descarga autenticado del propio sitio.
- ⏳ Consejo de Estado, Corte Suprema, Supersociedades, DIAN, Superfinanciera: mapeados como
  accesibles, ingesters aún no escritos.
- 🔴 SUIN-Juriscol y jurisprudencia.ramajudicial.gov.co: bloqueados a nivel de firewall.
  Respaldo: repos GitHub `legalize-dev/legalize-co` y `scuervo91/leyes-colombianas` (MIT).

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

1. Ejecutar un crawl real de Gestor Normativo (varios cientos de normas, pausado y responsable).
2. Retomar Corte Constitucional cuando el WAF libere el bloqueo temporal.
3. Resolver descarga de PDFs de SIC (relatoria.sic.gov.co).
4. Escribir ingesters para Consejo de Estado, Supersociedades, DIAN, Superfinanciera.
5. Clonar `legalize-co` como respaldo de SUIN histórico.
