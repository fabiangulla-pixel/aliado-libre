# Plan de la noche del 10-sep-2026 (Fabian durmiendo)

Encargo: esperar a ParrillaPRO, reindexar, seguir trabajando hasta donde se
pueda, y apagar el PC al terminar.

## Orden

1. ESPERA a que terminen los 2 `banco_cli.py` del Boletin de hidrologia
   isotopica #3 (ParrillaPRO). No se toca nada suyo.
2. Cerrar LM Studio y Ollama (autorizado por Fabian: los modelos eran para
   ParrillaPRO esta noche y ya cumplieron). Liberan 12,8 GB de VRAM.
3. Apartar el indice roto -> `index/chroma_db.roto_9sep` (2,3 GB, NO se borra).
4. Reindexar (~849.000 fragmentos) + reconstruir FTS5, encadenado.
5. Medir recall@5 sobre `finetune/eval/banco_prueba_200.json`.
   Referencias: indice sano viejo 33,5% · indice roto del 9-sep 0,5%.
6. Si el recall es razonable, regenerar los 20 casos de la abogada desde el
   indice bueno (los de `revision_juridica_limpia_v2.html` salieron del roto).
7. Actualizar PROJECT_STATE, SESSION_LOG y memoria. Commit local.
8. Apagar el PC.

## Lo que NO voy a hacer

- **No hago push.** Fabian no lo ha autorizado y sigue sin autorizarlo.
- **No borro** el indice roto ni nada del trabajo de ParrillaPRO.
- **No apago** si queda algo corriendo o algo sin guardar (ver condiciones).

## Condiciones para apagar

Se apaga SOLO si todas se cumplen:
- Ningun `banco_cli.py` vivo (el trabajo de ParrillaPRO termino por su cuenta).
- Ningun `reindexar_con_gpu.py` vivo.
- `git status` limpio en aliado-libre (todo commiteado).
- Este informe y la memoria escritos.

Si el reindexado falla, se apaga igual, pero dejando el fallo escrito aqui y en
la memoria. Un fallo documentado cierra la noche; un proceso a medias no.

## Si algo se tuerce

- **CUDA out of memory**: no deberia pasar ya, con los 12,8 GB liberados. Si
  pasara igual, bajar `batch_size` de 64 a 16 en `reindexar_con_gpu.py`.
- **El reindexado muere**: reanuda solo; se relanza. El indice bueno se va
  construyendo encima de si mismo, no se pierde lo hecho.

## Estado al empezar

Commit `eb054ad`, 344 tests verdes, lint y formato limpios, arbol limpio.
8 commits locales sin subir.

## Incidente 22:53 — el lanzador detenido no estaba detenido

`TaskStop` sobre la tarea de fondo mato el envoltorio de bash, **pero no el
script desprendido**: el primer lanzador (PID 25500, de las 22:27:44) siguio
vivo 13 minutos, escribiendo en el mismo log que el relanzado de las 22:40:36.
Se vio porque el log traia **dos series de timestamps interleavadas** (:42/:44 y
:04/:07/:11).

Si no se hubiera visto, los dos lanzadores habrian pasado la espera a la vez y
lanzado **dos reindexados concurrentes sobre el mismo indice**. Peor: el archivo
del script se reescribio dos veces mientras el primero corria, y bash lee los
scripts de forma incremental, asi que ese proceso estaba ejecutando una mezcla
de dos versiones.

Se mato el 25500 con sus hijos antes de que arrancara ningun reindexado. El
superviviente arranco a las 22:54:02, y se confirmo que hay **un solo**
`reindexar_con_gpu.py` (PID 5532).

**Leccion: tras TaskStop de un script de fondo, verificar por PID que murio, y
nunca reescribir un .sh que puede estar corriendo — escribir uno nuevo.**

## Nota 22:54 — cierre de LM Studio parcial

`Stop-Process` dio "Acceso denegado" en un proceso de LM Studio. Da igual: la
GPU quedo libre igualmente (2.034 MiB de 16.303, 0% de uso) porque fabia-6b ya
habia parado su trabajo y gemma estaba descargado. No se insiste.

## Contexto del trabajo de ParrillaPRO (de fabia-6b, 22:53)

Era una comparativa de 11 modelos locales sobre el mismo manuscrito. La paro al
confirmar el diagnostico: medir unos modelos en CPU y otros en GPU daria un
ranking falso. Hay que rehacerla con las capas en GPU, cuando Fabian decida.
Pidio el dato de velocidad real en GPU que salga de este reindexado.

## 23:30 — la desaceleracion no es degradacion

El ritmo cayo de 68 a 43 frag/s y la ETA subio de 257 a 318 min. Medido antes de
alarmarse:

- GPU al **89% de media** en 30 muestras de 1 s (25 al 100%, con caidas a 0
  durante los upserts a Chroma). Sigue siendo trabajo de GPU.
- Los fragmentos **no miden lo mismo segun la fuente**: 921 caracteres de media
  en `corte_constitucional` (por donde empezo) y 1.204 en `dian` (donde va).
  68 x 921/1204 = 52 frag/s. La caida es proporcional al tamano: los tokens/s
  son constantes.

**Conclusion: medir el avance en frag/s enganya cuando el corpus es heterogeneo.**
La ETA real depende de que fuentes queden, no del ritmo instantaneo. Estimacion
honesta: entre las 3:30 y las 5:30.

`dian.json` es con diferencia la fuente mas pesada del corpus (mas de la mitad
de los fragmentos), pese a tener 25.927 documentos frente a los 71.900 de
legalize_co.

## Si esta sesion muere antes de que termine

El reindexado es un proceso desprendido: sigue solo. Lo que se pierde es el
monitor, la verificacion, el commit final y el apagado. Nada se corrompe, y
`_run/verificar_tras_reindexado.py` se puede correr a mano despues.

## Lista de cierre tras el reindexado (ampliada 23:45)

1. `_run/verificar_tras_reindexado.py` — conteo, FTS5, prueba de cordura,
   recall@5 con intervalo por conglomerados.
2. Regenerar los 20 casos de la abogada (`regenerar_20_casos_limpios.py` y
   `generar_html_limpio_v2.py`, ya corregidos) y **comprobar que el HTML trae
   100 bloques `<details>`**, no 0 como el del 9-sep.
3. **Actualizar las cifras de 718.388 fragmentos** en README (lineas 32, 94, 157)
   y en PROJECT_STATE por el conteo real.
4. **`docs/DESPLIEGUE_INDICE.md` queda obsoleto**: sus cifras de hosting (5,12 GB
   de RAM, ~21 GB de disco, "Render Pro NO alcanza") se calcularon sobre 718.388
   fragmentos. El indice nuevo tiene ~29% mas. Medir RAM y disco reales y
   corregir, porque de ahi sale una decision de contratar.
5. Nota para el CHANGELOG: el indice se construyo con la rama "DADO EN ... a los"
   del patron de cierre inerte (los `\b` eran retrocesos). Fallo conservador: el
   indice conserva algunas coletillas ceremoniales. Ya esta arreglado en codigo,
   pero **el indice en disco no lo refleja**.
6. Suite completa + lint + formato, commit, informe, dato de velocidad a fabia-6b,
   apagado.

## 00:20 — ETA corregida: entre las 5:30 y las 6:00

El ritmo bajo de 45 a 36 frag/s. Medido para distinguir la causa: GPU al **86%**
de media (30 muestras), frente al 89% de las 23:30. Chroma NO se vuelve mas lento
al crecer; el cuello sigue siendo la codificacion.

O sea que la bajada es tamano de fragmento. Recalculado en caracteres, que es la
unidad estable: quedan ~816 millones a ~43.000 car/s -> **5,2 horas**.

Descartado acelerar: con la GPU al 86% subir el lote da poco, y media precision
cambiaria los vectores del indice respecto a como se codifican las consultas
(fp32). Cambio sin validar = lo que rompio el indice el 9-sep.
