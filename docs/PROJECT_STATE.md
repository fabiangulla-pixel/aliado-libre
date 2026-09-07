# PROJECT_STATE — Aliado Libre

Última verificación: **7-sep-2026**, en el PC Lenovo, antes de migrar a un MSI.
Comprobado en esta sesión, no recordado.

## Estado funcional

**En desarrollo. No apto para uso profesional todavía.** La capa que redacta
respuestas está en calibración y no alcanza el umbral de acierto fijado.

- `pytest tests/ -q` → **272 pasan, 0 fallan** (75 s). El README todavía dice
  257; el número real hoy es 272.
- Búsqueda operativa sobre **718.388 fragmentos** de 7 entidades colombianas,
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

**En curso, sin confirmar:** reindexado completo con `multilingual-e5-large` a
512 tokens, hecho en GPU (Colab) porque en CPU local no era viable. **Falta
medir el índice nuevo contra el mismo banco.** Hasta que eso se haga, la
hipótesis sigue siendo hipótesis.

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
- `tests/` — 272 pruebas

Tres modos de uso, los elige el usuario según su máquina: todo local (~11 GB
disco, ~2,3 GB RAM) · modelo local + índice en la nube · servidor MCP.

## Comandos

```bash
./venv/Scripts/python.exe -m pip install -r requirements.txt       # uso
./venv/Scripts/python.exe -m pip install -r requirements-dev.txt   # desarrollo
./venv/Scripts/python.exe scripts/install_hooks.py                 # hook pre-commit

./venv/Scripts/python.exe -m pytest tests/ -q     # 272 pruebas, 75 s
check.bat                                          # lint + formato + tests
make check                                         # equivalente vía Makefile

./venv/Scripts/python.exe index/build_index.py        # índice vectorial (Chroma)
./venv/Scripts/python.exe index/build_fts.py          # índice léxico (FTS5)
./venv/Scripts/python.exe index/buscar.py "consulta"  # probar búsqueda
./venv/Scripts/python.exe mcp_server/server.py        # servidor MCP
./venv/Scripts/python.exe gui/server.py               # GUI web local
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
