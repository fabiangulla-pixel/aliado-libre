# Empaquetado: el .exe de Aliado Libre

Cómo se produce `AliadoLibre.exe`, qué lleva dentro, qué deliberadamente no
lleva, y cómo comprobar que eso último es cierto.

## Cómo compilar

```bat
build.bat
```

o, equivalente:

```
./.venv/Scripts/python.exe scripts/build_exe.py
```

Siempre con el intérprete del venv (Python 3.12). El Python del sistema (3.14)
no sirve para este proyecto.

El script borra `build/` y `dist/` y pasa `--clean` antes de compilar. **Esto no
es opcional.** PyInstaller cachea el análisis de dependencias; si se cambian los
`excludes` del `.spec` y no se limpia, el binario sigue arrastrando módulos que
uno cree haber quitado, compila sin errores y pesa de más.

## Qué va dentro y qué no

| Va dentro | Se queda fuera |
|---|---|
| Servidor web local (`gui/server.py`, solo stdlib) | El corpus (`data/`) |
| La página `gui/static/index.html` | El índice Chroma (`index/chroma_db/`) |
| `llama-cpp-python` + sus DLL (`ggml`, `llama`) | El índice FTS5 (`index/fts_index.db`) |
| `index/cliente_remoto.py` (consulta el índice por HTTP) | `sentence-transformers`, `torch`, `transformers` |
| `requests`, `numpy` (dependencia real de llama-cpp) | `peft`, `trl`, `datasets`, `accelerate` |
| | `index/buscar.py` (el índice *local*) |

La arquitectura es: **el modelo viaja con el usuario, el índice vive en un
servidor.** El .exe corre el Qwen2.5-1.5B afinado en local con llama.cpp y
consulta los fragmentos por HTTP. Por eso nada de la pila de embeddings ni de
la base vectorial tiene por qué estar en el binario.

Los `excludes` del `.spec` son explícitos y agresivos a propósito. PyInstaller
sigue cualquier import, aunque sea perezoso o esté dentro de un `try`, y con eso
basta para que la pila científica entera acabe dentro: es el origen conocido de
los .exe de 600-900 MB en otros proyectos de la suite. Excluirla baja el tamaño
alrededor del 85%.

## Tamaño real medido

```
dist/AliadoLibre.exe   28.6 MB
```

De esos, la mayor parte son las DLL nativas de llama.cpp (~31 MB sin comprimir)
y numpy. Sin llama-cpp-python el binario bajaría a unos pocos MB, pero entonces
no habría modelo local.

## El modelo GGUF NO va dentro del .exe

A propósito. Un ejecutable *onefile* de PyInstaller se descomprime entero en una
carpeta temporal en **cada** arranque; meterle ~1 GB de pesos haría que abrir el
programa tardara decenas de segundos y escribiera un giga en disco cada vez.

El modelo se distribuye **al lado** del .exe:

```
AliadoLibre/
├── AliadoLibre.exe
└── modelo/
    └── modelo_lora_15b.q4_k_m.gguf
```

## Qué falta para que sea distribuible de verdad

Actualizado 4-sep-2026. Los dos bloqueos grandes ya están resueltos:

- ~~El GGUF Q4_K_M no existe~~ → **existe**: `finetune/salida/modelo_lora_15b.q4_k_m.gguf`,
  **940 MB** (32% del f16 de 2.950 MB). Generado con `finetune/cuantizar_q4.py`.
  El paquete completo (.exe + modelo) queda en unos **970 MB**.
- ~~`index/responder.py` habla con Ollama~~ → **migrado** a `llama_cpp.Llama`
  en proceso, con carga perezosa una sola vez. El .exe ya no depende de que el
  usuario instale Ollama.

Queda pendiente:

1. **Fijar la URL por defecto del servidor de índice.** Sigue sin haber valor
   por defecto porque el servidor aún no está desplegado — ver
   `docs/DESPLIEGUE_INDICE.md`. Lo que ya no hace falta es una variable de
   entorno: desde el 6-sep-2026 el cliente lee también
   `~/.aliado_libre/credenciales.json`:

   ```json
   {"indice_url": "https://...", "indice_token": "..."}
   ```

   Precedencia: lo que se pasa a mano > el entorno > ese archivo. Así el .exe
   se puede configurar sin tocar variables del sistema, y el token queda fuera
   del repositorio. Cuando haya servidor, basta con hornear la URL como valor
   por defecto y el archivo pasa a servir para apuntar a otro.
2. ~~**Reevaluar la calidad del Q4.**~~ → **hecho (6-sep-2026): el Q4_K_M se
   queda.** Medido contra el q8_0 con ambos generados en CPU, sobre las mismas
   150 preguntas: la diferencia cabe en el ruido del muestreo (McNemar p = 0,40).
   La comparación anterior, que sí daba una caída significativa, comparaba a la
   vez cuantización y hardware —una en GPU y otra en CPU— y quedó retirada.
   Detalle en `docs/PROJECT_STATE.md`. Con esto el paquete se queda en ~970 MB en
   vez de ~3 GB.
3. Firma de código e icono propio (hoy usa el icono por defecto de PyInstaller).

## Los parámetros de inferencia no son libres

`index/responder.py` fija `n_ctx=8192`, `max_tokens=400`, `temperature=0.2` y
`stop=["Pregunta:", "###"]`. Son exactamente los que se usaron para **medir** la
calidad del modelo (`finetune/generar_respuestas_local.py` y el notebook de
evaluación en GPU). Cambiarlos en producción no "afina" nada: invalida el número
medido, porque el modelo pasa a evaluarse en condiciones distintas de las que se
midieron. Lo mismo vale para `PROMPT_SISTEMA`, contra el que se hizo el
fine-tuning.

## Cómo verificar que la pila ML quedó fuera

**Buscar cadenas dentro del .exe da falso negativo.** El código Python viaja
comprimido dentro de un archivo `PYZ` incrustado en el binario, así que `torch`
no aparece como texto plano aunque el módulo esté dentro. Hay que abrir el PYZ:

```python
from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader

archivo = CArchiveReader("dist/AliadoLibre.exe")
open("PYZ.pyz", "wb").write(archivo.extract("PYZ.pyz"))
print(sorted(ZlibArchiveReader("PYZ.pyz").toc))
```

Esto está automatizado en `tests/test_empaquetado.py`, que falla si `torch`,
`chromadb`, `sentence_transformers`, `peft` u otros aparecen en el PYZ. Las
pruebas se saltan solas si no hay `.exe` compilado.

## Regla dura: nunca `sys.executable` en código congelado

Dentro de un .exe de PyInstaller, `sys.executable` **es el propio .exe**, no un
intérprete de Python. Relanzarlo con `subprocess` para instalar dependencias o
correr un subproceso hace que el programa se ejecute a sí mismo en bucle: bomba
fork. `tests/test_empaquetado.py` verifica que el código empaquetado no lo haga.
