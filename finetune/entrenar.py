"""Fine-tuning LoRA de un modelo chico para responder preguntas de derecho
colombiano basándose SOLO en los fragmentos que se le den (mismo contrato
que index/responder.py). Corre en CPU — lento, pero funcional: LoRA solo
entrena una fracción de los parámetros del modelo base.

Base: Qwen2.5-3B-Instruct (sin gating en Hugging Face, buen español, bien
soportado por llama.cpp/Ollama para exportar a GGUF después).

Uso:
    ./venv/Scripts/python.exe finetune/entrenar.py
"""

from __future__ import annotations

import json
from pathlib import Path

from datasets import Dataset
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import SFTConfig, SFTTrainer

RAIZ = Path(__file__).resolve().parent
MODELO_BASE = "Qwen/Qwen2.5-3B-Instruct"
SALIDA_LORA = RAIZ / "modelo_lora"


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

    modelo = AutoModelForCausalLM.from_pretrained(MODELO_BASE, torch_dtype="auto")

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
        output_dir=str(RAIZ / "checkpoints"),
        use_cpu=True,
        num_train_epochs=3,
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
