"""Convierte un modelo ya entrenado a GGUF, el formato que usa llama-cpp-python
para servir sin necesitar Ollama ni PyTorch instalados — el objetivo final es
empaquetar esto dentro del .exe.

Colab a veces guarda el modelo COMPLETO fusionado (config.json + model.safetensors,
~1-2GB, ej. el primer modelo_lora_05b) y a veces guarda solo el adaptador LoRA
suelto (adapter_config.json + adapter_model.safetensors, unos pocos MB, ej.
modelo_lora_15b) — este script detecta cuál es y, si es un adaptador suelto,
lo fusiona primero con el modelo base descargado de Hugging Face.

Requiere el script convert_hf_to_gguf.py de llama.cpp (no se distribuye por
pip) — este script clona el repo automáticamente la primera vez, en
finetune/llama.cpp/ (shallow, ignorado en git).

Uso:
    ./venv/Scripts/python.exe finetune/exportar_gguf.py modelo_lora_05b
    ./venv/Scripts/python.exe finetune/exportar_gguf.py modelo_lora_15b --outtype q8_0
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
LLAMA_CPP = RAIZ / "llama.cpp"
SALIDA = RAIZ / "salida"
FUSIONADOS = RAIZ / "fusionados"


def asegurar_llama_cpp() -> Path:
    convert = LLAMA_CPP / "convert_hf_to_gguf.py"
    if convert.exists():
        return convert
    print("Clonando llama.cpp (solo la primera vez, shallow)...")
    subprocess.run(
        ["git", "clone", "--depth", "1", "https://github.com/ggml-org/llama.cpp", str(LLAMA_CPP)],
        check=True,
    )
    if not convert.exists():
        raise SystemExit(f"El clon no trajo {convert} — revisar si llama.cpp renombró el script.")
    return convert


def asegurar_paquete_gguf() -> None:
    faltantes = []
    try:
        import gguf  # noqa: F401
    except ImportError:
        faltantes.append("gguf")
    try:
        import sentencepiece  # noqa: F401
    except ImportError:
        faltantes.append("sentencepiece")
    if faltantes:
        print(f"Instalando paquetes requeridos por convert_hf_to_gguf.py: {faltantes}...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", *faltantes], check=True)


def fusionar_adaptador(modelo_dir: Path, nombre_modelo: str) -> Path:
    """Carga el modelo base indicado en adapter_config.json, le aplica el
    adaptador LoRA y guarda el resultado fusionado — convert_hf_to_gguf.py
    no entiende adaptadores PEFT sueltos, solo modelos completos."""
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    config = json.loads((modelo_dir / "adapter_config.json").read_text(encoding="utf-8"))
    modelo_base = config["base_model_name_or_path"]

    destino = FUSIONADOS / nombre_modelo
    if (destino / "model.safetensors").exists():
        print(f"Ya existe un fusionado en {destino}, se reusa.")
        return destino

    print(f"Cargando modelo base {modelo_base} para fusionar con el adaptador...")
    base = AutoModelForCausalLM.from_pretrained(modelo_base, dtype=torch.float32)
    tokenizer = AutoTokenizer.from_pretrained(modelo_base)

    print("Aplicando adaptador LoRA y fusionando...")
    modelo_peft = PeftModel.from_pretrained(base, str(modelo_dir))
    modelo_fusionado = modelo_peft.merge_and_unload()

    FUSIONADOS.mkdir(exist_ok=True)
    destino.mkdir(exist_ok=True)
    modelo_fusionado.save_pretrained(str(destino))
    tokenizer.save_pretrained(str(destino))
    print(f"Modelo fusionado guardado en {destino}")
    return destino


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("nombre_modelo", help="carpeta dentro de finetune/, ej. modelo_lora_05b")
    parser.add_argument(
        "--outtype",
        default="q8_0",
        choices=["f16", "f32", "q8_0"],
        help="precision de salida. q8_0 (por defecto) es 1/4 del tamaño de f32 sin "
        "necesitar compilar llama-quantize; para Q4_K_M hay que compilar llama.cpp aparte.",
    )
    args = parser.parse_args()

    modelo_dir = RAIZ / args.nombre_modelo
    if not modelo_dir.exists():
        raise SystemExit(f"No existe {modelo_dir} — descomprime el .zip de Colab ahí primero.")

    if (modelo_dir / "adapter_config.json").exists():
        print(f"{modelo_dir.name} es un adaptador LoRA suelto — fusionando con el modelo base primero.")
        modelo_dir = fusionar_adaptador(modelo_dir, args.nombre_modelo)
    elif not (modelo_dir / "model.safetensors").exists():
        raise SystemExit(
            f"{modelo_dir} no tiene ni model.safetensors ni adapter_config.json — ¿carpeta correcta?"
        )

    asegurar_paquete_gguf()
    convert = asegurar_llama_cpp()

    SALIDA.mkdir(exist_ok=True)
    archivo_salida = SALIDA / f"{args.nombre_modelo}.{args.outtype}.gguf"

    print(f"Convirtiendo {modelo_dir} -> {archivo_salida} ({args.outtype})...")
    subprocess.run(
        [
            sys.executable,
            str(convert),
            str(modelo_dir),
            "--outfile",
            str(archivo_salida),
            "--outtype",
            args.outtype,
        ],
        check=True,
    )

    tamano_mb = archivo_salida.stat().st_size / (1024 * 1024)
    print(f"Listo: {archivo_salida} ({tamano_mb:.0f} MB)")


if __name__ == "__main__":
    main()
