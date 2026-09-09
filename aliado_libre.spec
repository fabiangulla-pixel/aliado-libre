# -*- mode: python ; coding: utf-8 -*-
"""Empaquetado de Aliado Libre con PyInstaller.

Arquitectura del ejecutable distribuible:

  * SÍ va dentro: el servidor web local (stdlib), la página gui/static/ y el
    motor de inferencia local (llama-cpp-python + sus DLL de ggml/llama),
    que corre el modelo Qwen2.5-1.5B afinado en GGUF Q4_K_M.
  * NO va dentro: el corpus, el índice Chroma, el índice FTS5,
    sentence-transformers, torch, transformers, peft/trl/datasets/accelerate.
    El índice se consulta por HTTP contra el servidor remoto.

La razón de los `excludes` agresivos: cuando PyInstaller ve un import
(aunque sea perezoso o condicional) arrastra la pila científica entera y el
.exe se va a 600-900 MB. Excluirla explícitamente lo baja ~85%. Si alguna
exclusión rompe el arranque, el fallo es un ImportError claro al ejecutar,
no un binario silenciosamente inflado.

El modelo GGUF NO se empaqueta dentro del .exe: son ~1.1 GB que harían el
arranque lentísimo (onefile descomprime todo en cada ejecución). Se
distribuye al lado, en modelo/ — ver docs/EMPAQUETADO.md.
"""

from pathlib import Path

RAIZ = Path(SPECPATH)

# --- datos ---------------------------------------------------------------
datas = [
    (str(RAIZ / "gui" / "static"), "gui/static"),
]

# --- pila que NO debe entrar --------------------------------------------
# ML / embeddings / entrenamiento
EXCLUDES_ML = [
    "torch", "torchvision", "torchaudio",
    "transformers", "tokenizers", "sentence_transformers",
    "peft", "trl", "datasets", "accelerate", "evaluate", "safetensors",
    "huggingface_hub", "bitsandbytes", "onnx", "onnxruntime", "optimum",
    "timm", "sentencepiece", "gguf",
]
# base de datos vectorial y sus dependencias pesadas
EXCLUDES_VECTORIAL = [
    "chromadb", "chroma_hnswlib", "hnswlib", "posthog", "pulsar",
    "opentelemetry", "grpc", "grpcio", "google", "kubernetes",
    "rank_bm25", "faiss",
]
# pila científica general
EXCLUDES_CIENTIFICO = [
    "scipy", "sklearn", "pandas", "matplotlib", "numba", "llvmlite",
    "sympy", "networkx", "PIL", "cv2", "h5py", "pyarrow", "numexpr",
]
# ingesta / crawling / herramientas de desarrollo: no se usan en el .exe
EXCLUDES_HERRAMIENTAS = [
    "bs4", "lxml", "pypdf", "docx", "mcp", "tqdm",
    "pytest", "ruff", "IPython", "jupyter", "notebook", "setuptools", "pip",
    "tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6", "wx",
]
# index.buscar es el índice LOCAL: importa sentence_transformers y chromadb,
# ambos excluidos. En el .exe nunca se usa (se usa index.cliente_remoto), así
# que se excluye para que no viaje un módulo que solo puede fallar al importarse.
EXCLUDES_PROYECTO = ["index.buscar"]

excludes = (
    EXCLUDES_ML + EXCLUDES_VECTORIAL + EXCLUDES_CIENTIFICO
    + EXCLUDES_HERRAMIENTAS + EXCLUDES_PROYECTO
)

# --- módulos del proyecto que se importan tarde --------------------------
# index.buscar queda FUERA a propósito: importa sentence_transformers y
# chromadb, que son justo lo que no debe viajar en el .exe.
hiddenimports = [
    "index.responder",
    # confianza_tls y truststore hacen que el .exe funcione en equipos con un
    # antivirus que inspecciona TLS. Sin ellos dentro, esos equipos ven
    # CERTIFICATE_VERIFY_FAILED al primer uso. Ver confianza_tls.py.
    "confianza_tls",
    "truststore",
]
try:
    import index.cliente_remoto  # noqa: F401
    hiddenimports.append("index.cliente_remoto")
except Exception:
    pass

# llama-cpp-python trae sus DLL nativas (ggml, llama) como datos del paquete
binaries = []
try:
    from PyInstaller.utils.hooks import collect_dynamic_libs
    binaries += collect_dynamic_libs("llama_cpp")
    hiddenimports.append("llama_cpp")
except Exception:
    pass


a = Analysis(
    [str(RAIZ / "gui" / "server.py")],
    pathex=[str(RAIZ)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="AliadoLibre",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
