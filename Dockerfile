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

# El modelo de embeddings se descarga en build y queda dentro de la imagen: así
# el arranque no depende de la red de Hugging Face ni paga esa latencia. En
# runtime index/buscar.py fuerza HF_HUB_OFFLINE=1.
ENV HF_HOME=/opt/hf
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"

ENV PYTHONUNBUFFERED=1

# El índice (index/chroma_db/ ~9.2GB y index/fts_index.db ~1.66GB) NO está en
# git ni en la imagen: vive en un disco persistente montado en /datos.
#
# No se monta el disco directamente sobre /app/index porque eso taparía los
# módulos de Python que viven ahí (buscar.py, cliente_remoto.py...). En su
# lugar se dejan symlinks: index/buscar.py sigue leyendo sus rutas de siempre
# y no hay que tocarlo. Ver docs/DESPLIEGUE_INDICE.md.
RUN rm -rf /app/index/chroma_db /app/index/fts_index.db \
    && ln -s /datos/chroma_db /app/index/chroma_db \
    && ln -s /datos/fts_index.db /app/index/fts_index.db

EXPOSE 8800

# Servidor del índice (arquitectura "modelo local + índice en la nube").
# Para desplegar en cambio el servidor MCP, sobrescribe el comando:
#   dockerCommand: python mcp_server/server.py
CMD ["python", "servidor_indice/server.py"]
