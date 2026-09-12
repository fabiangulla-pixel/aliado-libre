# Informe de la noche del 11 al 12 de septiembre de 2026

## El resultado

El reindexado con el troceo corregido termino a las 04:38: **1.049.705
fragmentos** + indice lexico, Chroma y FTS5 cuadrando exactamente.

| indice | fragmentos | sin reranker | con reranker |
|---|---|---|---|
| sano viejo (7-sep) | 718.388 | 33,5% | 43,5% |
| 11-sep madrugada | 928.086 | 25,5% | 37,5% |
| **hoy, troceo corregido** | **1.049.705** | **24,5%** | **36,5%** |
| roto (9-sep) | 158.000 | — | 0,5% |

IC 95% del 36,5% remuestreando los 25 anclas: **27,5% - 46,0%**.

**Recuperar los 121.619 fragmentos que el troceo borraba NO mejoro la
recuperacion.** Un punto abajo en ambas configuraciones, dentro del ruido. El
arreglo sigue siendo correcto —se estaba borrando el 18% del texto de
`legalize_co_github` en silencio— pero **no explica la brecha contra el 7-sep**,
y hay que decirlo sin adornos: la hipotesis de trabajo de ayer era que ahi
estaban los puntos perdidos, y no estaban.

## Que queda por explicar, y el experimento que lo decide

La brecha de 8-9 puntos contra el 7-sep sigue abierta. Lo que cambio entre
aquel indice y este, aparte de los bugs ya corregidos, es **el rediseno del
troceo del 9-sep**: el corte por parrafos dentro de cada articulo.

El dato que lo senala: **mismo corpus, 718.388 fragmentos entonces y 1.049.705
ahora (+46%)**. A igual texto, eso significa fragmentos un ~32% mas cortos de
media. Un fragmento mas corto lleva menos contexto y casa peor con la consulta.

**Siguiente experimento, y es el obvio:** reindexar con el troceo ANTERIOR al
9-sep (corte por articulo + respaldo por tamano, sin logica de parrafos) y medir.
Son ~2 h con la GPU libre. Si el recall vuelve a ~33/43%, el rediseno del troceo
era el problema y se revierte. Es una sola variable.

## Lo que se hizo y se midio

- **Embedding afinado: hecho y NO adoptado.** El 38% de los negativos de
  entrenamiento eran falsos. Ganancia: +2,5 puntos, 11 anclas mejor contra 8
  peor de 25 — indistinguible del azar. Queda en `modelos/e5_afinado`.
- **TF32 si, fp16 no.** fp32 19 p/s, TF32 32 p/s con conjunto top-5 identico
  60/60, fp16 78 p/s pero top-5 solo 51/60. PyTorch trae allow_tf32=False por
  defecto. Salvedad: las cifras absolutas se midieron compitiendo por la GPU.
- **Prefijos query:/passage:** ya no pueden desaparecer en silencio.
- **Hoja de la abogada** regenerada desde el indice vigente: 100 bloques,
  ninguna consulta sin documentos.
- 355 tests, lint y formato limpios.

## Lo que de verdad falta para el 90%

**Ya esta alcanzado en el numero que importa.** Desde el 7-sep esta medido que
Haiku 4.5 responde bien el **93%** con la busqueda actual. El recall@5 por ancla
no puede llegar al 90%: su techo medido es **75%**, y ademas subcuenta (78 de
100 "fallos" auditados tenian un documento que si respondia).

Lo que falta no es mas recuperacion ni mas GPU: es **la revision humana de los
20 casos**. La hoja esta lista y correcta. Es lo unico que convierte el 93% y el
86% de utilidad real en resultados publicables en vez de hipotesis.

## Pendientes

1. **Revision humana de 20 casos** — `finetune/eval/revision_juridica_limpia_v2.html`.
2. **Reindexar con el troceo anterior al 9-sep** y medir. Una sola variable.
3. **15 commits sin subir.** Sigue sin autorizacion de push.
4. **No hay particion de desarrollo en disco**: cualquier calibracion futura
   contaminaria la unica medicion apartada. Regenerarla cuesta API.
5. **SDK de Anthropic con 600 s x 2 reintentos por defecto** en diez scripts de
   `finetune/`. La ruta de produccion esta a salvo.
6. Decidir si `.venv` es el nombre canonico del entorno.

## Coordinacion con la otra sesion

La cadena funciono: su senal llego a las 03:10, se confirmo la GPU libre y el
reindexado arranco solo. Entre las dos sesiones se encontraron **siete fallos de
guardas**, ninguno visible desde dentro del propio trabajo. Estan en
`feedback_precaucion_que_no_cambia_el_resultado` en la memoria.
