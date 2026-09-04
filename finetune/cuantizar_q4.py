"""Genera una versión Q4_K_M (mucho más chica que Q8_0) de un modelo ya
exportado, usando el binario llama-quantize compilado localmente
(finetune/llama.cpp/build/bin/Release/llama-quantize.exe — ver
finetune/README de compilación más abajo si no existe).

Q4_K_M no se puede generar directo desde convert_hf_to_gguf.py (ese script
solo hace f32/f16/q8_0 sin compilar nada) — hace falta re-cuantizar un GGUF
f16 con el binario compilado de llama.cpp.

Uso:
    ./venv/Scripts/python.exe finetune/cuantizar_q4.py modelo_lora_15b
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from finetune.exportar_gguf import RAIZ, SALIDA, asegurar_llama_cpp, asegurar_paquete_gguf, fusionar_adaptador

QUANTIZE_BIN = RAIZ / "llama.cpp" / "build" / "bin" / "Release" / "llama-quantize.exe"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("nombre_modelo", help="carpeta dentro de finetune/, ej. modelo_lora_15b")
    parser.add_argument(
        "--tipo", default="Q4_K_M", help="tipo de cuantización de llama-quantize (default Q4_K_M)"
    )
    args = parser.parse_args()

    if not QUANTIZE_BIN.exists():
        raise SystemExit(
            f"No existe {QUANTIZE_BIN} — compílalo primero:\n"
            "  cmake -B finetune/llama.cpp/build -S finetune/llama.cpp "
            "-DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_CURL=OFF\n"
            "  cmake --build finetune/llama.cpp/build --config Release --target llama-quantize"
        )

    modelo_dir = RAIZ / args.nombre_modelo
    if not modelo_dir.exists():
        raise SystemExit(f"No existe {modelo_dir}")

    if (modelo_dir / "adapter_config.json").exists():
        modelo_dir = fusionar_adaptador(modelo_dir, args.nombre_modelo)

    asegurar_paquete_gguf()
    convert = asegurar_llama_cpp()

    SALIDA.mkdir(exist_ok=True)
    f16_path = SALIDA / f"{args.nombre_modelo}.f16.gguf"
    if not f16_path.exists():
        print(f"Generando intermedio f16: {f16_path} (necesario como entrada de llama-quantize)...")
        subprocess.run(
            [sys.executable, str(convert), str(modelo_dir), "--outfile", str(f16_path), "--outtype", "f16"],
            check=True,
        )
    else:
        print(f"Ya existe el intermedio f16 en {f16_path}, se reusa.")

    salida_q4 = SALIDA / f"{args.nombre_modelo}.{args.tipo.lower()}.gguf"
    print(f"Cuantizando a {args.tipo}: {salida_q4}...")
    subprocess.run([str(QUANTIZE_BIN), str(f16_path), str(salida_q4), args.tipo], check=True)

    tamano_f16 = f16_path.stat().st_size / (1024 * 1024)
    tamano_q4 = salida_q4.stat().st_size / (1024 * 1024)
    print(
        f"\nf16: {tamano_f16:.0f} MB -> {args.tipo}: {tamano_q4:.0f} MB "
        f"({tamano_q4 / tamano_f16 * 100:.0f}% del tamaño)"
    )
    print(f"Listo: {salida_q4}")


if __name__ == "__main__":
    main()
