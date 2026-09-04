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

Variables de entorno del cliente:

- `ALIADO_INDICE_URL` — p. ej. `https://aliado-libre-indice.onrender.com`
- `ALIADO_INDICE_TOKEN` — el mismo secreto que el servidor

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

## Cómo llega el índice al servidor

**El índice no está en git y no cabe en la imagen Docker.**

| Artefacto | Tamaño |
|---|---|
| `index/chroma_db/` (vectorial) | ~9,2 GB |
| `index/fts_index.db` (FTS5) | ~1,66 GB |
| **Total** | **~10,9 GB** |

Va en un **disco persistente**, montado en `/datos` (15GB en `render.yaml`).

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

## RAM

Medido: **~2,3 GB** de RSS en caliente. Se compone de:

- modelo de embeddings `paraphrase-multilingual-MiniLM-L12-v2` + PyTorch
- índice HNSW de Chroma, que sí se mapea a memoria

Chroma y FTS5 son disco-residentes, así que **la RAM no crece con el tamaño
del corpus** (la versión anterior con `rank_bm25` en memoria pedía ~10GB solo
para arrancar; por eso este proyecto puede hostearse por decenas y no por
cientos de dólares al mes).

Con 2,3 GB de pico, un plan de 2GB **no alcanza**: hay que ir a uno de 4GB.

## Costo mensual estimado

Precios consultados el 4 de septiembre de 2026. Cambian; verifícalos antes de
contratar.

### Render

| Concepto | Precio | Cantidad | Mes |
|---|---|---|---|
| Web service **Pro** (4GB RAM) | 85 USD/mes | 1 | 85,00 |
| Disco persistente | 0,25 USD/GB/mes | 15 GB | 3,75 |
| | | **Total** | **~88,75 USD/mes** |

Los tiers de Render son Starter 7 USD (0,5 GB), Standard 25 USD (2 GB) y Pro
85 USD (4 GB). Standard queda descartado por los 2,3 GB medidos. **El salto
de 25 a 85 USD por pasar de 2 a 4 GB es lo que domina el costo de esta
arquitectura**; si el pico de RAM bajara de 2 GB (por ejemplo cuantizando el
modelo de embeddings o dejando el HNSW en disco), la factura caería a ~29 USD.

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

Fly.io sale entre **3 y 5 veces más barato** para este caso, porque cobra la
RAM de forma continua en vez de por escalones. El precio de Render es por la
comodidad: `render.yaml` en el repo, disco y despliegue sin tocar CLI.

Un tercer camino, más barato aún, es un VPS cualquiera con 4GB y 20GB de
disco (Hetzner CX22 y similares rondan los 5 USD/mes), corriendo
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
./venv/Scripts/python.exe servidor_indice/server.py     # escucha en 8800
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
