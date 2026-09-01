"""Fine-tuning LoRA de un modelo chico para responder preguntas de derecho
colombiano basándose SOLO en los fragmentos que se le den (mismo contrato
que index/responder.py). Corre en CPU — lento, pero funcional: LoRA solo
entrena una fracción de los parámetros del modelo base.

Base: Qwen2.5-3B-Instruct (sin gating en Hugging Face, buen español, bien
soportado por llama.cpp/Ollama para exportar a GGUF después).

Uso:
    ./venv/Scripts/python.exe finetune/entrenar.py [modelo_base] [nombre_salida]
    ./venv/Scripts/python.exe finetune/entrenar.py Qwen/Qwen2.5-0.5B-Instruct modelo_lora_05b
    ./venv/Scripts/python.exe finetune/entrenar.py Qwen/Qwen2.5-1.5B-Instruct modelo_lora_15b
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from datasets import Dataset
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import SFTConfig, SFTTrainer

RAIZ = Path(__file__).resolve().parent
MODELO_BASE = sys.argv[1] if len(sys.argv) > 1 else "Qwen/Qwen2.5-3B-Instruct"
NOMBRE_SALIDA = sys.argv[2] if len(sys.argv) > 2 else "modelo_lora"
SALIDA_LORA = RAIZ / NOMBRE_SALIDA


def cargar_dataset() -> Dataset:
    ruta = RAIZ / "data" / "entrenamiento.jsonl"
    ejemplos = [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines() if linea.strip()]
    textos = [f"{ej['prompt']}{ej['completion']}" for ej in ejemplos]
    return Dataset.from_dict({"text": textos})


def main() -> None:
    print("Cargando dataset de entrenamiento...")
    dataset = cargar_dataset()
    print(f"{len(dataset)} ejemplos cargados")

    print(f"Cargando modelo base {MODELO_BASE} (puede tardar, descarga ~6GB la primera vez)...")
    tokenizer = AutoTokenizer.from_pretrained(MODELO_BASE)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # float32 explícito: los checkpoints de Qwen traen bfloat16 por defecto,
    # pero esta CPU no tiene soporte de hardware para bf16 (AMD Ryzen 5500U
    # sin AVX512-BF16) — PyTorch lo emula por software, mucho más lento que
    # usar float32 con las instrucciones vectoriales que el chip sí soporta.
    modelo = AutoModelForCausalLM.from_pretrained(MODELO_BASE, dtype="float32")

    # LoRA: solo se entrenan estas matrices pequeñas insertadas en las capas
    # de atención, no los ~3B parámetros del modelo completo — es lo que
    # hace viable esto en CPU en horas y no en días.
    config_lora = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        task_type="CAUSAL_LM",
    )
    modelo = get_peft_model(modelo, config_lora)
    modelo.print_trainable_parameters()

    argumentos = SFTConfig(
        output_dir=str(RAIZ / f"checkpoints_{NOMBRE_SALIDA}"),
        use_cpu=True,
        num_train_epochs=2,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        logging_steps=1,
        save_strategy="epoch",
        report_to=[],
        max_length=1024,
        dataset_text_field="text",
    )

    entrenador = SFTTrainer(
        model=modelo,
        args=argumentos,
        train_dataset=dataset,
        processing_class=tokenizer,
    )

    print("Entrenando (esto va a tardar varias horas en CPU)...")
    entrenador.train()

    print(f"Guardando adaptador LoRA en {SALIDA_LORA}...")
    modelo.save_pretrained(str(SALIDA_LORA))
    tokenizer.save_pretrained(str(SALIDA_LORA))
    print("Listo. Siguiente paso: finetune/exportar_gguf.py para usarlo en Ollama.")


if __name__ == "__main__":
    main()
