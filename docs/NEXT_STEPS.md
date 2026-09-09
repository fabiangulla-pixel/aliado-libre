# NEXT_STEPS — Aliado Libre

Estado al 7-sep-2026.

## Siguiente tarea concreta

**Afinar el embedding sobre este corpus, en Colab con GPU.**

Todo está preparado: `finetune/data/pares_embedding.jsonl` (936 pares, todos los
perfiles al 99-100%) y `finetune/colab_afinar_embedding.ipynb`, ambos ya en la
carpeta de Drive. Solo hay que abrirlo, poner GPU y ejecutar.

Por qué es lo siguiente y no otra cosa: lo demás ya se probó y está medido.

- El índice e5-large: adoptado, 33,5% de recall@5 en datos apartados.
- El reranker: +10 puntos (43,5%), confirmado. Encendido en escritorio con GPU
  desde el 9-sep-2026; en el servidor sigue siendo decisión del operador.
- Reordenar más profundo: **no sirve**, el acierto se satura en 40 candidatos.
- Rechunkear: **descartado con datos**, no hay truncamiento.

Lo que queda es que ninguno de los dos modelos entiende este dominio ni esta
forma de preguntar. Afinar el embedding es la única palanca sin usar. Si
funciona, el paso siguiente es afinar el reranker con los mismos pares.

**Se mide contra la partición de prueba** (D-06), que sigue sin usarse para
ajustar nada. Y ojo con D-07 al comparar: el mismo modelo dio 41,0% en CPU y
43,5% en GPU sobre las mismas consultas.

## Después

2. **Recalcular la factura del hosting.** La cifra que sostenía la elección de
   plan se calculó con el embedding viejo y está marcada como no válida: el
   nuevo pesa ~4× más y la memoria decide el escalón de precio. **No contratar
   nada hasta volver a medirla.**
3. **Medir el reranker sobre 200 candidatos en GPU** — ya está preparado
   (`36fe17f`), sin correr. Es la medición que decide si entra.
4. **Terminar el afinado del embedding** con los 936 pares equilibrados
   (`6862f6d`). Los negativos no son al azar: son los documentos equivocados que
   el buscador trae hoy.
5. **Resolver el recaudo** (D-01): pasarela, cuenta, figura jurídica y sus
   implicaciones tributarias en Colombia. Ver `docs/RECAUDO.md` — y leer la
   alerta sobre impuesto de ganancia ocasional antes de recibir el primer peso.
6. **Decidir el nombre nuevo** (`docs/NOMBRE.md`) y verificar la disponibilidad
   de verdad, no por ausencia de sitio web.
7. **Corte Suprema de Justicia**: el ingester corre con reintento persistente
   esperando una ventana estable del servidor de la Corte (502 intermitente).
8. Actualizar el README: dice 257 pruebas, son 272.

## Al llegar al MSI

- **Si el MSI trae GPU con CUDA, esto cambia el proyecto entero**: el reindexado
  y el afinado del embedding se hicieron en Colab porque en CPU local no eran
  viables. Verificarlo es lo primero.
- Recrear el venv (`pip install -r requirements.txt`), **nunca copiarlo**. Las
  versiones están pinneadas a propósito (D-05): instalar exactamente esas.
- Este repo vive en `C:\Users\Lenovo\aliado-libre` y **no está en Drive**:
  hay que clonarlo desde GitHub o copiarlo a mano.
- `data/respaldo_legalize_co/` es un repo git anidado (legalize-co, 71.900
  normas). Clonarlo aparte.
- El índice (Chroma + FTS5) es grande y regenerable: no copiarlo, reconstruirlo
  con `build_index.py` + `build_fts.py`, o bajarlo de Hugging Face.
- Las variables `ALIADO_INDICE_URL` / `ALIADO_INDICE_TOKEN` / `HF_TOKEN` se
  configuran a mano en el equipo nuevo. **No van al repo.**
