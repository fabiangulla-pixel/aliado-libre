#!/usr/bin/env bash
# Cadena de trabajo que corre sin internet y solo con CPU.
#
# Se lanza ANTES de que el equipo se quede sin conexión, porque sin internet
# tampoco hay asistente que la arranque después. Por eso es autosuficiente:
# espera sola a que termine la generación del banco (que sí necesita red), y
# sigue aunque esa generación se quede a medias por el corte.
#
# Orden a propósito: lo que responde la pregunta abierta va primero, y el
# control del q8 —~3h, reanudable, guarda cada respuesta— va al final, donde
# quedarse a medias no cuesta nada.
set -u
cd "$(dirname "$0")/.." || exit 1
PY=./venv/Scripts/python.exe
mkdir -p finetune/eval

marca() { echo "=== $(date '+%H:%M:%S') $* ==="; }
consultas() { $PY -c "import json;print(len(json.load(open('finetune/eval/banco_coloquial.json',encoding='utf-8'))))" 2>/dev/null || echo 0; }

marca "PASO 0/3 — esperando a que termine el banco coloquial"
# Dos formas de terminar: el generador dice "Listo:", o el archivo deja de
# crecer (lo que pasa si el corte de internet mata la generación a medias).
ESPERA_MAXIMA=2400   # 40 min
sin_cambios=0
anterior=$(consultas)
for ((t = 0; t < ESPERA_MAXIMA; t += 30)); do
    if grep -q "^Listo:" finetune/banco_coloquial.log 2>/dev/null; then
        marca "banco completo"
        break
    fi
    sleep 30
    actual=$(consultas)
    if [ "$actual" = "$anterior" ]; then
        sin_cambios=$((sin_cambios + 1))
        if [ "$sin_cambios" -ge 6 ]; then   # 3 min sin crecer
            marca "el banco dejó de crecer (¿se cortó la red?), sigo con lo que hay"
            break
        fi
    else
        sin_cambios=0
        anterior=$actual
    fi
done
marca "banco con $(consultas) consultas"

marca "PASO 1/3 — recuperación ACTUAL sobre el banco coloquial"
$PY finetune/medir_recuperacion.py > finetune/log_recuperacion_base.log 2>&1
echo "  codigo de salida: $?  (finetune/log_recuperacion_base.log)"

marca "PASO 2/3 — recuperación CON reescritura (submuestra equilibrada)"
# reescribir cuesta ~8s de CPU por consulta: el banco entero no cabe en la
# ventana. 320 mantiene 40 por perfil, suficiente para comparar perfiles.
$PY finetune/medir_recuperacion.py --reescribir --limite 320 > finetune/log_recuperacion_reescrita.log 2>&1
echo "  codigo de salida: $?  (finetune/log_recuperacion_reescrita.log)"

marca "PASO 3/3 — control en CPU del q8_0 (150 preguntas, reanudable)"
$PY finetune/generar_respuestas_local.py finetune/salida/modelo_lora_15b.q8_0.gguf \
    --salida finetune/respuestas_gpu/respuestas_local_q8.json \
    > finetune/log_q8_cpu.log 2>&1
echo "  codigo de salida: $?  (finetune/log_q8_cpu.log)"

marca "CADENA TERMINADA"
