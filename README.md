# Aliado Libre

RAG legal colombiano libre y gratuito — alternativa abierta a ALI Cerebro Legal (aliado.pro).
Legislación y jurisprudencia colombiana con **citas verificables**, para cualquiera: abogado,
estudiante o persona sin formación jurídica.

Es la primera herramienta de [Suite Legal Libre](../suite-legal-libre).

## Qué es y qué no es (4-sep-2026)

Asistente que **responde en prosa** y cita sus fuentes, con un modelo propio fine-tuneado
que corre en el equipo del usuario. Se usa de tres maneras, y la elige el usuario según
la máquina que tenga:

| Modo | Qué necesita | Para quién |
|---|---|---|
| Todo local | ~11 GB de disco, ~2,3 GB de RAM | quien quiera independencia total |
| Modelo local + índice en la nube | conexión; el .exe pesa 29 MB + modelo | equipos modestos |
| Servidor MCP | un asistente de IA propio (Claude, Cursor…) | perfil técnico |

**Estado: en desarrollo, no apto para uso profesional todavía.** La capa que redacta
respuestas está en calibración y su tasa de acierto aún no alcanza el umbral que nos hemos
puesto para darla por utilizable. Mientras tanto: **verifica siempre la cita** — cada
respuesta trae los fragmentos oficiales de los que salió, y esos sí son texto literal
comprobable. No sustituye asesoría jurídica profesional.

Las mediciones de calidad se llevan internamente y se publicarán cuando la precisión
alcance el objetivo fijado.

**Lo que puedes hacer hoy**

- Buscar en 718.388 fragmentos de 7 entidades colombianas, con citas verificables.
- **Acotar por entidad** (solo la SIC, solo la DIAN, o varias cruzadas) y ver qué
  fuentes están cubiertas y **cuáles no, con el motivo**.
- **Apartar fuentes en un tablero** y exportarlas a `.md` o `.txt` para trabajar en tu
  equipo. El tablero vive en tu navegador y desaparece al cerrar la pestaña.
- Pedir una respuesta redactada por el modelo propio (gratis) o, si tienes clave de
  API de otro proveedor, por esa IA — viendo **el costo estimado antes de gastar**.

**No guardamos tus consultas ni registramos quién pregunta.** Ver `docs/PRINCIPIOS.md`.

**Salvaguarda que ya existe**: un verificador determinista comprueba que cada número de
norma, artículo, plazo y cifra de la respuesta esté en los fragmentos recuperados, y marca
lo que no encuentre.

**Cobertura honesta**: este proyecto NO pretende cubrir "toda" la data jurídica de Colombia.
Cubre lo que tiene fuente abierta confirmada y documentada (ver `docs/fuentes.md`).
Cuando el índice no tiene algo, la app debe decirlo explícitamente — nunca inventar — y
distinguir "no está en el índice" de "no sé": los huecos de cobertura son información útil.

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
  build_fts.py     construye el índice léxico FTS5 (SQLite, en disco) a partir de Chroma
  buscar.py        búsqueda híbrida (vectorial + FTS5, fusión RRF ponderada — RAM ~2.3GB
                    con los 718k fragmentos, antes ~10GB con BM25 en memoria)
mcp_server/
  server.py        expone buscar_normativa() como herramienta MCP
```

## Entorno

**La versión de Python no es negociable: 3.12.** PyTorch y sentence-transformers hacen
segfault en el 3.14 del sistema, y este proyecto los carga siempre que toca el índice. Está
declarado en `pyproject.toml` (`requires-python`), no solo aquí.

Instalación desde cero:

```sh
py -3.12 -m venv venv
./venv/Scripts/python.exe -m pip install -r requirements.txt      # para usarlo
./venv/Scripts/python.exe -m pip install -r requirements-dev.txt  # además, para desarrollar
./venv/Scripts/python.exe scripts/install_hooks.py                # hook de pre-commit
```

Las versiones están fijadas a propósito: son las que se usaron para construir el índice y
medir la calidad. Sin fijarlas, una instalación de dentro de tres meses trae otra cosa y las
mediciones dejan de ser reproducibles sin que nadie se entere.

Falta el índice: no está en git (pesa ~21 GB). Se descarga ya construido desde
[Hugging Face](https://huggingface.co/datasets/Gullax/indice-legal-colombia) o se reconstruye
con `index/build_index.py` + `index/build_fts.py`.

Comprobar que todo está bien:

```sh
./venv/Scripts/python.exe -m pytest tests/ -q     # 257 tests
check.bat                                          # lint + formato + tests
```

Comandos de uso:

```
./venv/Scripts/python.exe index/build_index.py     # construir/actualizar índice vectorial (Chroma)
./venv/Scripts/python.exe index/build_fts.py       # construir el índice léxico (FTS5) a partir de Chroma
./venv/Scripts/python.exe index/buscar.py "consulta"  # probar búsqueda por CLI
./venv/Scripts/python.exe mcp_server/server.py      # levantar servidor MCP
./venv/Scripts/python.exe gui/server.py             # GUI web local (abre navegador solo)
```

La GUI (`gui/server.py`) es la forma recomendada de uso diario: búsqueda
híbrida con citas, y opcionalmente una respuesta redactada en español por un
modelo local vía Ollama (checkbox "Redactar respuesta con IA local"), ambas
100% locales sin llamadas externas.

## Fine-tuning y modelo local

`finetune/` tiene el pipeline completo para entrenar un modelo chico (LoRA en Colab, GPU
gratuita) que responda citando fuentes en el formato de `index/responder.py`, exportarlo a
GGUF (`finetune/exportar_gguf.py`) y evaluarlo (`finetune/evaluar.py`, banco de preguntas
real generado y juzgado con Claude). Se compararon 4 candidatos sobre 150 preguntas reales
y ganó **Qwen2.5-1.5B**, que le gana incluso a la generación más nueva (Qwen3) a este
tamaño de parámetros: a esta escala pesó más el tamaño que la generación. Qwen3.5 se
descartó por un bug real del conversor de llama.cpp para su arquitectura híbrida (no
carga, sin importar el tamaño del modelo).

Las cifras de acierto de cada candidato están en las mediciones internas
(`docs/MEDICIONES.md`, no versionado), no aquí.

## Próximos pasos

1. **Subir el acierto de la búsqueda**, que es el cuello de botella real. Dos vías
   preparadas y no confirmadas: reordenar los candidatos con un modelo que lee pregunta y
   pasaje juntos (`index/reordenar.py`), y afinar el embedding sobre este mismo corpus
   (`finetune/generar_pares_embedding.py` + `finetune/colab_afinar_embedding.ipynb`).
   Cualquiera de las dos se juzga contra la partición de prueba del banco, que no se usa
   para ajustar nada.
2. **Volver a medir la memoria del índice** con el embedding nuevo, antes de contratar
   hosting: la cifra que hay en `docs/DESPLIEGUE_INDICE.md` es del modelo anterior y es
   la que decide el escalón de precio.
3. **Desplegar el servidor del índice** y fijar su URL por defecto en el ejecutable.
4. Publicar el índice construido en Hugging Face Hub (`scripts/publicar_indice_hf.py`)
   para que otros lo usen sin tener que reconstruirlo.
5. Reintentar Corte Suprema cuando su backend esté disponible (sigue en 0 documentos;
   comprobado de nuevo el 6-sep-2026, responde 502).
6. Consejo de Estado sigue bloqueado por WAF — no hay plan de reintento hasta que aparezca
   una vía de acceso pública real.

Cerrado ya: la cuantización del modelo (se distribuye Q4_K_M, ver `docs/EMPAQUETADO.md`),
el `.spec` de PyInstaller y la decisión de arquitectura híbrida nube+API.
