# Informe de la noche del 10 al 11 de septiembre de 2026

Encargo: esperar a ParrillaPRO, reindexar, trabajar hasta donde se pueda y
apagar el PC.

## Lo primero: el resultado que importa

**El indice esta reparado, pero NO recuperado.** Medido sobre las 200 consultas
apartadas (25 fragmentos ancla x 8 perfiles):

| | sin reranker | con reranker |
|---|---|---|
| Indice sano viejo (7-sep) | 33,5% | 43,5% |
| **Indice nuevo (hoy)** | **25,5%** | **37,5%** |
| Indice roto (9-sep) | — | 0,5% |

IC 95% del 37,5%, remuestreando los 25 anclas: **27,0% - 48,5%**.

La catastrofe esta resuelta (de 0,5% a 37,5%), pero queda **8 puntos por debajo
del 7-sep sin reranker y 6 con**. No se puede llamar exito.

**Cuidado con comparar mal:** el reranker se enciende solo cuando hay GPU, asi
que la primera medicion salio con el encendido. La comparacion honesta exige
emparejar: 25,5 contra 33,5, o 37,5 contra 43,5.

## Por que sigue por debajo: causa identificada y corregida

El troceo del 9-sep (`_cortar_respetando_parrafos`) **borraba los parrafos de
menos de 150 caracteres** dentro de los articulos largos. En texto juridico esos
son numerales, definiciones y clausulas operativas.

Medido sobre el corpus real: `legalize_co_github` conservaba el **82,3%** de su
texto y `supersociedades` el **91,7%**. El agregado parecia sano (104,3%) porque
el solape de `_cortar_por_tamanio` duplica texto en otras fuentes y compensaba la
perdida. **Mi propia verificacion de anoche no lo vio**: midio la retencion del
paso de limpieza ceremonial, no la del troceo.

Corregido y verificado: legalize_co pasa a 101,3%, supersociedades a 102,1%, y
los documentos que perdian mas del 10% bajan de 187 a 1 (de 1.750 muestreados).

**El indice en disco NO tiene este arreglo.** Hace falta reindexar otra vez para
saber si esos puntos vuelven. Son ~6 horas.

## Lo que se arreglo esta noche

1. **Chunking**: formulas de cierre ancladas y como frase completa (antes
   "confirma" y "el Presidente" truncaban el documento entero: se perdia el 77%
   del corpus y el 12,2% de los documentos desaparecia). Ningun documento con
   texto sale sin fragmentos. Ningun parrafo se borra. Ningun fragmento pasa del
   tope declarado.
2. **Contrato unico entre indexar y consultar**: modelo, coleccion y prefijos
   viven solo en `index/buscar.py`. `build_index.py` seguia en el modelo viejo de
   384 dimensiones y `build_fts.py` en la coleccion vieja.
3. **Prefijo `passage: `**, que el reindexado del 9-sep no aplicaba pese a que un
   comentario del codigo afirmaba lo contrario.
4. **Indice lexico FTS5** encadenado al reindexado, y aviso ruidoso si falta
   (antes la busqueda se degradaba a solo-vectorial en silencio).
5. **Reindexado reanudable**, que verifica el conteo y no borra antes de tener.
6. **Hoja de la abogada**: tenia CERO documentos (los calculaba y la plantilla no
   los imprimia) y los que iba a mostrar venian del indice viejo. Ahora trae los
   100 bloques, del indice vigente, con HTML escapado.
7. **Caracteres de control**: tres `\b` de una regex se habian escrito como bytes
   0x08, dejando muerta una rama del patron de cierre. Corregido, con un test que
   recorre todos los .py del repo.
8. **22 comandos documentados estaban rotos**: el repo decia `./venv/Scripts/` y
   el entorno se llama `.venv`.
9. **Cifras de hosting remedidas**: RAM 5,12 -> **6,43 GB**; disco ~21 -> **16,1
   GB**. Cualquier plan dimensionado para 5,12 GB se queda corto.

**348 tests** (eran 337, con 3 en rojo que nadie habia mirado), lint y formato
limpios.

## Metodologia: el banco no son 200 casos

Son **25 fragmentos ancla reformulados en 8 perfiles de usuario**. Es decir, 25
necesidades de informacion independientes, no 200. Un solo documento mueve el
resultado 4 puntos. Esto afecta por igual a las cifras historicas: el "+10 puntos
del reranker" son unos 2,5 anclas cambiando de lado, y el McNemar publicado supone
una independencia que no existe. Las cifras nuevas van con intervalo por
conglomerados.

## Datos de la corrida

- Reindexado: **6 h 12 min** (22:54:02 a 05:06:03), 928.086 fragmentos.
- GPU al 86-89% de media: el cuello fue la codificacion, no Chroma.
- Ritmo 36-68 frag/s. La variacion NO es degradacion: es el tamano del fragmento
  segun la fuente (921 car/frag en corte_constitucional, 1.204 en dian). En
  caracteres el ritmo fue estable, ~43.000 car/s.

## Incidentes

- **`TaskStop` no mato el lanzador**: siguio vivo 13 minutos y estuvo a punto de
  disparar dos reindexados concurrentes sobre el mismo indice. Se detecto por
  timestamps interleavados en la bitacora.
- **Consultas de procesos que se cuentan a si mismas**: un filtro por linea de
  comando daba 9 procesos en vez de 2. Encadenar la espera a esa cuenta habria
  esperado para siempre.
- **Heredocs corrompiendo escapes**, cuatro veces.

Los tres estan guardados en memoria.

## Pendiente para Fabian

1. **Reindexar otra vez** con el troceo corregido, y volver a medir. Es lo unico
   que dira si se recuperan los 8 puntos. ~6 horas.
2. **NO mandar la hoja a la abogada todavia**: el instrumento ya es correcto,
   pero el indice del que sale aun no lo es.
3. **8 commits sin subir** (ahora 10). Sigue sin autorizacion de push.
4. Releer `docs/DESPLIEGUE_INDICE.md` antes de contratar nada.
5. Decidir si `.venv` es el nombre canonico (cambie 22 rutas a el).
