# Changelog

## 2026-09-12 (tarde-2) — Piloto de 100 consultas: el sistema falla justo con quien fue hecho

### El resultado que importa: recuperación por perfil de usuario

Banco nuevo de 100 consultas escritas sobre el texto real del corpus, en las
palabras del usuario, repartidas en los ocho perfiles. **100 anclas
independientes**, no 25 reformuladas ocho veces como el banco anterior. Las
preguntas evitan a propósito el vocabulario del artículo: redactarlas copiando
el texto legal hace que la búsqueda acierte por coincidencia léxica.

| perfil | recuperación@5 |
|---|---|
| abogado_junior | 60,9% |
| mensaje_telegrafico | 40,0% |
| semi_tecnico_impreciso | 36,4% |
| ciudadano_medio | 23,5% |
| con_ruido_irrelevante | 20,0% |
| comerciante_practico | 7,1% |
| **adulto_mayor_informal** | **0,0%** |
| **baja_alfabetizacion** | **0,0%** |

Global 29,9% (26/87 anclados) frente al 36,5% del banco sintético. **Cero
aciertos en quince intentos** para las dos poblaciones que el proyecto dice
servir. La media global lo tapaba, y el banco anterior también: sus consultas
nacían del fragmento que debían recuperar.

### Se retira una afirmación: la cobertura no era el problema

Durante esta misma sesión se sostuvo que el corpus no tenía las leyes más
consultadas. **Era falso**, y salió de generalizar unos sondeos que devolvían
jurisprudencia. El conteo real por documento: Código Sustantivo del Trabajo
(Decreto 2663 de 1950) 218 fragmentos, Código de Comercio 629, CPACA 294,
Ley 100 de 1993 274, Ley 769 de 2002 175, Ley 1098 de 2006 167, Ley 1480 de
2011 96, Ley 675 de 2001 68, Ley 1266 de 2008 40, Ley 820 de 2003 36,
Decreto 2591 de 1991 23.

Prueba directa sobre nueve consultas típicas: la búsqueda trae la norma
correcta **4 de 9 veces, estando las nueve indexadas**. El hueco está en la
recuperación, no en el corpus, y eso cambia el plan: no hay que ingerir más.

Por eso el banco distingue `no_cubierto` (4 casos reales) de
**`responde_no_recuperado` (8 casos: el índice tiene la respuesta y la búsqueda
no la trae)**. Sin esa distinción el diagnóstico apunta al sitio equivocado, y
un banco que afirma ausencias falsas castiga a la aplicación por acertar.

### El banco se valida antes de medir con él

`validar_banco_piloto.py` comprueba que cada ancla exista y que cada cita esté
LITERALMENTE en su fragmento: 95 anclas y 74 citas verificadas. Encontró un id
mal transcrito. Un banco de evaluación es una afirmación sobre el corpus, y si
la afirmación es falsa toda medición que salga de él es basura.

`correr_piloto.py` mide casi todo de forma determinista, sin juez: recuperación
por `documento_id`, y si lo que la respuesta pone entre comillas angulares
aparece de verdad en los fragmentos que recibió — que es la prueba de
alucinación más barata que hay. Sin `--ejecutar` no llama a ninguna API.

### El formato de respuesta que pidió el usuario

`PROMPT_SISTEMA` pasa a tres partes obligatorias: qué norma revisar, la cita
literal entre «», y qué significa para el caso de la persona. La cita literal
es además verificable por programa, así que el formato nuevo abarata la
evaluación además de servir mejor a quien consulta.

370 pruebas, lint y formato limpios.

## 2026-09-12 (tarde) — El experimento que no hay que correr: el corpus había cambiado

### La premisa era falsa, y comprobarlo costó cuatro minutos

El plan era reindexar con el troceo anterior al 9-sep (~2 h de GPU) para ver si
volvían los puntos de recall perdidos frente al 7-sep. Antes de gastarlos se
corrió el **código de troceo histórico literal** (commit `941ea9c`, el que
construyó aquel índice) sobre el corpus de hoy: da **1.042.474 fragmentos, no los
718.388** que tenía el índice del 7-sep.

Con el troceo fijado, la única variable que queda es el corpus, y **no era el
mismo**: los archivos de `data/raw` están fechados el 9-sep a las 23:32, después
de aquella medición. De ahí se siguen dos cosas:

- **El 33,5% / 43,5% del 7-sep se retira como línea base.** Nunca fue comparable
  con lo medido después. La "caída a 24,5%" se calculó contra otra cosa.
- **El razonamiento de los "fragmentos un 32% más cortos" era erróneo.** Entre el
  troceo viejo y el actual, sobre el mismo corpus, la diferencia real es del 1%
  en número de fragmentos y del 6% en longitud media. El experimento habría
  comparado dos troceos casi idénticos y devuelto "sin diferencia" por una razón
  que no era la del experimento.

Se sospechó también que cambiar el troceo invalidaba la métrica, porque
`documento::fragN` pasa a contener otro texto — y en efecto **10 de las 25 anclas
del banco tienen texto distinto entre los dos índices**, 9 de ellas muy distinto.
Pero `medir_recuperacion.py` ya cuenta acierto por `documento_id`, así que lo
absorbe. La métrica está sana; lo que estaba suelto era el corpus.

### El arreglo: el corpus y el troceo se graban dentro del índice

La causa raíz no era el troceo, sino que nada registraba **con qué corpus y con
qué troceo** se había construido un índice, de modo que dos recalls se podían
comparar sin que nadie notara que medían cosas distintas. El indexador graba
ahora `corpus` (huella sha256 de ids + longitudes), `documentos` y `troceo` en
los metadatos de la colección, y se niega a reanudar un índice cuya marca no
coincida. Los dos índices en disco quedaron marcados con `e422ffbae7186cb8`
(145.560 documentos).

Cuatro guardas nuevas, cada una con su prueba negativa que demuestra que **sí**
bloquea —una guarda que no puede negarse es falsa seguridad—:

- reanudar un índice construido con el otro troceo. Es la más traicionera: los
  ids de fragmento son `documento::fragN` en los dos modos, así que el filtro de
  "ya indexados" los daba por hechos y se saltaba casi todo, dejando un índice
  mitad de un troceo y mitad del otro, con el conteo cuadrando y sin un error;
- reanudar un índice poblado que no dice con qué troceo se hizo;
- reanudar con un corpus distinto del que lo construyó;
- pedir `ALIADO_DB_FTS` sin `ALIADO_DIR_INDICE`, que mediría el FTS5 de un índice
  contra el Chroma de otro.

`reindexar_con_gpu.py` deja además de redeclarar las rutas del índice y las
importa de `index/buscar.py`: tener dos copias es exactamente cómo indexador y
buscador acabaron apuntando a sitios distintos el 9-sep.

### Variables nuevas

- `ALIADO_TROCEO` = `parrafos` (por defecto) | `tamanio`, para que el troceo sea
  una variable elegible del experimento y no un cambio de código.
- `ALIADO_DIR_INDICE` / `ALIADO_DB_FTS`, para construir y medir un índice
  alternativo al lado del de producción sin quedarse sin búsqueda entretanto.

### Deuda documental saldada

- **`docs/MEDICIONES.md` existe por fin.** Se citaba desde el 6-sep en cinco
  sitios sin existir. Recoge las mediciones dispersas y abre con la regla de
  comparación. No se versiona (`.gitignore:27`): guarda cifras sin revisión
  humana.
- **Hosting remedido sobre el índice definitivo**: 6,43 GB de RAM y **17,2 GB**
  de disco (15,0 Chroma + 2,2 FTS). El documento seguía recomendando planes con
  la cifra de 5,12 GB del 7-sep en el cuerpo y en la conclusión.
- `PROJECT_STATE.md` seguía anunciando en rojo, dos días después, que el índice
  no servía.

368 pruebas (355 + 13), lint y formato limpios. Informe:
`_run/INFORME_12sep_tarde.md`.

## 2026-09-09 (tarde) — Reordenar llega al escritorio, y el bug del cuerpo no drenado reaparece en la GUI

### El reranker llega al escritorio, que era donde no estaba

Los +10 puntos de recall@5 del cross-encoder llevaban meses medidos y adoptados,
pero cableados **solo en `servidor_indice/server.py`**. Quien usaba el programa en
su equipo —la GUI, el servidor MCP, `responder`— buscaba sin ellos. La mejora
confirmada del proyecto no le llegaba al usuario.

Ahora vive en `IndiceBusqueda.buscar`, que es el punto por donde pasan todos los
que consultan el índice local. El cliente remoto queda fuera **por construcción**:
el .exe no lleva la pila de ML con la que reordenar, y allí decide el servidor.
El servidor deja de duplicar el ensanchado de ventana y el reordenado: tener dos
sitios que hacen lo mismo es tener dos sitios que se desincronizan.

Quién decide, en `index.reordenar.activo()`: **hay GPU o no**. La señal es el
costo medido, no una preferencia. `ALIADO_RERANKER_ACTIVO` sigue mandando en
ambos sentidos, y el servidor del índice se queda fuera de la regla a propósito
(`quedarse_fuera_de_la_regla_automatica()`): desplegar en un host con aceleradora
no debe empezar a gastar por su cuenta.

### Media precisión: 2,9x más rápido con el mismo orden, exactamente

En GPU el modelo se carga en `float16`. Lo que autoriza el cambio no es la
velocidad sino el acuerdo, comprobado sobre las 60 primeras consultas del banco
apartado con sus candidatos reales:

| | float32 | float16 |
|---|---|---|
| Tiempo por consulta | 3,49 s | **1,19 s** |
| Mismo top-1 | — | **60/60** |
| Mismo top-5, mismo orden | — | **60/60** |
| Ancla dentro del top-5 | 16/60 | **16/60** |

O sea que los +10 puntos medidos en float32 se heredan enteros: no es una
aproximación que haya que volver a validar. De paso, los 40 candidatos van en un
solo lote; el batch por defecto (32) los partía en dos sin ganar nada.

### La cifra de 0,66 s era optimista

Al medir el camino completo contra el índice real (718.388 fragmentos, seis
consultas reales, RTX 5080), el costo honesto es:

| | |
|---|---|
| Búsqueda como estaba (k=5) | 0,06 s |
| Ensanchar la ventana a 40 candidatos | +0,01 s |
| Reordenar 40 en float16 | 1,50 s |
| **Total por consulta** | **1,57 s** |

Los 0,66 s que circulaban en la bitácora no se reproducen: el reordenado real
cuesta 1,50 s con media precisión, y habría costado 3,5 s sin ella. Aun así el
intercambio se sostiene —1,5 s por +10 puntos de recall en una consulta legal— y
la conclusión de encenderlo en escritorio no cambia. La que cambia es la cifra, y
se corrige donde estaba mal escrita (README, `docs/PROJECT_STATE.md`,
`docs/DESPLIEGUE_INDICE.md`, `docs/NEXT_STEPS.md`).

### Y de paso, el mismo bug del cuerpo no drenado, ahora en la GUI

El hook de pre-commit hizo fallar la suite con `ConnectionResetError
[WinError 10054]` en `test_ia_externa_endpoint.py`. No era ruido: `do_POST` de
`gui/server.py` respondía **404 sin leer el cuerpo** que el cliente seguía
enviando, y `_leer_json` rechazaba igual en tres caminos más. En Windows eso no
llega como el 404 sino como una conexión abortada.

Es **exactamente el defecto que se arregló el 8-sep en `servidor_indice`**, donde
también era "el fallo intermitente de la suite". Que reapareciera en el otro
servidor es la razón de que la regla ya no esté copiada: vive en
`drenar_cuerpo.py` y los dos la usan.

Este pesa más que el del servidor del índice, porque `gui/server.py` es lo que
usa la gente.

La prueba negativa: con el arreglo revertido, **11 de 12 repeticiones fallan**; con
él, 25 de 25 pasan. Ese 1 que pasaba es la razón de que hagan falta repeticiones
—una sola petición no detecta esto— y de que llevara meses escondido.

`drenar_cuerpo` se añadió a `hiddenimports` del .spec y al test de empaquetado:
`gui/server.py` lo importa al arrancar, así que sin él el .exe no abriría.

### La clave de la API deja de vivir solo en el entorno

Para volver a auditar la métrica hacía falta `ANTHROPIC_API_KEY` exportada, y en
este PC no estaba: la clave no se migró del equipo viejo. Exigirla por entorno
obliga a exportarla en cada terminal nueva, y lo que pasa en la práctica es que
acaba pegada en el historial o en un archivo del repositorio.

`finetune/clave_api.py` la lee del entorno o de `~/.aliado_libre/credenciales.json`
—la misma carpeta fuera del repositorio que el .exe ya usa para el token del
índice— y si no hay ninguna, explica las dos formas en vez de soltar un traceback.
`auditar_metrica.py` ya la usa; los demás scripts de `finetune/` siguen pidiendo
la variable de entorno.

También quedó verificado el insumo de la auditoría: `candidatos_prueba.json` se
copió de Drive (55,5 MB) y se comprobó **parseándolo entero**, no por tamaño —200
consultas, la última íntegra con sus 200 candidatos. Son 133 fallos en @5 de 200,
que es exactamente el 33,5% de acierto ya reportado. Ver
[[feedback_drive_copia_silenciosa_truncada]].

### Pruebas

278 → 337 tests. Nuevo `tests/test_buscar_reordena.py` (contrato del punto único:
cuántos candidatos se piden, cuántos se devuelven, que apagado no cueste nada, que
un reranker que no carga no rompa la búsqueda, y que el cliente remoto no reordene).
`tests/test_reordenar.py` cubre la regla de encendido y la media precisión, y
`tests/test_ia_externa_endpoint.py` el cuerpo drenado, con repeticiones porque el
fallo es intermitente.

**Un test cambió de signo**: `test_no_esta_conectado_a_la_busqueda_todavia`
afirmaba que `buscar()` no llamaba al reranker —era el guardián de que se midiera
antes de encenderlo—. Ahora afirma lo contrario.

## 2026-09-09 — El equipo nuevo cambia la cuenta del reranker, y aparece un fallo de instalación que no era nuestro

Sesión de montaje en el PC nuevo (RTX 5080 Laptop, 16 GB de VRAM). Además de dejar
el entorno funcionando, salieron tres cosas que valen más que el montaje.

### El reranker deja de ser caro donde hay GPU

Medido aquí, reordenar 40 candidatos cuesta **0,66 s**, frente a los 3,42 s de la
T4 de Colab y los ~57 s en CPU sobre los que se decidió dejarlo apagado. Con la
búsqueda en 0,04 s, una consulta completa con reranker sale por **~0,70 s** a
cambio de los +10 puntos de recall@5 ya confirmados en datos apartados.

La consecuencia es que `ALIADO_RERANKER_ACTIVO` merece revisarse: "encenderlo
convierte una búsqueda de 2 s en una de un minuto" era cierto en CPU y ya no
describe el modo escritorio con GPU. **La decisión no se toma en este commit**,
porque el servidor del índice sigue siendo el caso caro.

De paso, el **pico de RAM se replicó en hardware distinto**: 5,06 GB aquí contra
los 5,12 GB medidos antes. La cifra que decide el plan de hosting deja de depender
de una sola máquina.

### El programa se rompía en equipos con antivirus, y no era culpa del programa

Norton (y Avast, Kaspersky, ESET) interceptan el TLS: sustituyen el certificado
del servidor por uno propio, firmado por una raíz que está en el almacén de
Windows pero no en `certifi`. El navegador y `curl` no se enteran; Python falla
con `CERTIFICATE_VERIFY_FAILED`. Un usuario final habría visto ese error en inglés
al primer arranque, sobre una descarga que él no pidió.

Añadido `confianza_tls.py`, invocado desde la GUI y el servidor MCP: verifica
contra el almacén del sistema en vez de contra `certifi`. **No** se desactiva la
verificación —que es la receta habitual para este error—, y hay un test que falla
si alguien lo intenta. `truststore` pasa a estar declarado en `requirements.txt`,
porque ahora se importa directamente, y añadido al `.spec` para que viaje en el
`.exe`.

### El 413 seguía roto, y esta vez de forma reproducible

`test_buscar_con_cuerpo_enorme_da_413` fallaba 5 de 5 veces. La sesión del 7-sep
arregló los caminos 404 y 401, pero el de 413 seguía cerrando el socket sin drenar
el cuerpo, así que el cliente recibía un RST en lugar del mensaje. El docstring
prometía un `Connection: close` que el código nunca enviaba. Ahora se drena con
tope (`MAX_DRENAJE`), con su test negativo para que el límite no se pierda al
"arreglarlo".

### Higiene

- `.gitignore` ignoraba `venv/` pero no `.venv/`: un entorno virtual estaba a un
  `git add -A` de entrar al repositorio. Cubierto con `.venv*/`.
- Ruff analizaba el código de las dependencias dentro de los entornos con sufijo
  (`.venv312`) y reportaba 13 errores ajenos, rompiendo `make check`.
- Sigue pendiente: **PyInstaller no está declarado** en `requirements-dev.txt`
  pese a que `scripts/build_exe.py` y dos tests lo necesitan.

## 2026-09-07 — El cuello de botella no era la búsqueda, y la métrica estaba torcida

Sesión larga (madrugada y tarde). Dos hallazgos cambian el rumbo del proyecto, y
los dos consisten en descubrir que estábamos midiendo mal. Las cifras están en
`docs/MEDICIONES.md`, que no se versiona: siguen sin alcanzar el umbral acordado
para publicarlas.

### 1. Con la búsqueda de hoy, un modelo capaz ya responde casi siempre bien

Mismas preguntas, los mismos fragmentos recuperados, el mismo prompt y el mismo
juez. Lo único que cambia es quién redacta. El modelo propio afinado se queda muy
por detrás de un modelo de API, y no por poco: entre las preguntas comparables
**no hay una sola** en la que gane el modelo propio.

La diferencia más grave está en las preguntas cuya respuesta no está en los
fragmentos, donde lo correcto es callarse. El modelo pequeño se inventa una
respuesta buena parte de esas veces. El grande, ninguna.

El objetivo de calidad que nos fijamos no estaba lejos por culpa de la búsqueda:
estaba en qué modelo redacta. Encaja con la decisión de producto ya tomada —nube
por defecto, local como alternativa sin conexión— y significa que **a este tamaño
seguir afinando el modelo propio no tiene recorrido**. Conviene decirlo después de
cinco modelos entrenados y dos generaciones de dataset.

Generar una respuesta cuesta menos de medio centavo de dólar. Eso convierte el
recaudo en el pendiente urgente: por fin hay una cifra concreta que sostener.

### 2. Buena parte de nuestros "fallos" no eran fallos

El banco de evaluación marca **un** fragmento como correcto: aquel del que se
generó la pregunta. Pero el corpus tiene más de setecientos mil fragmentos y
muchas preguntas las responde otro igual de bien. Auditando cien de esos supuestos
fallos con un juez, en la gran mayoría había un documento que sí respondía.

La utilidad real de la búsqueda es bastante mayor de lo que veníamos reportando.
Las comparaciones entre técnicas siguen valiendo, porque el sesgo afectaba igual a
los dos lados de cada una; lo que no vale es la cifra absoluta, y así se estaba
usando al hablar del objetivo.

Queda preparada una revisión humana de veinte casos, con el veredicto del juez
oculto hasta que la persona marque el suyo. Hasta que alguien la haga, esto es una
hipótesis con buen aspecto y no un resultado.

### Cuatro técnicas medidas: una funciona, dos fallan, una da igual

- **Reordenar los resultados con un cross-encoder**: funciona, y es la única
  mejora de recuperación confirmada sobre datos apartados. Queda conectada al
  servidor y **apagada por defecto**: cuesta segundos por consulta y más memoria
  de la que ya pide el índice, así que encenderla es una decisión de factura.
- **Reordenar más candidatos**: mismo resultado que con pocos y varias veces el
  costo. El reordenador ya tiene delante el documento correcto y no lo reconoce.
- **Buscar con el pasaje jurídico que imagina un modelo**: empeora, y bastante.
  Inventa números de norma que suenan bien y son falsos, y la búsqueda léxica se
  va detrás de la cita inventada.
- **Traducir la consulta al vocabulario de la norma**: neutro. No se adopta; el
  código se conserva por si cambia el peso de la fusión.

También quedó descartado con datos que el problema fuera el troceado del corpus, y
medido cuál es el techo real de la recuperación: hay consultas cuyo documento no
aparece por ningún lado, y esas no las arregla ningún reordenamiento.

### Un error propio, corregido antes de que costara una GPU

El material para afinar el modelo de búsqueda estaba contaminado con un defecto
que la literatura tiene identificado: los ejemplos negativos se sacan de los
primeros resultados, que son justo los más propensos a ser correctos sin estar
etiquetados. Entrenar así le enseña al modelo a alejar del usuario documentos que
sí responden. El proceso ahora los limpia antes de entrenar.

### Lo que se arregló de camino

Cuatro cosas que habrían roto el servicio el día del despliegue: la imagen
horneaba el modelo de búsqueda equivocado, el servidor cortaba la conexión antes
de entregar sus propios mensajes de error, el cliente se rendía ante un servidor
que estaba despertando, y el ejecutable exigía una variable de entorno para poder
buscar. Además, el índice publicado servía una versión que el código ya no usa, y
las cifras de recursos estaban calculadas con el modelo anterior: ocupa el doble
de disco y más del doble de memoria de lo documentado, lo que descarta el plan de
hosting que se había elegido.

## 2026-09-06 (tarde) — Una conclusión que había que retirar, y cuatro fallos del despliegue

### Se retira la recomendación sobre la cuantización

Estaba escrito que la versión Q4_K_M perdía precisión de verdad frente a la q8_0, con
una prueba estadística detrás. **Esa comparación no era válida**: las respuestas de una
se habían generado en GPU y las de la otra en CPU, así que se comparaban dos cosas a la
vez. Repetida con ambas en CPU, sobre las mismas 150 preguntas y el mismo juez, la
diferencia desaparece dentro del ruido del muestreo.

Consecuencia práctica: **se distribuye la Q4_K_M**, que pesa 940 MB frente a 2.950 MB
—un tercio del ejecutable— sin una pérdida de precisión que estos datos puedan sostener.
Dicho con honestidad: "no se detecta diferencia" con 115 preguntas pareadas no es "no hay
diferencia"; una caída pequeña sería invisible a este tamaño de muestra.

La lección se queda escrita en `docs/MEDICIONES.md`: **el hardware donde se genera es una
variable del experimento**. Cambiar dos cosas a la vez sostuvo tres días una conclusión
falsa que casi triplica el tamaño de lo que se iba a repartir.

### Cuatro fallos que habrían roto el índice remoto el día del despliegue

Ninguno se ve desde el uso local de hoy. Los cuatro se ven el día que alguien apunte a
un servidor:

- La imagen del servidor descargaba el modelo de embeddings **viejo**, mientras el
  buscador ya pedía el nuevo. Como en el servidor se prohíbe descargar nada en caliente,
  habría arrancado y muerto. Ahora el nombre se lee de un solo sitio y hay un test que
  impide que vuelvan a separarse.
- El servidor contestaba sus errores (404, 401, 413) **sin leer la petición** que el
  cliente todavía estaba enviando. El resultado era que el usuario veía un error de red
  en vez del mensaje en español que sí se le había escrito.
- El cliente se rendía a la primera ante un servidor que estaba despertando, que es
  exactamente lo que hace un servidor barato tras un rato sin visitas. Ahora reintenta lo
  que se cura esperando, y solo eso.
- El juez de respuestas ahora dice cuánto costó de verdad la llamada a la API, en vez de
  dejarlo a ojo.

### La factura del hosting estaba calculada con el modelo viejo

El embedding nuevo pesa unas cuatro veces más que el anterior, y la memoria es justo lo
que decide el escalón de precio. La cifra que sostenía la elección de plan quedó marcada
como no válida en la guía de despliegue y en la configuración, con la instrucción de no
contratar nada hasta volver a medirla.

### Preparado, sin correr todavía

- Material y entrenamiento para **afinar el embedding sobre este corpus**: los ejemplos
  negativos no son al azar, son los documentos equivocados que el buscador trae hoy. Solo
  se usa la mitad de dev del banco; la de prueba queda intacta para poder medir después.
- `docs/NOMBRE.md`: candidatos para el nombre nuevo con la disponibilidad verificable, y
  la advertencia de que un dominio sin uso no es un dominio libre.

## 2026-09-06 — El cuello de botella era la búsqueda; modelo Wikipedia; sin registro

Sesión larga. Se identificó y atacó la causa raíz de la baja precisión, se fijó el
modelo de sostenimiento del proyecto, y se construyeron las funciones que hacen
falta para que otra persona pueda usar esto.

### El hallazgo: no es el LLM, es la recuperación

El banco coloquial de 1.583 consultas dio el número que de verdad describe el
producto, y es duro. Sobre las mismas preguntas y los mismos documentos, cambiando
solo **cómo está escrita la pregunta**, el acierto se desploma: el perfil de abogado
encuentra su documento varias veces más a menudo que el de una persona que pregunta
con sus propias palabras, y un perfil entero (adulto mayor, con rodeos) no acierta
ni una sola vez en 197 consultas. El modelo casi nunca ve el documento correcto, así
que da igual lo bueno que sea. Cifras exactas en `docs/MEDICIONES.md` (no versionado).

Causa raíz, verificada: el modelo de embeddings tiene `max_seq_length = 128` tokens
(~450 caracteres) y el **76% de los fragmentos supera los 500 caracteres**. En tres de
cada cuatro fragmentos, el vector solo representa el encabezado — que en una norma no
es la parte que responde. Y encima es un modelo de *paráfrasis* donde hace falta uno
de *recuperación*: una consulta coloquial y el artículo que la responde no se parecen
en la superficie. Esto explica lo que ya se había medido y quedó como rareza: que BM25
explicara el 100% de los aciertos de un solo método.

**En curso**: reindexado completo con `multilingual-e5-large` a 512 tokens, hecho en
GPU (Colab) porque en CPU local no era viable. La hipótesis todavía **no está
confirmada**: falta medir el índice nuevo contra el mismo banco.

### Medido y descartado (vale tanto como lo que funciona)

- **Reescritura de consultas con el modelo propio: no sirve.** Sobre 160 consultas
  pareadas no mejora nada y cuesta 15 s por consulta. La razón de fondo: convierte
  "cuanto se paga de tiembre" en "sueldo mensual salario fijo". Un modelo que acierta
  poco tampoco sabe reformular.
- **Filtro de palabras vacías: gana velocidad, no acierto.** De 7,82 s a 0,39 s por
  consulta de media (20×), con acierto estadísticamente igual. Se queda igualmente:
  el coste escalaba con la longitud de la pregunta, así que castigaba con 15 s de
  espera justo a quien más rodeos da, es decir al usuario menos experto.

### Producto: modelo Wikipedia

Gratuito, sostenido por aportes voluntarios; nube por defecto para usuarios externos
y todo-local como banco de pruebas. Documentado en `docs/PRINCIPIOS.md`, con el
pendiente sin resolver anotado: **el recaudo del dinero**.

### No se guardan consultas — como código, no como promesa

- El servidor del índice **registraba la IP de cada petición**. Con la hora, eso
  identifica a quien pregunta por su despido o su tutela. Eliminado.
- Los errores registran el **tipo** de excepción, nunca su detalle: el texto de una
  excepción puede arrastrar la consulta del usuario hasta el log.
- `tests/test_no_registro.py` falla si alguien reintroduce cualquiera de las dos.

### Funciones nuevas

- **Filtro por entidad**: acotar la búsqueda a la SIC, la DIAN, la Corte
  Constitucional… o cruzar varias. Y la lista muestra **también lo que NO está**, con
  el motivo: quien no sabe que el Consejo de Estado no está cubierto puede creer que
  su asunto no existe. Detalle que decide si el filtro sirve: al filtrar hay que pedir
  más candidatos antes de fusionar, o una entidad pequeña como la SIC (0,7% del
  corpus) nunca aparecería.
- **Tablero de notas**: el usuario aparta las fuentes que le sirven y las exporta a
  `.md` o `.txt` con identificador, fuente y enlace. Vive en el navegador
  (`sessionStorage`, muere al cerrar la pestaña) y no toca el servidor.
- **IA externa opcional con la clave del usuario**: se muestra el **costo estimado
  antes** de llamar y el **costo real después**. La clave se usa para una llamada y se
  descarta; nunca vuelve en una respuesta ni en un error.
- **Verificador determinista de anclaje** conectado a la interfaz: marca todo número
  de norma, artículo, plazo o cifra que no esté en los fragmentos recuperados. Sobre
  150 respuestas reales no marcó ni una buena.

### Diagnóstico que redirige la estrategia

De 104 respuestas incorrectas del modelo propio, el 65% **no inventa nada**: cita el
artículo 38 cuando la respuesta estaba en el 39 del mismo decreto. Es un fallo de
*relevancia*, no de anclaje, y ninguna comprobación de cadenas puede verlo. El camino
hacia más precisión pasa por elegir mejor el pasaje (reranker, modelo mayor), no por
controlar alucinaciones.

### Bugs reales corregidos

- **sqlite entre hilos**: la conexión al índice léxico se guardaba en el objeto y el
  servidor da un hilo por petición. La primera búsqueda funcionaba y la segunda moría.
  Ninguna prueba lo vio porque todas hacían una sola consulta. Lo encontró el usuario.
- La selección de índice en desarrollo decidía por si fallaba un import que en el
  repositorio nunca falla, así que la app local intentaba hablar con un servidor
  inexistente.
- El `.exe` *onefile* sobrevivía a `terminate()` y dejaba un proceso huérfano ocupando
  el puerto; una sonda posterior le hablaba a ese huérfano.
- Un fragmento falso de prueba usaba claves inventadas: la prueba validaba un contrato
  que no existe.


## 2026-09-04 — Q4 cuantizado, índice en la nube, .exe autónomo y medición honesta

Sesión larga. Se cerraron los cinco pendientes abiertos, se decidió la dirección del
producto (que estaba a la deriva respecto al README) y se descubrió que el banco de
pruebas existente era ciego al fallo real del producto.

### Producto: decisión explícita

El README decía "solo hace búsqueda, no genera texto" y "100% local por diseño", pero tres
sesiones de fine-tuning habían llevado el proyecto a otro sitio. Decidido y documentado:
es un **asistente que responde en prosa**, para **abogado y ciudadano por igual**, con
**tres modos** (todo local / modelo local + índice en la nube / servidor MCP) que elige
el usuario según su equipo. Consecuencia: la precisión pasa a ser la métrica que manda.

### Resuelto

- **Q4_K_M del modelo ganador**: 940 MB (32% del f16). ~~Pero **cuesta precisión** frente
  al q8_0: contraste pareado sobre las mismas preguntas, con significancia estadística
  (McNemar) — la caída es real, no ruido. Recomendación: distribuir el q8_0.~~
  **RETIRADO el 6-sep-2026**: aquella comparación no era válida (una versión se había
  generado en GPU y la otra en CPU, así que comparaba dos cosas a la vez). Repetida en
  igualdad de condiciones, la diferencia cabe en el ruido. **Se distribuye el Q4_K_M.**
  Ver la entrada del 6-sep.
- **Índice en la nube listo, sin desplegar**: `servidor_indice/` (stdlib) e
  `index/cliente_remoto.py`, que no importa torch ni chromadb — ese es el punto de mover
  el índice. Costo real documentado en `docs/DESPLIEGUE_INDICE.md`.
- **`.exe` de 28,6 MB, ya autónomo**: `index/responder.py` migrado de Ollama a
  `llama_cpp.Llama`. Verificado abriendo el PYZ (buscar cadenas da falso negativo) y
  arrancando el binario contra un índice remoto.
- **Índice publicado**: 10,67 GB verificados en HF (`Gullax/indice-legal-colombia`),
  Chroma + FTS5. Publicar solo el vectorial dejaba el dataset inservible.
- **Corte Suprema**: sigue 502. `/filters` responde 200; el POST real no. No es del cliente.

### Bugs reales encontrados

- **sqlite entre hilos**: `IndiceBusqueda` guardaba una conexión FTS5 en `__init__` y el
  servidor es `ThreadingHTTPServer`. La primera búsqueda funcionaba y la segunda moría.
  Ninguna prueba lo vio porque todas hacían UNA consulta. Lo encontró el usuario usando
  la app.
- **Selección de índice rota en desarrollo**: se decidía por si fallaba el import de
  `cliente_remoto`, que en el repo nunca falla.
- **El .exe onefile sobrevivía a `terminate()`**: el bootloader deja un hijo vivo que
  ocupaba el puerto, y una sonda posterior le hablaba a ese huérfano.
- **Fragmento falso con esquema inventado** en una prueba: validaba un contrato inexistente.

### Medición: el banco anterior era ciego

`banco_prueba.json` lo generó un LLM a partir de los fragmentos, así que heredó su
vocabulario jurídico. El recall que medía describía a un abogado, no a un ciudadano.

- **`finetune/eval/banco_coloquial.json`**: 1.583 consultas sobre 198 fragmentos reales,
  8 perfiles de usuario equilibrados (baja alfabetización, adulto mayor, ciudadano medio,
  comerciante, semi-técnico impreciso, telegráfico, con ruido, y abogado como control),
  estratificadas por las 7 fuentes. Verdad de referencia por construcción: sin juez,
  sin coste.
- **`finetune/medir_recuperacion.py`** y **`finetune/calibrar_abstencion.py`**:
  recall@k por perfil y por fuente, y la curva precisión/cobertura para elegir cuándo
  callarse. Acercarse al 100% exige abstenerse, no acertar más.
- **`index/verificar_anclaje.py`**: comprobación determinista de que cada dato duro de la
  respuesta esté en los fragmentos. Sobre las respuestas reales evaluadas no produjo
  ningún falso positivo (cifras en `docs/MEDICIONES.md`, no versionado). Conectado a la GUI.
- **Diagnóstico que redirige la estrategia**: de las respuestas incorrectas, la gran mayoría no
  inventa nada — citan el artículo 38 cuando la respuesta estaba en el 39 del mismo
  decreto. Es un fallo de *relevancia*, no de anclaje: ninguna comprobación de cadenas
  puede verlo. El camino no pasa por controlar alucinaciones sino por elegir mejor el
  pasaje (reranker, modelo mayor).

### Rendimiento: la búsqueda penalizaba al usuario menos experto

Cada palabra de la consulta se volvía un término `OR` de FTS5 sobre 718.388 fragmentos,
así que el coste escalaba con la longitud: 15 s para el perfil "adulto mayor" (72
palabras) frente a 0,5 s para el telegráfico. Filtrando palabras vacías y topando a 12
términos: media del banco de **7,82 s a 0,39 s, veinte veces más rápido**.


## 2026-09-03 — Fine-tuning en Colab (4 modelos comparados), búsqueda optimizada de RAM

Sesión larga (~8h): se resolvió el fine-tuning local inviable moviéndolo a Colab (GPU
gratuita), se compararon 4 modelos con datos reales, y se encontró y arregló un cuello de
botella real en la búsqueda que afectaba a cualquier modelo por igual.

### Resuelto

- **Fine-tuning movido a Colab**: 4 notebooks nuevos, uno por modelo (`finetune/colab_entrenar_qwen35_08b.ipynb`,
  `_qwen35_2b`, `_qwen3_06b`, `_qwen3_17b`) — cada uno fijo a un solo `MODELO_BASE`, sin
  selector editable, para eliminar el riesgo de mezclar experimentos en la misma sesión de
  Colab (pasó una vez: los dos primeros `.zip` resultaron ser el mismo modelo 0.5B con
  nombres distintos). Cada notebook verifica el `hidden_size` real contra el esperado
  (leído del propio `config.json` del repo de HF) y **para con error** si no coincide.
- **Bug real de sobreajuste encontrado en el dataset de entrenamiento original** (50
  ejemplos, `finetune/generar_dataset.py`): 3 de 10 ejemplos negativos usaban "fiducia
  mercantil" como tema y cero positivos — el modelo aprendió una correlación espuria
  (ese tema → "no sé") en vez del patrón general. Corregido con
  `finetune/generar_dataset_ampliado.py` (175 ejemplos, temas diversos, sin repetición
  en negativos) y luego `finetune/generar_dataset_multifragmento.py` (185 ejemplos con
  **5 fragmentos reales por ejemplo**, igual que en producción — el dataset original
  solo mostraba 1 fragmento, un desajuste real entre entrenamiento e inferencia que
  explicaba buena parte de las confusiones del modelo con fragmentos irrelevantes).
- **Causa raíz encontrada para el techo de precisión de la búsqueda**: midiendo con
  preguntas reales, el modelo de embeddings genérico (`paraphrase-multilingual-MiniLM-L12-v2`)
  no aportaba ningún hallazgo único sobre este corpus (español jurídico/histórico) — BM25
  explicaba el 100% de los aciertos de un solo método. Pesar igual ambos métodos en la
  fusión RRF dejaba fuera del top-5 documentos que BM25 ya rankeaba en el puesto #1.
  Doblar el peso de BM25 (`PESO_BM25 = 2.0` en `index/buscar.py`) subió el acierto en
  el top-5 sobre 40 preguntas reales (`finetune/ajustar_pesos_rrf.py`).
- **`index/buscar.py` reescrito para RAM baja**: `rank_bm25` (todo el corpus en listas de
  Python) reemplazado por SQLite FTS5 (`index/build_fts.py`, disco-residente). RAM medida
  con el índice completo cargado: **10GB → 2.3GB**. Esto es lo que hace viable pensar en
  hostear el índice en un servidor barato (~$5-25/mes) en vez de necesitar ~200 USD/mes
  solo por RAM.
- **Bug real en `finetune/evaluar.py`**: `n_ctx=4096` insuficiente (5 fragmentos largos +
  pregunta + `max_tokens` de respuesta superaban el límite, crash real a mitad de una
  corrida de 150 preguntas) — subido a 8192, y agregado checkpoint incremental (escribe
  `resultados.json` tras cada pregunta, no solo al final) para no perder progreso si algo
  falla a mitad de una corrida larga.
- **Evaluación local en CPU descartada por lentitud** (4 modelos × 150 preguntas ≈ 10h) a
  favor de generar las respuestas con GPU en Colab (`finetune/colab_evaluar_gpu.ipynb`) y
  juzgarlas aparte, local, con `finetune/juzgar_respuestas.py` (rápido, son solo llamadas a
  la API del juez, no cómputo pesado). El notebook lee todo directo desde una carpeta de
  Google Drive (`00_Programas y macros/aliado_libre_eval/`, fuera del proyecto en C: — el
  proyecto en sí sigue sin vivir en Drive, por la lentitud/fallos ya documentados de leer
  en lote desde ahí) para no depender de subir archivos a mano.
- **Qwen3.5 descartado**: bug real del conversor `convert_hf_to_gguf.py` de llama.cpp para
  su arquitectura híbrida (atención lineal + normal) — el modelo carga y se cuantiza sin
  error pero el binario resultante falla al cargar (`tensor 'blk.24.attn_norm.weight' not
  found`), confirmado en 0.8B y 2B, con el `llama-cpp-python` de pip y con un `llama-cli`
  compilado desde cero en esta sesión. Se compiló `llama-quantize`/`llama-cli` localmente
  (VS Build Tools 2022 + cmake) para diagnosticar esto y para poder generar Q4_K_M después.

### Resultado: comparación de 4 modelos (150 preguntas reales, juzgadas con Claude)

Ganó **Qwen2.5-1.5B**, por delante de Qwen3-1.7B, Qwen3-0.6B y Qwen2.5-0.5B en ese orden:
a esta escala pesó más el tamaño que la generación del modelo. Las cifras están en
`docs/MEDICIONES.md` (no versionado) — no se publican hasta alcanzar el objetivo de
precisión.

### Archivos nuevos (`finetune/`)
`exportar_gguf.py`, `probar_gguf.py`, `evaluar.py`, `juzgar_respuestas.py`,
`generar_dataset_ampliado.py`, `generar_dataset_multifragmento.py`, `diagnosticar_busqueda.py`,
`ajustar_pesos_rrf.py`, `precalcular_prompts.py`, `cuantizar_q4.py`,
`colab_entrenar_qwen35_08b.ipynb`, `colab_entrenar_qwen35_2b.ipynb`,
`colab_entrenar_qwen3_06b.ipynb`, `colab_entrenar_qwen3_17b.ipynb`, `colab_evaluar_gpu.ipynb`.

### Limpieza
Liberados ~14GB de disco local (17GB → 31GB libres): modelos Qwen3.5 muertos y sin usar en
caché de HF, `finetune/fusionados/` (resultados intermedios, reproducibles).

## 2026-09-01 — DIAN completado, diagnóstico real de la lentitud del fine-tuning en CPU

### Resuelto

- **DIAN escalado a las 3 materias**: relanzado con tope elevado (50.000);
  pasó de 20.000 (solo tributario + 15 de aduanero) a **25.927 documentos**
  (tributario 19.985, aduanero 5.567, cambiario 375). Ya no hay materias sin
  cubrir.
- **`finetune/entrenar.py` parametrizado**: acepta `[modelo_base] [nombre_salida]`
  por línea de comandos en vez de tener el modelo hardcodeado, con
  checkpoints separados por experimento (`checkpoints_<nombre_salida>/`) —
  necesario para poder comparar 0.5B vs 1.5B sin pisar resultados.
- **Causa real de la lentitud en CPU encontrada**: los checkpoints de Qwen
  cargan en `bfloat16` por defecto (`torch_dtype="auto"`), pero la CPU de
  esta máquina (AMD Ryzen 5 5500U) no tiene soporte de hardware para bf16
  (sin AVX512-BF16) — PyTorch lo emulaba por software, mucho más lento que
  usar `float32` nativo. Corregido: `dtype="float32"` explícito en la carga
  del modelo. El fix ayudó pero no fue suficiente por sí solo: incluso así,
  el primer step tardó ~40+ min en esta CPU — se concluyó que el hardware en
  sí (chip móvil de bajo consumo, sin GPU) no es viable para entrenar ni
  siquiera un modelo de 500M de parámetros en tiempo razonable.
- **`.gitignore`**: patrones `finetune/checkpoints*/` y `finetune/modelo_lora*/`
  (antes solo cubrían los nombres exactos sin sufijo) + `*.log` para los
  logs de scripts en background.
- **`requirements.txt`**: agregadas `peft`, `trl`, `accelerate`, `datasets`
  (ya estaban instaladas en el venv para el fine-tuning pero no declaradas).

### Decisión de arquitectura

- El adaptador LoRA NO reduce el tamaño del modelo a usar en producción —
  sigue necesitando el modelo base completo cargado. Como el criterio de
  éxito final es el tamaño del `.exe` distribuible (con el modelo
  **empaquetado dentro**, no vía Ollama externo), se decidió abandonar
  `Qwen2.5-3B` y probar en paralelo `Qwen2.5-0.5B-Instruct` y
  `Qwen2.5-1.5B-Instruct` como base — modelos mucho más chicos, mejor
  candidatos para terminar en un `.gguf` cuantizado embebido vía
  `llama-cpp-python` (no `transformers`+`torch`, que son inviables de
  empaquetar — ver `feedback_pyinstaller_excluir_pila_ml`).
- **`finetune/colab_entrenar.ipynb`** (nuevo): notebook autocontenido para
  correr el mismo entrenamiento en la GPU gratuita de Google Colab (T4),
  donde bf16 sí tiene soporte de hardware real y debería tardar minutos en
  vez de días. Pide subir `finetune/data/entrenamiento.jsonl` y descarga un
  `.zip` con el adaptador resultante al terminar.
- **Intento de automatizar Colab por CDP con Chrome clonado**: se clonó
  `Profile 3` y se abrió una ventana de Chrome separada con el puerto de
  debug remoto — la sesión de Google no viajó (probablemente por DBSC,
  cookies de sesión atadas al dispositivo/instalación original). El perfil
  clonado se cerró y se borró correctamente. Conclusión: el fine-tuning en
  Colab se corre manualmente por ahora.

### Pendiente / próxima sesión

1. **Correr `finetune/colab_entrenar.ipynb` en Colab manualmente** (Fabián):
   subir el notebook, GPU T4, subir `entrenamiento.jsonl`, correr dos veces
   (una por cada `MODELO_BASE`/`NOMBRE_SALIDA`), descargar los dos `.zip` y
   descomprimirlos en `finetune/modelo_lora_05b/` y `finetune/modelo_lora_15b/`.
2. Con ambos adaptadores entrenados, comparar calidad de respuesta entre
   0.5B y 1.5B sobre preguntas reales del índice, y decidir cuál usar.
3. Escribir `finetune/exportar_gguf.py` (aún no existe) para convertir el
   adaptador ganador a GGUF cuantizado.
4. Cambiar el runtime de inferencia en producción de Ollama a
   `llama-cpp-python` (más liviano, sin dependencia de PyTorch) para poder
   empaquetar el modelo dentro del `.exe`.
5. Escribir el `.spec` de PyInstaller para Aliado Libre (hoy no existe
   ningún empaquetado a `.exe`, corre directo con `venv/Scripts/python.exe`)
   y medir el tamaño final real con cada modelo para decidir 0.5B vs 1.5B.
6. Corte Suprema sigue en 0 documentos (backend inestable, no se reintentó
   esta sesión).
7. Publicar el índice en Hugging Face Hub — sigue pendiente, decidido
   posponer (ya se tiene un `HF_TOKEN` de lectura funcional de esta sesión,
   pero habría que generar uno con permiso Write para publicar).

## 2026-08-30 — GUI web local, capa conversacional Ollama, reindex resiliente, fine-tuning LoRA

### Resuelto

- **Reindex completo**: `index/build_index.py` reescrito para subir a Chroma
  en lotes de 2000 en vez de un solo `encode()`+`upsert()` final — un job de
  7.5h había muerto en silencio al 9% sin nada guardado (probable OOM por
  contención con otra sesión concurrente en la misma máquina). Relanzado con
  el fix: **718.388 fragmentos de 119.708 documentos**, 7 fuentes.
- **Bug crítico en `scripts/_crawl_retry.py`**: el wrapper de reintentos
  reutilizaba una lista en memoria tras una excepción en vez de releer el
  checkpoint en disco, causando una pérdida real de 1.475 documentos de
  Superfinanciera. Corregido: recibe `cargar_previos` (callable) y lo llama
  al inicio y tras cada excepción.
- **Superfinanciera, 2º bug de decodificación binaria**: el heurístico
  "¿parece texto?" solo miraba los primeros 8KB; un .mp3 con tag ID3v2 con
  metadata XMP legible ahí lo engañó, generando un documento de 114 millones
  de caracteres que mató el reindex de 7.5h. Corregido con rechazo de firmas
  binarias conocidas + muestreo en 3 puntos + tope de 2M caracteres.
- **GUI web local** (`gui/server.py`, `gui/static/index.html`): stdlib puro,
  sin frameworks, autoabre navegador. 9 tests nuevos.
- **Capa conversacional con Ollama** (`index/responder.py`): respuesta en
  español anclada estrictamente en los fragmentos recuperados, con citas
  entre paréntesis y negativa explícita si no hay información suficiente.
  Degrada a solo-citas si Ollama no responde. 5 tests nuevos.
- **GitHub**: repo público (`github.com/fabiangulla-pixel/aliado-libre`).
- **Render**: evaluado y descartado por costo — uso queda 100% local.
- **DIAN/Superfinanciera/legalize-co**: escalados a producción (ver detalle
  en `docs/fuentes.md` y memoria del proyecto).
- **Corte Suprema sigue en 0 documentos**: backend GraphQL propio de la
  Corte extremadamente inestable (100+ ráfagas de reintento en 4 corridas),
  confirmado como problema de servidor, no de cliente.
- 77 tests (era 58).

### En curso al cierre

- **Fine-tuning LoRA propio en CPU** (`finetune/`): dataset de 50 ejemplos
  hand-authored y anclados en fragmentos reales (`finetune/generar_dataset.py`),
  entrenando un adaptador sobre `Qwen/Qwen2.5-3B-Instruct` (`finetune/entrenar.py`).
  Bug real corregido: `SFTConfig` necesita `use_cpu=True` explícito en
  trl 1.12.0 o falla con `ValueError` de bf16/gpu incluso sin GPU. El
  entrenamiento arrancó bien tras el fix pero **no se confirmó que terminara
  las 3 épocas** antes del cierre de sesión — revisar el log al retomar.
  Falta además `finetune/exportar_gguf.py` (no escrito) para cargar el
  resultado en Ollama.

## 2026-08-29 (tarde) — Escalado real: corpus 44.733 → 120.133+ documentos

Continuación de la sesión de la mañana: se le dio soporte de reanudación a
los 4 ingesters nuevos y se corrieron crawls reales a escala.

### Resuelto

- **DIAN**: 3.000 documentos (tope del lote, hay más disponible — el crawl
  se detuvo por `max_documentos`, no porque se agotaran las fuentes).
- **legalize-co**: **71.900 documentos** — el respaldo completo, leído en
  una sola corrida (lectura local, sin red, ~15 minutos).
- **Superfinanciera**: en progreso al cierre (500+ de 3.000 objetivo), corre
  en background y es reanudable.
- **Corte Suprema**: **0 documentos** — el backend GraphQL resultó mucho más
  inestable de lo esperado: 3 sesiones completas de reintentos (15 intentos
  en total, ~50 minutos) sin lograr una sola respuesta 200 sostenida. Queda
  documentado como pendiente a reintentar en otro momento — el código del
  ingester está verificado y funciona (se confirmó con éxito real durante la
  investigación de la mañana), el problema es enteramente de disponibilidad
  del servidor de la Corte, no del cliente.
- **2 bugs reales encontrados y corregidos al correr a escala** (nunca
  aparecieron en las pruebas con lotes de 5-10 documentos):
  1. El "archivo de texto" descargable de Superfinanciera es en realidad un
     `.docx` — decodificarlo directo como texto (asumiendo que el nombre del
     enlace no mentía) infló 225 documentos a 6.7GB antes de descubrirse.
  2. Segunda vuelta del mismo enlace: algunos son en realidad **audios
     .mp3** de audiencias — mismo problema, más grave (MemoryError al
     serializar el checkpoint). Corregido con una heurística de detección
     de binario (proporción de bytes de control) en vez de confiar en la
     extensión o en que la decodificación "no falle" (latin1 nunca falla).
- Auditoría de datos corrida sobre el corpus completo (`DATA_AUDIT.md`):
  sin duplicados, sin colisiones de ID entre las 8 fuentes, esquema completo
  en el 100% de los documentos. Único hallazgo no bloqueante: 72% de los
  conceptos de Superfinanciera sin fecha (identificador es un título largo
  sin fecha embebida para el subtipo "jurisdiccional").
- 4 scripts de crawl (`scripts/crawl_*.py`) con checkpoint incremental y
  reanudación (`documentos_previos`) añadida a los 4 ingesters nuevos.
- 10 tests nuevos (48 → 58).

### Pendiente

1. Terminar el lote de Superfinanciera (corriendo en background al cierre).
2. Reintentar Corte Suprema cuando el backend esté estable — o considerar
   escalarlo en sesiones cortas y frecuentes en vez de una corrida larga.
3. Reconstruir el índice (embeddings + Chroma) con el corpus ampliado —
   aún no se tocó `index/build_index.py` en esta sesión.
4. DIAN: correr de nuevo con `max_documentos` más alto para agotar las 3
   materias completas (hoy se cortó a mitad de camino por el tope).

## 2026-08-29 — 3 ingesters nuevos + respaldo GitHub + preparación de deploy

Segunda sesión: se atacaron los 4 pendientes dejados el 28-ago.

### Resuelto

- **3 fuentes nuevas con ingester funcionando** (`ingest/fuentes/{dian,superfinanciera,corte_suprema}.py`),
  las 3 verificadas con datos reales, no solo con fixtures:
  - **DIAN**: no era SPA — cada materia (tributario/aduanero/cambiario) tiene páginas
    estáticas con fragmentos HTML (`*_parte_NN.html`) que enlazan documentos en `docs/*.htm`
    con el texto completo embebido. Cero necesidad de Playwright.
  - **Superfinanciera**: el buscador "Conceptos y Jurisprudencia" resultó ser un catálogo
    bibliográfico clásico ABCD/ISIS con 18.569 registros, paginación GET simple
    (`desde`/`count`, 1-indexado — `desde=0` rompe la búsqueda) y archivo de texto
    descargable por registro.
  - **Corte Suprema**: hallazgo mayor — el frontend Vue (documentado antes como "shell
    vacío, API no capturada") en realidad habla con un backend GraphQL propio sin
    autenticación (`consultaprovidenciasbk.cortesuprema.gov.co/api`, dominio no visto en
    la investigación previa). El comodín `query: "*"` enumera el corpus completo de cada
    Sala (Civil ~109k, Laboral ~302k, Penal ~218k, Tutelas ~394k) y `getContentSearch`
    trae el texto ya extraído del PDF/DOCX. Backend inestable (502 intermitente incluso
    con los headers correctos) — el ingester reintenta con backoff.
- **Consejo de Estado reintentado a fondo, sigue bloqueado**: encontrado un tercer buscador
  público no documentado antes (`SAMAI/TitulacionRelatoria/BuscadorProvidenciasTituladas.aspx`,
  "Mi Relatoría"), pero el primer postback devuelve 403 de un Azure Application Gateway —
  confirma que el bloqueo es de infraestructura compartida (WAF), no de una URL específica.
  Cerrado; no vale la pena seguir probando URLs nuevas en el mismo dominio.
- **Respaldo `legalize-co` clonado e integrado** (no solo clonado): `data/respaldo_legalize_co/`
  (clon superficial, 71.903 archivos Markdown con YAML front matter) + un cuarto ingester
  nuevo, `ingest/fuentes/legalize_co_github.py`, que lee el respaldo local sin red. De paso
  resuelve el pendiente de escalar Gestor Normativo: el respaldo trae **61.429 decretos**
  completos sin depender del grafo de "Vigencias" que topó techo en 2.381.
- **Deploy a Render preparado, no ejecutado** (confirmado con el usuario: crear el servicio
  real queda pendiente de su aprobación explícita): `Dockerfile`, `render.yaml` (plan
  `standard` + disco persistente de 5GB para el índice de 2.4GB) y `docs/DEPLOY.md` con los
  pasos y el riesgo de costo. `mcp_server/server.py` ahora sirve `streamable-http` sobre
  `$PORT` si la variable existe, sin romper el modo `stdio` local.
- 17 tests nuevos (31 → 48), todos con fixtures/mocks — ninguno depende de red.
  Lint limpio (ruff).

### Pendiente

- Ingestar a escala real las 3 fuentes nuevas (hoy solo verificadas con lotes pequeños) y
  el respaldo legalize-co completo (61.429 decretos + ~10.000 leyes/actos legislativos),
  con checkpoint como Gestor Normativo — la Corte Suprema en particular implica cientos de
  miles de llamadas a `getContentSearch`, hace falta ir por lotes y con pausas generosas.
- Decidir si de verdad se justifica el costo de Render antes de crear el servicio.

## 2026-08-28 — Proyecto creado, 4 fuentes funcionando, índice validado

Primera sesión de trabajo. Proyecto construido desde cero.

### Resuelto

- **Arquitectura completa**: esquema común (`ingest/schema.py`), chunking por artículo,
  índice híbrido (embeddings locales + BM25 con fusión RRF), servidor MCP.
- **4 fuentes con ingester funcionando**:
  - Gestor Normativo (legislación): 2.381 normas, incluye extracción del grafo de vigencias
    (modifica/deroga/reglamenta) nativo del sitio.
  - Supersociedades (conceptos jurídicos): 4.999 documentos, texto embebido en Elasticsearch.
  - Corte Constitucional (jurisprudencia): 36.853 sentencias (1992-2026) — descubierto que un
    solo request por año trae todas las providencias, no hace falta paginar por documento.
  - SIC (decisiones jurisdiccionales): 500 providencias — resuelto el 403 de descarga de PDF
    encontrando el endpoint Lambda público que firma URLs de S3 bajo demanda.
- **Auditoría de datos** (`scripts/audit_corpus.py`) antes de indexar, encontró y corrigió:
  fechas en español sin normalizar (2.377 docs), 1 documento duplicado (Elasticsearch sin
  `sort` explícito), mojibake residual en 28 documentos.
- **Bugs de escala arreglados**: límite de batch de Chroma en `upsert()` (5.461) y en `.get()`
  ("too many SQL variables") — se sube/carga en lotes de 5.000.
- **API de `mcp` actualizada** de v1 (`FastMCP`) a v2 (`MCPServer`).
- Índice final: 44.733 documentos → 214.435 fragmentos. Validado con consultas reales en
  3 dominios (societario, laboral, salud/tutela).
- 31 tests, lint limpio (ruff), CI local (Makefile/check.bat), hook de pre-commit instalado
  y validado con prueba negativa.

### Archivos clave de esta sesión

- `ingest/schema.py`, `ingest/chunking.py`, `ingest/normalizar.py`
- `ingest/fuentes/{gestor_normativo,supersociedades,corte_constitucional,sic}.py`
- `index/{build_index,buscar}.py`, `mcp_server/server.py`
- `scripts/crawl_*.py`, `scripts/audit_corpus.py`
- `docs/fuentes.md` — mapa completo de fuentes investigadas (30+ sitios evaluados)

### Pendiente

1. Ingesters para Consejo de Estado, Corte Suprema, DIAN, Superfinanciera (mapeados
   como accesibles, código no escrito).
2. Clonar `legalize-co` (GitHub, MIT) como respaldo de SUIN-Juriscol histórico
   (SUIN está bloqueado a nivel de firewall, confirmado con curl/Playwright/PowerShell).
3. Desplegar el servidor MCP como servicio (Render).
4. Gestor Normativo tocó el techo natural del método BFS vía "Vigencias" en 2.381 normas
   (confirmado 3 veces con distintas semillas) — crecer más requiere otro método.
