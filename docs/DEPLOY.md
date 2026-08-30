# Desplegar el servidor MCP en Render

Todo lo de este documento queda preparado pero **no ejecutado** — crear el
servicio en Render es una acción sobre tu cuenta, la confirmas tú.

## Qué ya está listo

- `Dockerfile`: imagen con las dependencias de `requirements.txt` (incluye
  `sentence-transformers`, `chromadb`, `mcp`).
- `render.yaml`: Blueprint de Render — un servicio web tipo `docker`, plan
  `standard` (el índice cargado en memoria por `sentence-transformers` +
  Chroma necesita más de los ~512MB del plan free) y un disco persistente
  de 5GB montado en `index/chroma_db/`.
- `mcp_server/server.py`: ahora arranca en modo `streamable-http` sobre
  `0.0.0.0:$PORT` si la variable de entorno `PORT` existe (la pone Render
  automáticamente), y en modo `stdio` normal si no (uso local sin cambios).

## Por qué hace falta un disco persistente

El índice actual (`index/chroma_db/`) pesa **~2.4GB** — 214.435 fragmentos
con sus embeddings. No está en git (`.gitignore`) ni se puede meter dentro
de la imagen Docker de forma razonable (el build de Render clona el repo,
no tiene acceso a tu disco local). Un disco persistente de Render es la
única forma limpia de que el contenedor arranque con el índice ya
construido en vez de reconstruirlo desde cero en cada deploy.

## Pasos para desplegar (cuando decidas hacerlo)

1. En el dashboard de Render: **New > Blueprint**, apuntar al repo de
   `aliado-libre` en GitHub (necesita estar pusheado — hoy es solo local).
2. Render detecta `render.yaml` y propone el servicio + el disco. Confirmar.
3. **Primer deploy**: el disco nace vacío. Antes de que el servidor pueda
   responder consultas reales, hay que subir el índice. Opciones:
   - Más simple: abrir un *Shell* en el servicio ya desplegado (Render lo
     ofrece en el dashboard) y correr `python index/build_index.py` ahí,
     apuntando a los mismos `data/raw/*.json` (hay que subirlos también,
     vía `git lfs`, un bucket externo, o `scp` al disco montado).
   - Alternativa sin mover 2.4GB de datos crudos: reconstruir el índice
     completo desde las fuentes en el propio servidor de Render (más lento,
     pero no requiere transferir nada manualmente) — no recomendado como
     primer intento porque toma varias horas de crawling.
4. Verificar con `buscar_normativa("prueba")` desde un cliente MCP apuntando
   a `https://<tu-servicio>.onrender.com/mcp`.

## Riesgo a tener presente

El plan `standard` de Render no es gratis (a diferencia de todo lo demás en
Aliado Libre, que corre 100% local y gratis). Evaluar si el uso real
justifica el costo mensual antes de confirmar el deploy, o si conviene
seguir usando el servidor solo local (`python mcp_server/server.py`, modo
`stdio`) como hasta ahora.
