# SESSION_LOG — Aliado Libre

Bitácora breve. El detalle sesión a sesión está en `CHANGELOG.md`, que es
extenso y explica el porqué de cada cosa.

---

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
