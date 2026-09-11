#!/bin/bash
# Reanuda el reindexado 2 tras el CUDA error del 11-sep 15:31. No borra nada:
# el script salta los fragmentos ya presentes en Chroma.
REPO="C:/Users/fabia/GitHub/aliado-libre"
LOG="$REPO/_run/reindexado2.log"
PY="$REPO/.venv/Scripts/python.exe"
cd "$REPO" || exit 1
echo "[$(date +%H:%M:%S)] REANUDANDO reindexado 2 (GPU libre tras el fallo)" >> "$LOG"
"$PY" reindexar_con_gpu.py >> "$LOG" 2>&1
codigo=$?
echo "[$(date +%H:%M:%S)] FIN reindexado 2, codigo de salida $codigo" >> "$LOG"
exit $codigo
