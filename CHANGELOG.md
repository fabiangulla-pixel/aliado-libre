# Changelog

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

- **Q4_K_M del modelo ganador**: 940 MB (32% del f16). Pero **cuesta precisión** frente al
  q8_0: contraste pareado sobre las mismas preguntas, con significancia estadística
  (McNemar) — la caída es real, no ruido. El daño está en las positivas
  (elegir el fragmento correcto); las abstenciones no empeoran. Recomendación:
  distribuir el q8_0.
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
