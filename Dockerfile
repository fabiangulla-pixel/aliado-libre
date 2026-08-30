FROM python:3.12-slim

WORKDIR /app

# git: lo necesita el respaldo de legalize-co si se reconstruye dentro del contenedor;
# build-essential: algunas dependencias de sentence-transformers compilan extensiones nativas.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV HF_HUB_OFFLINE=0
# El índice (index/chroma_db/) vive en un disco persistente montado en Render,
# no en la imagen — ver docs/DEPLOY.md. Si no existe al arrancar, buscar_normativo()
# fallará con un error claro en vez de silenciosamente devolver vacío.

EXPOSE 8000

CMD ["python", "mcp_server/server.py"]
