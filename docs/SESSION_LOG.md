# SESSION_LOG — Aliado Libre

Bitácora breve. El detalle sesión a sesión está en `CHANGELOG.md`, que es
extenso y explica el porqué de cada cosa.

---

## 10-sep-2026 — El reindexado del 9-sep dejó el índice inservible

Medido, no supuesto: **recall@5 = 0,5%** sobre las 200 consultas apartadas
(`finetune/eval/banco_prueba_200.json`), contra el 33,5% del índice anterior.
Tres causas independientes, todas del mismo cambio:

1. **El limpiador de ceremonial se comía el documento.** `PATRON_CIERRE` cortaba
   por `FIRMA`, `MINISTRO`, `PRESIDENTE` y `CONGRESO` sueltos, sin límite de
   palabra ni ancla de final, y con `DOTALL` se llevaba todo lo que siguiera.
   "confirma", "firmará" y "el Presidente de la República" disparaban el corte.
   Sobre el corpus real: **se perdía el 77% de los caracteres** y el **12,2% de
   los documentos salía con cero fragmentos**, o sea desaparecía del índice.
   En `gestor_normativo` el 99,75% quedaba truncado a menos de la mitad.
2. **Los pasajes se codificaron sin el prefijo `passage: `** que e5 necesita,
   mientras las consultas sí llevan `query: `. El comentario de `index/buscar.py`
   afirmaba que el índice se construía con él; el script que lo construyó no lo
   hacía.
3. **El índice léxico se borró y nunca se reconstruyó.** El script elimina
   `index/fts_index.db` al empezar y no lo vuelve a crear, así que la búsqueda
   híbrida perdió su mitad FTS5 — en silencio, porque `_fts` devolvía `None` sin
   decir nada, con los pesos del RRF calibrados para una fusión que ya no pasaba.

Y el índice **ni siquiera terminó**: 158.000 fragmentos en disco, no los 226.000
del mensaje del commit. El script borraba el índice bueno antes de empezar, así
que la corrida interrumpida dejó el proyecto sin índice utilizable.

**Los 20 casos de `revision_juridica_limpia_v2.html` salieron de ese índice. No
se pueden mandar a la abogada.**

### Arreglado

- `ingest/chunking.py`: fórmulas de cierre ancladas a principio de línea, como
  frase completa, y solo si aparecen en el último 30% del documento. Ningún
  documento con texto puede salir con cero fragmentos. Retención medida sobre el
  corpus real: **99,7% de los caracteres, 0 documentos perdidos** (antes 22,9% y
  12,2%). Proyección: ~849.000 fragmentos, el mismo orden que el índice sano de
  718.388.
- Modelo, colección y prefijos pasan a vivir solo en `index/buscar.py` y los
  importan `index/build_index.py`, `index/build_fts.py` y `reindexar_con_gpu.py`.
  Los tres tenían constantes propias: `build_index.py` seguía apuntando al modelo
  viejo de 384 dimensiones y `build_fts.py` a la colección vieja.
- `reindexar_con_gpu.py` ya no borra el índice antes de tener uno nuevo, reanuda
  sobre lo ya indexado, verifica el conteo final y encadena la reconstrucción del
  FTS5.
- Falta el índice léxico → `RuntimeWarning`, una vez por proceso.
- 9 tests de regresión nuevos (chunking y aviso de FTS). **342 en total**, lint y
  formato limpios.
- `docs/MEDICIONES.md` se citaba en código y en cinco documentos, y nunca existió
  (está en `.gitignore`). Las citas vivas apuntan ahora a `docs/PROJECT_STATE.md`.

**Pendiente y bloqueante: reindexar.** Sin eso el programa no busca. El índice en
disco hoy es el roto.

## 7-sep-2026 — Cierre para migración a PC MSI

Sesión de infraestructura, sin cambios funcionales.

- **Pruebas: 272 pasan, 0 fallan, en 75 segundos.** (El README dice 257;
  quedó anotado como pendiente.)
- Creados `docs/PROJECT_STATE.md`, `DECISIONS.md`, `NEXT_STEPS.md` y este
  archivo, más `CLAUDE.md` en la raíz.
- Se detectó que había **11 commits sin pushear**, no 6: la referencia local de
  `origin/main` estaba desactualizada. Todo el trabajo del 4 al 6 de septiembre
  existía solo en este disco.

## 6-sep-2026 (tarde) — Una conclusión retirada y cuatro fallos del despliegue

- **Se retiró** la recomendación sobre la cuantización. Estaba escrito, con
  prueba estadística, que Q4_K_M perdía precisión frente a q8_0. La comparación
  no era válida: una se generó en GPU y la otra en CPU. Repetida con ambas en
  CPU sobre las mismas 150 preguntas y el mismo juez, la diferencia desaparece
  dentro del ruido. Se distribuye la Q4_K_M — 940 MB frente a 2.950 MB.
- Cuatro fallos que no se ven en uso local pero habrían roto el índice remoto:
  el servidor descargaba el modelo de embeddings viejo mientras el buscador
  pedía el nuevo; los errores HTTP se contestaban sin leer la petición; el
  cliente se rendía ante un servidor despertando; el juez no reportaba el costo
  real de la API.
- La factura del hosting quedó marcada como **no válida** (calculada con el
  modelo viejo).
- Preparado sin correr: material y entrenamiento para afinar el embedding
  (936 pares, negativos reales, solo mitad dev), y `docs/NOMBRE.md`.

## 6-sep-2026 — El cuello de botella era la búsqueda

Causa raíz verificada del bajo acierto: el embedding truncaba a 128 tokens y el
76% de los fragmentos supera los 500 caracteres — el vector solo representaba el
encabezado. Además era un modelo de paráfrasis donde hace falta uno de
recuperación. Explica la rareza ya medida (BM25 explicaba el 100% de los
aciertos de un método). Arrancó el reindexado con `multilingual-e5-large` a 512
tokens en GPU (Colab). Se decidió el modelo Wikipedia y el no-registro.

Medido y descartado: reescritura de consultas (no sirve, 15 s/consulta) y filtro
de palabras vacías (20× más rápido, acierto igual — se queda por equidad).

## 30-ago-2026 — GUI web local, capa Ollama, reindex resiliente, LoRA
Reescritura de `build_index.py` para subida resiliente a Chroma; corregida la
firma de caracteres que mató un reindex de 7,5 h.

## Antes
Ver `CHANGELOG.md` y `git log --oneline`.
