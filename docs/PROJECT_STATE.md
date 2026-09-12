# PROJECT_STATE — Aliado Libre

Última verificación: **12-sep-2026**, en el MSI. Comprobado, no recordado.

> ✅ **El índice funciona.** Reindexado completo el 12-sep-2026 a las 04:38:
> **1.049.705 fragmentos** + FTS5 cuadrando, corpus `e422ffbae7186cb8`
> (145.560 documentos). Recall@5 **36,5%** con reranker, 24,5% sin.
>
> ⚠️ **No comparar con el 33,5% / 43,5% del 7-sep-2026**: aquella cifra salió de
> un corpus más pequeño y se retiró como línea base el 12-sep. El porqué, en
> `docs/MEDICIONES.md`; desde ahora el corpus y el troceo quedan grabados en los
> metadatos del índice para que esto no se pueda repetir.
>
> 🔶 Pendiente de decisión humana: la **revisión de 20 casos**
> (`finetune/eval/revision_humana.html`) sigue sin hacerse desde el 7-sep. Hasta
> que se haga, el 93% de punta a punta y el 86% de utilidad real son hipótesis,
> no resultados, y no deben publicarse.

## Estado funcional

**En desarrollo. No apto para uso profesional todavía.** La capa que redacta
respuestas está en calibración y no alcanza el umbral de acierto fijado.

- `pytest tests/ -q` → **342 pasan, 0 fallan** (84 s), lint y formato limpios.
- Búsqueda operativa (con el índice sano) sobre **928.086 fragmentos** de 7 entidades colombianas,
  con citas verificables.
- Servidor MCP (`buscar_normativa()`) operativo en modo local (`stdio`).
- GUI web local operativa; `.exe` de 29 MB + modelo.

### El cuello de botella es la RECUPERACIÓN, no el LLM

Causa raíz verificada: el modelo de embeddings anterior tenía
`max_seq_length = 128` tokens (~450 caracteres) y **el 76% de los fragmentos
supera los 500 caracteres** — en 3 de cada 4, el vector solo representaba el
encabezado. Además era un modelo de *paráfrasis* donde hace falta uno de
*recuperación*. Esto explica la rareza ya medida: que BM25 explicara el 100% de
los aciertos de un solo método.

**CONFIRMADO (7-sep-2026, madrugada).** El índice `multilingual-e5-large` a 512
tokens está adoptado y medido, y encima se midió lo siguiente:

| | recall@5 (200 consultas apartadas) |
|---|---|
| Índice e5-large | 33,5% |
| **+ reranker (ventana 40)** | **43,5%** |

- El reranker (`bge-reranker-v2-m3`) da +10 puntos, confirmado sobre la partición
  de prueba que no se usó para elegir nada (McNemar p=0,0081 en la corrida CPU).
  Está cableado en `IndiceBusqueda.buscar`, o sea que lo usan la GUI, el servidor
  MCP y `responder`, y **se enciende solo cuando hay GPU** (9-sep-2026). El
  cliente remoto queda fuera por construcción: el .exe no lleva la pila de ML.
- **Lo que cuesta encenderlo, medido el 9-sep-2026 en la RTX 5080** con seis
  consultas reales: la búsqueda pasa de 0,06 s a 1,57 s. Ensanchar la ventana a
  40 candidatos cuesta 0,01 s; el resto es el cross-encoder. En CPU son ~57 s, y
  por eso allí no se enciende. La cifra de 0,66 s que circulaba era optimista.
- **Media precisión en GPU**: el modelo se carga en float16, que es 2,9x más
  rápido (3,49 s → 1,19 s por consulta sobre 60 consultas del banco apartado) y
  **ordena idéntico**: mismo top-1, mismo top-5 y en el mismo orden en 60 de 60,
  con el ancla dentro del top-5 en los mismos 16 casos. Los +10 puntos medidos en
  float32 se heredan enteros.
- El servidor del índice **queda fuera de esa regla a propósito**
  (`quedarse_fuera_de_la_regla_automatica()` fija `ALIADO_RERANKER_ACTIVO=0` si el
  operador no dijo nada): allí cada segundo es una factura.
- **Reordenar más profundo NO sirve**: ventanas de 40, 100 y 200 dan el mismo
  recall@5. El reranker ya tiene delante el documento correcto y no lo reconoce.
- **El techo de la recuperación es 75%**: en el 25% de las consultas el fragmento
  correcto no aparece ni entre 200 candidatos. Cuando aparece, su posición
  mediana es 8 — justo fuera de lo que el modelo lee.
- **El chunking NO es el problema** (se descartó con datos): los fragmentos están
  topados en 1.500 caracteres y el 0,0% supera los 512 tokens del modelo.

Dónde está ahora el cuello de botella: ni el embedding ni el reranker saben
distinguir el pasaje correcto cuando lo tienen delante, porque la pregunta está
en lenguaje corriente y el pasaje en jurídico. **La única palanca sin probar es
enseñarles el dominio**: el material para afinar el embedding está listo (936
pares, `finetune/data/pares_embedding.jsonl`) y el notebook también.

Las cifras completas viven en **`docs/MEDICIONES.md`** (creado el 12-sep-2026;
no se versiona, porque recoge resultados sin revisión humana). Empieza con la
regla de comparación: dos recalls solo valen uno contra otro si salieron del
mismo corpus y del mismo troceo.

### Cobertura del corpus

✅ Gestor Normativo (2.381 normas, con grafo de vigencias) · Supersociedades
(4.999 conceptos) · Corte Constitucional (36.853 sentencias, 1992-2026) · SIC
(500 providencias) · DIAN · Superfinanciera (18.569 en catálogo) · legalize-co
(71.900 normas, respaldo GitHub)
⏳ Corte Suprema de Justicia — el ingester funciona (GraphQL sin auth) pero el
servidor de la Corte da 502 intermitente; corriendo con reintento persistente.
🔴 Consejo de Estado, SUIN-Juriscol, jurisprudencia.ramajudicial.gov.co —
bloqueados por WAF.

El proyecto **no pretende** cubrir toda la data jurídica de Colombia: cubre lo
que tiene fuente abierta confirmada (`docs/fuentes.md`), y cuando el índice no
tiene algo la app debe decirlo, distinguiendo "no está en el índice" de "no sé".

## Arquitectura

- `ingest/` — ingesters por entidad
- `index/` — `build_index.py` (Chroma, vectorial) y `build_fts.py` (FTS5,
  léxico, derivado de Chroma); `buscar.py` para probar por CLI
- `gui/server.py` — GUI web local, la forma recomendada de uso diario
- `mcp_server/server.py` — servidor MCP (API `mcp` 2.x)
- `servidor_indice/` — índice remoto (Docker, Render); ver `docs/DEPLOY.md`
- `finetune/` — LoRA del modelo propio y afinado del embedding
- `tests/` — 368 pruebas

Tres modos de uso, los elige el usuario según su máquina: todo local · modelo
local + índice en la nube · servidor MCP.

**Cuidado con las cifras de recursos**: el índice ocupa ahora **~21 GB de disco**
(no 11) y pica en **5,12 GB de RAM** (no 2,3) — las cifras viejas eran del
embedding anterior. Eso descarta el plan Render Pro de 4 GB; ver
`docs/DESPLIEGUE_INDICE.md`.

## Comandos

```bash
./.venv/Scripts/python.exe -m pip install -r requirements.txt       # uso
./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt   # desarrollo
./.venv/Scripts/python.exe scripts/install_hooks.py                 # hook pre-commit

./.venv/Scripts/python.exe -m pytest tests/ -q     # 344 pruebas, 75 s
check.bat                                          # lint + formato + tests
make check                                         # equivalente vía Makefile

./.venv/Scripts/python.exe index/build_index.py        # índice vectorial (Chroma)
./.venv/Scripts/python.exe index/build_fts.py          # índice léxico (FTS5)
./.venv/Scripts/python.exe index/buscar.py "consulta"  # probar búsqueda
./.venv/Scripts/python.exe mcp_server/server.py        # servidor MCP
./.venv/Scripts/python.exe gui/server.py               # GUI web local
```

**Empaquetado:** `aliado_libre.spec` (PyInstaller) → `.exe` de 29 MB.
Se distribuye la cuantización **Q4_K_M** (940 MB), no la q8_0 (2.950 MB).
**Despliegue:** `Dockerfile` + `render.yaml`; ver `docs/DEPLOY.md` y
`docs/DESPLIEGUE_INDICE.md`.

Las versiones están fijadas **a propósito**: son las que construyeron el índice
y midieron la calidad. Sin fijarlas, las mediciones dejan de ser reproducibles
sin que nadie se entere.

## Dependencias externas

- Ollama (capa conversacional local) · Chroma (vectorial) · SQLite FTS5 (léxico)
- `multilingual-e5-large` (embeddings, reindexado en curso) + reranker
- Hugging Face Hub (publicación del índice) · Render (hosting del índice remoto)
- GPU: **no disponible en el Lenovo**; el reindexado se hizo en Colab

## Variables de entorno

Ningún secreto vive en el repo ni debe añadirse.

| Variable | Para qué | Obligatoria |
|---|---|---|
| `ALIADO_INDICE_URL` | URL del índice remoto | solo en modo nube |
| `ALIADO_INDICE_TOKEN` | token del índice remoto | solo en modo nube |
| `ALIADO_RERANKER_ACTIVO` | activa el reranker | no |
| `HF_TOKEN` | publicar el índice en Hugging Face | solo para publicar |
| `PORT` | puerto del servidor (lo inyecta Render) | no |

El `.exe` **exigía** una de estas variables para poder buscar; corregido en
`b6e257d`.

## Errores y limitaciones conocidas

1. **La hipótesis del reindexado no está confirmada.** Falta medir e5-large
   contra el mismo banco apartado. Es lo que decide si el problema de
   recuperación quedó resuelto.
2. **La factura del hosting está calculada con el modelo viejo y NO es válida.**
   El embedding nuevo pesa ~4× más y la memoria decide el escalón de precio.
   Marcado en la guía de despliegue: **no contratar nada hasta volver a medir.**
3. **El recaudo del dinero sigue sin resolver** (pasarela, cuenta, figura
   jurídica, implicaciones tributarias). En Colombia una donación incrementa el
   patrimonio de quien la recibe y puede generar impuesto de ganancia ocasional.
   Ver `docs/RECAUDO.md`. No improvisar.
4. Corte Suprema: el servidor de la Corte da 502 intermitente. Tres fuentes más
   están bloqueadas por WAF.
5. El nombre del proyecto va a cambiar (`docs/NOMBRE.md`), con la advertencia de
   que un dominio sin uso no es un dominio libre.
6. El README dice 257 pruebas; son 272.

### Medido y descartado (vale tanto como lo que funciona)

- **Reescritura de consultas con el modelo propio: no sirve.** 160 consultas
  pareadas, sin mejora, 15 s por consulta. Un modelo que acierta poco tampoco
  sabe reformular.
- **Filtro de palabras vacías: gana velocidad, no acierto.** De 7,82 s a 0,39 s
  (20×), acierto estadísticamente igual. Se queda igualmente, porque el coste
  escalaba con la longitud de la pregunta y castigaba justo al usuario que más
  rodeos da.

## Último trabajo realizado

Sesión del 6-sep-2026: se **retiró** una conclusión ya escrita sobre la
cuantización. Decía que Q4_K_M perdía precisión frente a q8_0, con prueba
estadística detrás — pero las respuestas de una se habían generado en GPU y las
de la otra en CPU. Repetida con ambas en CPU, la diferencia desaparece dentro
del ruido. Consecuencia: se distribuye la Q4_K_M, un tercio del tamaño.

También: cuatro fallos que habrían roto el índice remoto el día del despliegue
(modelo de embeddings desalineado entre servidor y buscador, errores HTTP
contestados sin leer la petición, cliente que se rendía ante un servidor
despertando, y el juez sin reportar costo real).
