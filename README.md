# Aliado Libre

RAG legal colombiano libre y gratuito — alternativa abierta a ALI Cerebro Legal (aliado.pro).
Conecta asistentes de IA (vía MCP) a legislación y jurisprudencia colombiana con citas verificables.

Es la primera herramienta de [Suite Legal Libre](../suite-legal-libre) — 100% local por
diseño (solo hace búsqueda, no genera texto, no necesita el módulo `llm_dual` de la suite).

**Cobertura honesta**: este proyecto NO pretende cubrir "toda" la data jurídica de Colombia.
Cubre lo que tiene fuente abierta confirmada y documentada (ver `docs/fuentes.md`).
Cuando el índice no tiene algo, el servidor MCP debe decirlo explícitamente — nunca inventar.

## Estado (30-ago-2026)

Corpus creciendo activamente — de 44.733 documentos (28-ago) a más de 150.000 y subiendo.
Ver `CHANGELOG.md` para el detalle sesión a sesión.

- ✅ **Gestor Normativo** (legislación nacional): 2.381 normas. Techo del método BFS confirmado
  (ver `docs/fuentes.md`). Incluye el grafo de vigencias (modifica/deroga/reglamenta) nativo.
- ✅ **Supersociedades** (Tesauro, conceptos jurídicos): 4.999 conceptos.
- ✅ **Corte Constitucional**: 36.853 sentencias (1992-2026).
- ✅ **SIC** (decisiones jurisdiccionales): 500 providencias.
- ✅ **DIAN**: normativa/doctrina/jurisprudencia tributaria, aduanera y cambiaria (creciendo).
- ✅ **Superfinanciera**: conceptos jurídicos y jurisprudencia financiera (creciendo, 18.569
  registros en el catálogo).
- ✅ **legalize-co** (respaldo GitHub): 71.900 normas completas, resuelve de paso el techo de
  Gestor Normativo.
- ⏳ **Corte Suprema de Justicia**: ingester funciona (backend GraphQL propio, sin autenticación,
  corpus de >1M resultados brutos) pero el servidor de la Corte es muy inestable (502
  intermitente) — corriendo con reintento persistente hasta que haya una ventana estable.
- 🔴 Consejo de Estado, SUIN-Juriscol, jurisprudencia.ramajudicial.gov.co: bloqueados por WAF.
- ✅ **Servidor MCP**: `buscar_normativa()` operativo (API `mcp` 2.x), modo local (`stdio`).
  Deploy a un servicio web (Render) preparado pero deliberadamente no activado — el costo
  recurrente no se justifica frente al uso 100% local actual (ver `docs/DEPLOY.md`).

**Portabilidad**: el código vive en GitHub (`github.com/fabiangulla-pixel/aliado-libre`), pero
`data/raw/` y `index/chroma_db/` (varios GB) no — se generan localmente corriendo los ingesters,
o se descargan ya construidos desde Hugging Face Hub una vez publicados
(`scripts/publicar_indice_hf.py`).

**Calidad**: 63+ tests (`make test`), lint limpio (ruff), hook de pre-commit instalado.

## Arquitectura

```
ingest/          scrapers por fuente -> Documento (esquema común en ingest/schema.py)
  fuentes/
    gestor_normativo.py, supersociedades.py, corte_constitucional.py, sic.py,
    dian.py, superfinanciera.py, corte_suprema.py, legalize_co_github.py
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

1. Terminar de escalar los crawls de DIAN, Superfinanciera y Corte Suprema.
2. Publicar el índice construido en Hugging Face Hub (`scripts/publicar_indice_hf.py`)
   para que otros lo usen sin tener que reconstruirlo.
3. Consejo de Estado sigue bloqueado por WAF — no hay plan de reintento hasta que aparezca
   una vía de acceso pública real.
