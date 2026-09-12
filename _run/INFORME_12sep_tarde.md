# 12-sep-2026 (tarde) — el experimento que no hay que correr

## Resumen

El plan de la mañana era reindexar con el troceo anterior al 9-sep (~2 h de GPU)
para ver si volvían los puntos de recall. **Ese experimento no se corre: su
premisa es falsa, y comprobarlo costó cuatro minutos de CPU.**

## La medición que lo decide

Se corrió el **código de troceo histórico literal** (commit `941ea9c`, el mismo
que construyó el índice del 7-sep) sobre el corpus de hoy:

| troceo | fragmentos | media de caracteres |
|---|---|---|
| `941ea9c` (7-sep, literal) | **1.042.474** | 1.258 |
| `42bf45f` (9-sep, el roto) | 226.988 | 1.128 |
| por tamaño (reconstruido hoy) | 1.039.750 | 1.256 |
| por párrafos (actual) | 1.049.705 | 1.183 |

El índice del 7-sep tenía **718.388** fragmentos. El mismo código, sobre el
corpus de hoy, da 1.042.474. Con el troceo fijado, la única variable que queda es
el corpus: **no era el mismo**. Los archivos de `data/raw` están fechados el 9-sep
a las 23:32, después de aquella medición.

## Qué se cae con eso

1. **El 33,5% / 43,5% del 7-sep deja de ser línea base.** Nunca fue comparable
   con las cifras posteriores. La "caída a 24,5%" se calculó contra una
   referencia de otro corpus.
2. **El razonamiento de los "fragmentos un 32% más cortos" era erróneo.** Entre
   el troceo viejo y el actual, sobre el mismo corpus, la diferencia real es del
   **1% en número de fragmentos y del 6% en longitud media**. Reindexar dos horas
   para comparar dos troceos casi idénticos no habría medido nada.
3. Un corpus mayor reparte los mismos 5 puestos entre más documentos candidatos,
   así que parte de la diferencia es mecánica. Cuánta, no se sabe: el índice del
   7-sep ya no existe en disco y no se puede remedir sobre el corpus de hoy.

## Lo que se comprobó y NO estaba roto

El medidor cuenta acierto si cualquiera de los 5 primeros resultados viene del
**mismo `documento_id`** (`finetune/medir_recuperacion.py:38`), no solo si
aparece el fragmento exacto. Se sospechó que cambiar el troceo invalidaba la
métrica, porque `documento::fragN` pasa a contener otro texto — comprobado: **10
de las 25 anclas tienen texto distinto entre los dos índices, 9 de ellas muy
distinto**. Pero el respaldo por documento lo absorbe. La métrica está sana.

## El arreglo: el corpus deja de ser una variable suelta

La causa raíz no es el troceo: es que **nada registraba con qué corpus y con qué
troceo se había construido un índice**, así que dos números de recall se podían
comparar sin que nadie notara que medían cosas distintas.

Desde ahora el indexador graba en los metadatos de la colección `corpus` (huella
sha256 de ids + longitudes), `documentos` y `troceo`, y **se niega a reanudar** un
índice cuya marca no coincida. Los dos índices en disco quedaron marcados con el
corpus `e422ffbae7186cb8` (145.560 documentos).

Guardas nuevas, todas con prueba negativa que demuestra que **sí** bloquean:

- reanudar un índice construido con el otro troceo (los ids coinciden entre
  troceos, así que el filtro de "ya indexados" se saltaba casi todo y dejaba un
  índice mezclado que cuadraba en el conteo);
- reanudar un índice poblado que no dice con qué troceo se hizo;
- reanudar con un corpus distinto del que lo construyó;
- pedir `ALIADO_DB_FTS` sin `ALIADO_DIR_INDICE`, que mediría el FTS5 de un índice
  contra el Chroma de otro.

Además, `reindexar_con_gpu.py` ya no redeclara las rutas del índice: las importa
de `index/buscar.py`. Tener dos copias es exactamente cómo indexador y buscador
acabaron apuntando a sitios distintos el 9-sep.

## Variables nuevas

- `ALIADO_TROCEO` = `parrafos` (por defecto) | `tamanio`
- `ALIADO_DIR_INDICE` / `ALIADO_DB_FTS` — construir y medir un índice alternativo
  al lado del de producción, sin quedarse sin búsqueda mientras dura el ensayo.

## Estado

368 pruebas (355 + 13), lint y formato limpios. `docs/MEDICIONES.md` existe por
fin, con la regla de comparación al principio.
