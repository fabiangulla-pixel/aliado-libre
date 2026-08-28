# Aliado Libre

RAG legal colombiano libre y gratuito — alternativa abierta a ALI Cerebro Legal (aliado.pro).
Conecta asistentes de IA (vía MCP) a legislación y jurisprudencia colombiana con citas verificables.

Es la primera herramienta de [Suite Legal Libre](../suite-legal-libre) — 100% local por
diseño (solo hace búsqueda, no genera texto, no necesita el módulo `llm_dual` de la suite).

**Cobertura honesta**: este proyecto NO pretende cubrir "toda" la data jurídica de Colombia.
Cubre lo que tiene fuente abierta confirmada y documentada (ver `docs/fuentes.md`).
Cuando el índice no tiene algo, el servidor MCP debe decirlo explícitamente — nunca inventar.

## Estado (28-ago-2026)

**4 fuentes funcionando de punta a punta.** Corpus crudo actual: ~2.381 Gestor Normativo +
5.000 Supersociedades + 36.853 Corte Constitucional + SIC en curso ≈ **44.000+ documentos**.
Índice en reconstrucción con el corpus completo (ver estado real corriendo `git log`).
Última validación con consultas reales (sobre 3.861 docs / 134.633 fragmentos) devolvió citas
correctas, incluyendo detección automática de normas derogadas.

- ✅ **Gestor Normativo** (legislación nacional): ~2.381 normas. Techo del método BFS confirmado
  (ver `docs/fuentes.md`) — para crecer más allá hace falta otro método, no solo más semillas.
  Incluye extracción del grafo de vigencias (modifica/deroga/reglamenta) nativo del sitio.
- ✅ **Supersociedades** (Tesauro, conceptos jurídicos): 5.000 conceptos. Texto embebido en
  Elasticsearch, sin depender de PDFs.
- ✅ **Corte Constitucional**: 36.853 sentencias (1992-2026). Un request por año trae todo el
  año (`maxprov` alto) — no hace falta paginar por documento.
- ✅ **SIC** (decisiones jurisdiccionales): PDFs vía URL firmada de S3 pública (endpoint Lambda
  sin autenticación), texto extraído con `pypdf`.
- ✅ **Servidor MCP**: `buscar_normativa()` operativo (API `mcp` 2.x).
- ⏳ Consejo de Estado, Corte Suprema, DIAN, Superfinanciera: mapeados como accesibles,
  ingesters aún no escritos.
- 🔴 SUIN-Juriscol y jurisprudencia.ramajudicial.gov.co: bloqueados a nivel de firewall.
  Respaldo: repos GitHub `legalize-dev/legalize-co` y `scuervo91/leyes-colombianas` (MIT).

**Calidad**: 25 tests (`make test`), lint limpio (ruff), hook de pre-commit instalado.

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

1. Terminar de reconstruir el índice con las 4 fuentes (~44.000 documentos, toma varias horas).
2. Escribir ingesters para Consejo de Estado, Corte Suprema, DIAN, Superfinanciera.
3. Clonar `legalize-co` como respaldo de SUIN histórico.
4. Desplegar el servidor MCP como servicio (Render).
