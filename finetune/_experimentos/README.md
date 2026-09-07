# Experimentos ya cumplidos

Aquí vive lo que **ya hizo su trabajo y no se vuelve a correr**. No es basura:
cada uno sostiene una decisión que hoy está tomada, y por eso se conserva con su
historial en vez de borrarse. Pero no forma parte de lo que se mantiene.

**No se garantiza que corran tal cual.** Varios ajustan `sys.path` contando con
estar un nivel más arriba; al moverlos aquí, sus importaciones pueden fallar. Se
guardan como evidencia de lo que se hizo, no como herramienta.

| Archivo | Qué respondió | Por qué ya no se usa |
|---|---|---|
| `ajustar_pesos_rrf.py` | Primera calibración del peso de BM25 frente al vectorial | La sustituyó `ajustar_pesos_rrf_v2.py`, recalibrada para el índice e5-large |
| `generar_dataset.py` | Los 50 primeros ejemplos de entrenamiento, escritos a mano | Lo sustituyó `generar_dataset_ampliado.py` y luego `generar_dataset_multifragmento.py`, que corrigió el desajuste de mostrar un solo fragmento cuando en producción llegan cinco |
| `colab_entrenar_qwen3_06b.ipynb`, `colab_entrenar_qwen3_17b.ipynb` | Entrenaron dos candidatos de la generación Qwen3 | Perdieron la comparación contra Qwen2.5-1.5B. A este tamaño pesó más el tamaño que la generación |
| `colab_entrenar_qwen35_08b.ipynb`, `colab_entrenar_qwen35_2b.ipynb` | Intentaron entrenar Qwen3.5 | Descartado: `convert_hf_to_gguf.py` de llama.cpp tiene un bug real con su arquitectura híbrida — exporta sin error y el binario no carga |
| `colab_reindexar_embeddings.py` + `.ipynb`, `hacer_notebook_reindex.py` | Primera versión del reindexado en GPU y el generador que convertía el `.py` en notebook | El reindexado que de verdad se corrió fue `colab_reindexar_embeddings_060926.ipynb`, que sigue en `finetune/` |

## Lo que NO está aquí, aunque lo parezca

`generar_dataset_ampliado.py` se ve superado por la versión multifragmento, pero
**tres scripts vivos lo importan** (`diagnosticar_busqueda.py`, `evaluar.py`,
`generar_dataset_multifragmento.py`): moverlo rompía las importaciones. Se queda
en `finetune/`.
