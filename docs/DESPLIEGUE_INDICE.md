# Desplegar el índice como servicio remoto

Aliado Libre puede funcionar de dos formas:

| | Índice local | **Modelo local + índice en la nube** |
|---|---|---|
| Dónde vive el corpus | Disco del usuario (~11GB) | Servidor |
| Dónde corre el LLM | Equipo del usuario (Ollama) | Equipo del usuario (Ollama) |
| Qué descarga el usuario | Todo el índice | Nada |
| Privacidad | Total | Sale la consulta, no la respuesta |

Este documento cubre la segunda. El LLM sigue siendo local: lo único que se
mueve al servidor es la búsqueda, que es lo único que necesita el corpus
completo.

## Piezas

- `servidor_indice/server.py` — servidor HTTP (stdlib, `ThreadingHTTPServer`).
  Carga el índice **una sola vez** al arrancar.
  - `GET /salud` → `{"estado", "fragmentos", "segundos_carga", "autenticado"}`
  - `POST /buscar` con `{"consulta": str, "n": int}` → `{"consulta", "n", "resultados": [...]}`
- `index/cliente_remoto.py` — `IndiceRemoto`, con la misma firma
  `buscar(consulta, k=8)` que `IndiceBusqueda`.
- `Dockerfile` / `render.yaml` — despliegue.

Los fragmentos de `resultados` son **exactamente** los dicts que devuelve hoy
`IndiceBusqueda.buscar()` (`id`, `puntaje`, `texto` y los metadatos del corpus
aplanados). El servidor no reordena, renombra ni recorta nada, para que el
cambio sea transparente.

## Intercambiar local ↔ remoto

```python
import os
from index.cliente_remoto import IndiceRemoto

url = os.environ.get("ALIADO_INDICE_URL")
if url:
    indice = IndiceRemoto()  # lee ALIADO_INDICE_URL y ALIADO_INDICE_TOKEN
else:
    from index.buscar import IndiceBusqueda  # importa torch/chroma; solo si hace falta

    indice = IndiceBusqueda()

resultados = indice.buscar("prescripción de la acción disciplinaria", k=5)
```

`index/cliente_remoto.py` **no importa nada de `index/buscar.py`**: se puede
usar en un equipo donde ni `torch` ni `chromadb` estén instalados. Ese es
justamente el punto de mover el índice al servidor.

Configuración del cliente, por orden de precedencia:

1. Lo que se pasa a `IndiceRemoto(url, token)`.
2. Las variables de entorno `ALIADO_INDICE_URL` y `ALIADO_INDICE_TOKEN`
   (p. ej. `https://aliado-libre-indice.onrender.com`).
3. El archivo `~/.aliado_libre/credenciales.json`:
   `{"indice_url": "https://...", "indice_token": "..."}`.

El archivo existe para quien recibe el .exe: pedirle a esa persona que defina
una variable de entorno para poder buscar una sentencia no es una opción. Vive
fuera del repositorio, así que el token no puede acabar en git por descuido, y
si está corrupto se ignora en silencio en vez de impedir el arranque.

Errores de red, timeouts y respuestas HTTP se traducen a `ErrorIndiceRemoto`
con un mensaje en español listo para mostrar al usuario.

## Autenticación

El servidor lee `ALIADO_INDICE_TOKEN`:

- **Definida** → exige `Authorization: Bearer <token>` en `/salud` y `/buscar`;
  sin él responde `401`. La comparación es en tiempo constante (`hmac.compare_digest`).
- **No definida** → arranca abierto y lo **advierte por log**. Solo para local.

No hay usuarios ni cuotas: es un secreto compartido. Si se filtra, se rota
cambiando la variable en Render y en los clientes.

Otros límites duros del servidor: cuerpo máximo 64KB (`413`), `n` topado a 50.

## Reranker (opcional, apagado por defecto)

`ALIADO_RERANKER_ACTIVO=1` hace que el servidor reordene los candidatos con un
cross-encoder antes de responder. `GET /salud` informa si está encendido.

Qué gana: recall@5 de 33,5% a 41,0% y @8 de 37,5% a 48,5%, sobre 200 consultas
que no se usaron para elegir nada (`docs/PROJECT_STATE.md`). Es la única mejora de
recuperación confirmada en datos apartados que tiene el proyecto.

Qué cuesta: **~57 s por consulta en CPU** y **~2,3 GB de RAM** además de los 5,12
del índice. En una máquina sin GPU eso convierte una búsqueda de 2 s en una de un
minuto: encenderlo sin GPU solo tiene sentido si se prefiere esperar a fallar. Con
GPU son 1,5 s por consulta (medido en una RTX 5080 el 9-sep-2026).

Por eso viene apagado y por eso no se enciende solo: es una decisión de factura
(RAM y CPU o GPU del servidor), no un detalle de configuración. **En el modo
escritorio sí se enciende solo cuando hay GPU**, y el servidor se queda fuera de
esa regla de forma explícita: `main()` fija `ALIADO_RERANKER_ACTIVO=0` si el
operador no dijo nada, así que desplegar en un host con aceleradora no empieza a
gastar por su cuenta. Un `ALIADO_RERANKER_ACTIVO=1` sigue mandando.

## Cómo llega el índice al servidor

**El índice no está en git y no cabe en la imagen Docker.**

| Artefacto | Tamaño |
|---|---|
| `index/chroma_db/chroma.sqlite3` | ~14,9 GB |
| `index/chroma_db/9601ae5b-…/` (vectores e5-large) | ~3,0 GB |
| `index/chroma_db/41519883-…/` (vectores del índice viejo) | ~1,2 GB |
| `index/fts_index.db` (FTS5) | ~1,55 GB |
| **Total** | **~20,7 GB** |

Va en un **disco persistente**, montado en `/datos` (30GB en `render.yaml`).

⚠️ **Estas cifras cambiaron con e5-large** (antes ~10,9 GB en total). Los
vectores son de 1024 dimensiones en vez de 384, y `chroma.sqlite3` guarda ahora
dos colecciones. El disco de 15 GB que estaba configurado **no alcanzaba**: el
despliegue habría fallado al copiar. Si hace falta apretar, la colección vieja
(`41519883-…`, 1,2 GB) se puede dejar fuera; el código ya no la consulta.

No se monta sobre `/app/index` porque taparía los módulos de Python que viven
ahí (`buscar.py`, `cliente_remoto.py`). El `Dockerfile` deja symlinks:

```
/app/index/chroma_db    -> /datos/chroma_db
/app/index/fts_index.db -> /datos/fts_index.db
```

Así `index/buscar.py` sigue usando sus rutas de siempre y no hubo que tocarlo.

### Subida inicial (una sola vez)

Render no tiene forma de escribir en un disco desde fuera, así que la subida
se hace desde dentro del contenedor:

1. Despliega el servicio (arrancará con `/salud` reportando `fragmentos: 0`
   o fallando al abrir Chroma: es lo esperado, el disco está vacío).
2. Abre una shell en el servicio (pestaña *Shell* en Render).
3. Trae el índice desde donde lo tengas publicado (un bucket S3/R2, un
   release privado, un servidor propio):
   ```sh
   cd /datos
   curl -L "$URL_FIRMADA_DEL_TAR" | tar xz    # ~11GB: cuenta con 15-40 min
   ls -la /datos   # debe verse chroma_db/ y fts_index.db
   ```
4. Reinicia el servicio para que `cargar_indice()` corra con el disco lleno.
5. Verifica: `curl -H "Authorization: Bearer $TOKEN" https://.../salud` debe
   devolver el número real de fragmentos (~718.388 hoy).

Empaquetar el tar en local:

```sh
tar czf indice.tar.gz -C index chroma_db fts_index.db
```

**Alternativa: reconstruirlo en el servidor.** Es posible (`index/build_index.py`
y `index/build_fts.py` contra el corpus de `data/`) pero tarda horas de CPU
facturada y hay que subir el corpus igual. Subir el tar es más barato.

### Reindexados posteriores

Construye en local, sube el tar nuevo a `/datos/nuevo/`, y solo cuando termine
mueve y reinicia. Si sobrescribes en caliente, Chroma sirve un índice a medias
sin avisar.

## RAM — medido con e5-large el 7-sep-2026

**Pico: 5,12 GB de RSS.** Medido en el proceso real, cargando el índice y
sirviendo ocho consultas de verdad:

| Momento | RSS |
|---|---|
| Tras importar `index.buscar` | 0,45 GB |
| Índice construido (68 s) | 3,97 GB |
| Tras 8 consultas | **5,12 GB** |

Se compone del modelo `multilingual-e5-large` (~2,2 GB de pesos) más PyTorch, y
del índice HNSW de Chroma, que se mapea a memoria y crece al servir consultas
(los 1,15 GB que aparecen entre la carga y la octava consulta son páginas del
HNSW que solo se tocan al buscar; por eso medir solo el arranque engaña).

**La cifra anterior de 2,3 GB era del embedding viejo y estaba mal por un factor
de más de dos.** Sostuvo durante tres días la elección de plan de hosting.

Chroma y FTS5 siguen siendo disco-residentes, así que la RAM no crece con el
tamaño del corpus — pero sí creció con el tamaño del modelo, que es lo que
cambió.

**Consecuencia directa: Render Pro (4 GB, 85 USD/mes) NO alcanza.** Hay que ir a
8 GB. Y si algún día se adopta el reranker, súmale otros ~2,3 GB del
cross-encoder: el servidor pasaría a necesitar 8 GB largos o 16.

## Costo mensual estimado

Precios consultados el 4 de septiembre de 2026. Cambian; verifícalos antes de
contratar.

### Render

| Concepto | Precio | Cantidad | Mes |
|---|---|---|---|
| Web service de **8 GB** (Pro Plus) | ~175 USD/mes | 1 | ~175 |
| Disco persistente | 0,25 USD/GB/mes | 30 GB | 7,50 |
| | | **Total** | **~180 USD/mes** |

Los tiers de Render son Starter 7 USD (0,5 GB), Standard 25 USD (2 GB) y Pro
85 USD (4 GB). **Con 5,12 GB medidos, Pro tampoco alcanza**: hay que subir al
siguiente escalón. Verifica el precio exacto antes de contratar; lo que importa
aquí es el orden de magnitud, que pasó de "caro" a "inviable para un proyecto
gratuito".

Es el mismo salto de escalón el que domina toda esta arquitectura: **bajar el
pico por debajo de 4 GB vale más que cualquier optimización de velocidad.** Dos
vías concretas, ninguna probada: cuantizar el modelo de embeddings, o servir el
HNSW desde disco en vez de mapearlo.

### Fly.io

| Concepto | Precio | Cantidad | Mes |
|---|---|---|---|
| Máquina `shared-cpu-2x` con 4GB RAM | ~12–22 USD/mes según región | 1 | ~12–22 |
| Volumen | 0,15 USD/GB/mes | 15 GB | 2,25 |
| Egreso | 0,02 USD/GB (NA/EU) | despreciable (JSON) | ~0 |
| | | **Total** | **~15–25 USD/mes** |

Fly documenta la RAM adicional a "about $5 per 30 days per GB" sobre una
máquina base, y su tabla por región da valores de un dígito a veintitantos
dólares para configuraciones de 4GB según región y tamaño de CPU. **El rango
es ancho a propósito: no logré fijar una cifra única y no la voy a inventar.**
Antes de decidir, mira la tabla de tu región concreta.

### Conclusión

Fly.io sale varias veces más barato para este caso, porque cobra la RAM de forma
continua en vez de por escalones; con 8 GB su tabla por región manda, y hay que
mirarla antes de decidir (las cifras de la tabla de arriba son para 4 GB y se
quedaron cortas).

**El camino que hoy recomienda este documento es el tercero: un VPS con 8-16 GB**
(Hetzner CX42 y similares rondan 15-30 EUR/mes con disco suficiente), corriendo
`python servidor_indice/server.py` detrás de un nginx con TLS. Requiere
administrarlo a mano; el servidor es stdlib puro y no pide nada más.

### Fuentes

- [Render — Pricing](https://render.com/pricing)
- [Render Pricing Breakdown (2026), Deploy Handbook](https://deployhandbook.com/pricing/render)
- [Render Pricing 2026, Costbench](https://costbench.com/software/developer-tools/render/)
- [Fly.io — Pricing](https://fly.io/docs/about/pricing/)

## Correr en local

```sh
export ALIADO_INDICE_TOKEN=lo-que-sea
./.venv/Scripts/python.exe servidor_indice/server.py     # escucha en 8800
```

Sin `PORT` usa el 8800. En Render usa `$PORT`.

Desde otro proceso:

```sh
curl -s -X POST http://localhost:8800/buscar \
  -H "Authorization: Bearer $ALIADO_INDICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"consulta":"acción de tutela","n":3}'
```

## Pendientes conocidos

- La GUI (`gui/server.py`) todavía no ofrece elegir índice remoto; hoy solo se
  puede cablear por código. Ese archivo está fuera del alcance de este cambio.
- No hay reintento automático en el cliente: un timeout se reporta y ya. Si el
  plan del servidor suspende por inactividad, el primer usuario después de una
  pausa verá el mensaje de timeout.
- El token es único para todos los clientes. No hay revocación por usuario.

---

## Cifras remedidas el 11-sep-2026 (indice de 928.086 fragmentos)

**Las cifras de arriba quedaron obsoletas**: se calcularon sobre el indice de
718.388 fragmentos. El reindexado del 10/11-sep lo dejo en **928.086** (+29%).
Medido en el MSI, con el reranker apagado (que es como corre el servidor):

| | antes (718.388) | ahora (928.086) |
|---|---|---|
| RAM del proceso de busqueda | 5,12 GB | **6,43 GB** |
| Disco (Chroma) | — | **14 GB** |
| Disco (FTS5) | — | **2,1 GB** |
| Disco total | ~21 GB | **16,1 GB** |

La RAM sube un 26% y el disco BAJA: el indice viejo ocupaba 19,8 GB en Chroma.
La conclusion de no contratar sin releer esto **sigue en pie**, y con mas razon
en RAM: cualquier plan dimensionado para 5,12 GB se queda corto.

**Pendiente antes de decidir hosting:** el indice actual se construyo con un
troceo que borraba los parrafos de menos de 150 caracteres (ver CHANGELOG del
11-sep). Corregido en codigo, pero **habra que reindexar**, y eso movera otra vez
estas cifras al alza.
