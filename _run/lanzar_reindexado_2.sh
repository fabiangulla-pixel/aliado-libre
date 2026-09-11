#!/bin/bash
# Reindexado del 11-sep-2026: troceo corregido (ya no borra parrafos cortos) y
# TF32 al codificar. Embedding BASE a proposito: el afinado no gano de forma
# clara (+2,5 puntos, 11 anclas mejor contra 8 peor de 25), y cambiarlo a la vez
# que el troceo haria el resultado no atribuible.
REPO="C:/Users/fabia/GitHub/aliado-libre"
LOG="$REPO/_run/reindexado2.log"
PY="$REPO/.venv/Scripts/python.exe"

cd "$REPO" || exit 1

# El indice actual se aparta, no se borra: es el que da 37,5% y es la referencia
# contra la que se medira el efecto del troceo.
if [ -d "$REPO/index/chroma_db" ]; then
  rm -rf "$REPO/index/chroma_db.troceo_viejo"
  mv "$REPO/index/chroma_db" "$REPO/index/chroma_db.troceo_viejo" 2>>"$LOG" \
    && echo "[$(date +%H:%M:%S)] indice anterior apartado en index/chroma_db.troceo_viejo" > "$LOG"
fi
rm -f "$REPO/index/fts_index.db"

echo "[$(date +%H:%M:%S)] INICIO reindexado 2 (troceo corregido + TF32)" >> "$LOG"
"$PY" reindexar_con_gpu.py >> "$LOG" 2>&1
codigo=$?
echo "[$(date +%H:%M:%S)] FIN reindexado 2, codigo de salida $codigo" >> "$LOG"
exit $codigo
