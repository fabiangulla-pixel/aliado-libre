# Estado al cierre del 11-sep-2026

## El proyecto queda SIN busqueda operativa. Es esperado, no un fallo.

- `index/chroma_db` tiene **692.000 de 1.049.705** fragmentos: reindexado a medias.
- `index/fts_index.db` **no existe**: se borra al empezar el reindexado y se
  reconstruye al terminar. Como no termino, no esta.
- Por tanto la GUI, el servidor MCP y `responder` NO devuelven resultados utiles
  hasta que el reindexado acabe.

## Como retomar (no hace falta empezar de cero)

    ./.venv/Scripts/python.exe reindexar_con_gpu.py

Salta los 692.000 ya hechos, encola el resto, verifica el conteo y reconstruye
el FTS5 al final. Quedan ~357.000 fragmentos: a los 58-79 frag/s medidos con la
GPU libre, unas 1,5-2 horas.

## Si manana hace falta buscar ANTES de terminar el reindexado

El indice bueno anterior (928.086 fragmentos, recall@5 37,5% con reranker) esta
entero en `index/chroma_db.troceo_viejo`. Para volver a el:

    mv index/chroma_db index/chroma_db.parcial_11sep
    mv index/chroma_db.troceo_viejo index/chroma_db
    ./.venv/Scripts/python.exe index/build_fts.py

Tarda lo que tarde el FTS (unos minutos). Deshacer el cambio es simetrico.

## Lo que falta medir, y contra que

Cuando el reindexado termine, `_run/verificar_tras_reindexado.py` mide el
recall@5 con intervalo por conglomerados. Las referencias, todas sobre el mismo
banco de 200 consultas (25 anclas x 8 perfiles):

| indice | sin reranker | con reranker |
|---|---|---|
| sano viejo (7-sep) | 33,5% | 43,5% |
| 928.086 frags (11-sep madrugada) | 25,5% | 37,5% |
| roto (9-sep) | — | 0,5% |

El indice nuevo cambia UNA sola cosa respecto al de la madrugada: el troceo ya
no borra los parrafos de menos de 150 caracteres. Por eso la comparacion
correcta es contra 25,5% y 37,5%, y por eso NO se adopto el embedding afinado.

## Pendientes que no dependen de la GPU

1. **12 commits sin subir.** Sigue sin autorizacion de push.
2. **Hoja de la abogada**: el instrumento ya es correcto (100 bloques), pero hay
   que regenerarla desde el indice nuevo. No mandarla antes.
3. **Revision humana de 20 casos**: lo unico que convierte el 93% de punta a
   punta y el 86% de utilidad real en resultados en vez de hipotesis. No es
   trabajo de GPU.
4. **No hay particion de desarrollo en disco**: solo sobrevivio la de prueba.
   Cualquier calibracion futura contaminaria la unica medicion apartada.
   Regenerarla cuesta API; falta estimar el costo y aprobarlo.
5. **SDK de Anthropic con 600 s x 2 reintentos por defecto** en diez scripts de
   `finetune/` — los que producen las cifras del proyecto. La ruta de produccion
   esta a salvo (urllib con timeouts explicitos). Sin cerrar.
