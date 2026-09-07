"""Fuente del notebook de Colab que recalcula los embeddings del índice en GPU.

Este archivo es la versión legible y versionable del notebook; el .ipynb se
genera con `./venv/Scripts/python.exe finetune/hacer_notebook_reindex.py`. Se
mantiene así para que el código pase por ruff y por revisión como cualquier
otro, en vez de vivir solo dentro de un JSON de notebook.

QUÉ RESUELVE
------------
El índice actual se construyó con `paraphrase-multilingual-MiniLM-L12-v2`, que
tiene dos problemas medidos:

1. `max_seq_length = 128` tokens (~450 caracteres). El 76% de los fragmentos
   del corpus supera los 500 caracteres y el 40% pasa de 1.000, así que en la
   mayoría el vector representa solo el principio del texto — que en una norma
   suele ser el encabezado, no la parte que responde.
2. Es un modelo de *paráfrasis* (simétrico, frase corta contra frase corta).
   La tarea real es asimétrica: pregunta coloquial corta contra pasaje legal
   largo. Una consulta y el artículo que la responde no son paráfrasis.

Resultado medido sobre 1.583 consultas reales: la mitad semántica del buscador
aporta casi nada, y el recall@5 depende de que el usuario use las palabras de
la norma — 68% para un abogado, 0% para el perfil "adulto mayor".

POR QUÉ EN COLAB Y NO AQUÍ
--------------------------
Reindexar 718.388 fragmentos con MiniLM tomó ~7,5 h de CPU en el equipo local,
y el modelo nuevo es varias veces más grande. En una T4 son ~1-3 h.

El corpus NO se sube desde el PC: se baja directo del dataset ya publicado en
Hugging Face, se procesa en Colab y el resultado se vuelve a subir allí. El
equipo local no participa en el trasiego.
"""

# --- CELDA 1: instalar ------------------------------------------------------
CELDA_INSTALAR = r"""
!pip install -q sentence-transformers huggingface_hub
import torch
assert torch.cuda.is_available(), (
    "No hay GPU. Entorno de ejecucion -> Cambiar tipo de entorno -> T4 GPU."
)
print("GPU:", torch.cuda.get_device_name(0))
"""

# --- CELDA 2: credenciales --------------------------------------------------
CELDA_TOKEN = r"""
import getpass, os
# Token de Hugging Face CON permiso de escritura (se pega a mano; no queda en el
# notebook ni en el repositorio).
os.environ["HF_TOKEN"] = getpass.getpass("HF_TOKEN (write): ").strip()

REPO_DATOS = "Gullax/indice-legal-colombia"   # de donde se baja el corpus
REPO_SALIDA = "Gullax/indice-legal-colombia"  # donde se suben los vectores nuevos
MODELO = "intfloat/multilingual-e5-large"     # 1024 dim, 512 tokens, asimetrico
LOTE = 128
"""

# --- CELDA 3: bajar el corpus y extraer los textos --------------------------
CELDA_DESCARGAR = r"""
from huggingface_hub import hf_hub_download
import sqlite3, json, os

print("Bajando chroma.sqlite3 (~7,9 GB)...")
ruta = hf_hub_download(
    repo_id=REPO_DATOS, filename="chroma.sqlite3",
    repo_type="dataset", token=os.environ["HF_TOKEN"],
)
print("en", ruta)

con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)

# El texto y la metadata viven en embedding_metadata (una fila por clave);
# se reconstruye un registro por fragmento. Se lee de una vez y en orden de id
# para que el orden sea reproducible entre corridas.
print("Extrayendo textos...")
campos = {}
for fila_id, clave, valor in con.execute(
    "SELECT id, key, string_value FROM embedding_metadata"
):
    campos.setdefault(fila_id, {})[clave] = valor

ids_por_fila = dict(con.execute("SELECT id, embedding_id FROM embeddings"))

registros = []
for fila_id, datos in campos.items():
    texto = (datos.get("chroma:document") or "").strip()
    frag_id = ids_por_fila.get(fila_id)
    if not texto or not frag_id:
        continue
    registros.append({
        "id": frag_id,
        "texto": texto,
        "documento_id": datos.get("documento_id"),
        "identificador_documento": datos.get("identificador_documento"),
        "titulo_documento": datos.get("titulo_documento"),
        "fuente": datos.get("fuente"),
        "url_original": datos.get("url_original"),
        "orden": datos.get("orden"),
    })

registros.sort(key=lambda r: r["id"])
print(f"{len(registros)} fragmentos listos")
with open("fragmentos.jsonl", "w", encoding="utf-8") as f:
    for r in registros:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
"""

# --- CELDA 4: embeddings por lotes, con checkpoint --------------------------
CELDA_EMBEDDINGS = r"""
import numpy as np, json, os, time
from sentence_transformers import SentenceTransformer

modelo = SentenceTransformer(MODELO, device="cuda")
modelo.max_seq_length = 512   # el punto de todo el ejercicio: dejar de truncar
print("max_seq_length:", modelo.max_seq_length,
      "| dim:", modelo.get_sentence_embedding_dimension())

registros = [json.loads(l) for l in open("fragmentos.jsonl", encoding="utf-8")]
# e5 exige prefijos y distingue documento de consulta. Sin esto el modelo rinde
# bastante peor: es literalmente como fue entrenado.
textos = ["passage: " + r["texto"] for r in registros]

# Por trozos, guardando cada uno: una sesion de Colab se puede cortar, y
# perder tres horas de GPU por no guardar seria absurdo.
TROZO = 50_000
os.makedirs("vectores", exist_ok=True)
inicio = time.time()
for i in range(0, len(textos), TROZO):
    salida = f"vectores/parte_{i // TROZO:03d}.npy"
    if os.path.exists(salida):
        print("ya estaba:", salida)
        continue
    vecs = modelo.encode(
        textos[i:i + TROZO], batch_size=LOTE, convert_to_numpy=True,
        normalize_embeddings=True, show_progress_bar=True,
    ).astype("float16")   # la mitad de tamano; la perdida es despreciable
    np.save(salida, vecs)
    hechos = min(i + TROZO, len(textos))
    transcurrido = (time.time() - inicio) / 60
    print(f"{hechos}/{len(textos)} | {transcurrido:.0f} min | "
          f"faltan ~{transcurrido / hechos * (len(textos) - hechos):.0f} min")

partes = sorted(os.listdir("vectores"))
matriz = np.concatenate([np.load(f"vectores/{p}") for p in partes])
np.save("embeddings.f16.npy", matriz)
print("matriz final:", matriz.shape, matriz.dtype)
"""

# --- CELDA 5: subir el resultado -------------------------------------------
CELDA_SUBIR = r"""
from huggingface_hub import HfApi
import json, os

api = HfApi(token=os.environ["HF_TOKEN"])
sufijo = MODELO.split("/")[-1]

api.upload_file(
    path_or_fileobj="embeddings.f16.npy",
    path_in_repo=f"embeddings_{sufijo}.f16.npy",
    repo_id=REPO_SALIDA, repo_type="dataset",
    commit_message=f"Embeddings recalculados con {MODELO} (512 tokens, sin truncar)",
)

# Los ids en el MISMO orden que las filas de la matriz: sin esto los vectores
# no se pueden volver a casar con sus fragmentos.
registros = [json.loads(l) for l in open("fragmentos.jsonl", encoding="utf-8")]
with open("ids.json", "w", encoding="utf-8") as f:
    json.dump([r["id"] for r in registros], f)

api.upload_file(
    path_or_fileobj="ids.json", path_in_repo=f"ids_{sufijo}.json",
    repo_id=REPO_SALIDA, repo_type="dataset",
    commit_message="Orden de los ids que corresponde a la matriz de embeddings",
)
print("Listo. Descargar con index/build_index_desde_vectores.py")
"""

CELDAS = [
    (
        "markdown",
        "# Reindexar los embeddings de Aliado Libre en GPU\n\n"
        "El índice actual trunca el 76% de los fragmentos a 128 tokens y usa un "
        "modelo de paráfrasis donde hace falta uno de recuperación. Esto lo "
        "recalcula con `multilingual-e5-large` a 512 tokens.\n\n"
        "**Entorno de ejecución → Cambiar tipo de entorno → T4 GPU** antes de empezar.",
    ),
    ("code", CELDA_INSTALAR),
    ("markdown", "## Credenciales y parámetros"),
    ("code", CELDA_TOKEN),
    (
        "markdown",
        "## Bajar el corpus ya publicado y extraer los textos\n\n"
        "El corpus se baja de Hugging Face, no se sube desde el PC.",
    ),
    ("code", CELDA_DESCARGAR),
    (
        "markdown",
        "## Calcular los embeddings (lo que tarda)\n\n"
        "Guarda cada 50.000 fragmentos: si Colab corta la sesión, se reanuda.",
    ),
    ("code", CELDA_EMBEDDINGS),
    ("markdown", "## Subir los vectores"),
    ("code", CELDA_SUBIR),
]
