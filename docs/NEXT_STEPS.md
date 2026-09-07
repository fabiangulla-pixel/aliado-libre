# NEXT_STEPS — Aliado Libre

Estado al 7-sep-2026.

## Siguiente tarea concreta

**Medir el índice reindexado con `multilingual-e5-large` contra el banco
apartado.**

Es lo que decide todo lo demás. El reindexado completo a 512 tokens ya se hizo
en GPU (Colab), pero **la hipótesis no está confirmada**: falta correr la
medición contra la mitad de prueba del banco, que se dejó intacta justamente
para esto (D-06).

Si el recall sube como predice el diagnóstico, la recuperación deja de ser el
cuello de botella y se puede volver a la capa que redacta. Si no sube, el
diagnóstico estaba incompleto y hay que rehacerlo — no seguir adelante.

Ojo con D-07: la medición del índice nuevo tiene que correrse en el **mismo
hardware** que la del viejo, o no compara nada.

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
