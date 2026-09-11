#!/bin/bash
# Espera a que termine el trabajo del Boletin de hidrologia (ParrillaPRO), cierra
# los modelos locales para liberar la GPU y lanza el reindexado de Aliado Libre.
# No deben competir: una sesion paralela ya mato un reindexado largo en silencio.
REPO="C:/Users/fabia/GitHub/aliado-libre"
LOG="$REPO/_run/reindexado.log"
PY="$REPO/.venv/Scripts/python.exe"

# Solo python.exe: el patron se encuentra a si mismo en la linea de comandos del
# propio powershell y de los bash que lo lanzan (daba 9 procesos en vez de 2).
vivos() {
  powershell -NoProfile -Command "(Get-CimInstance Win32_Process | Where-Object { \$_.Name -eq 'python.exe' -and \$_.CommandLine -match 'banco_cli' } | Measure-Object).Count" 2>/dev/null | tr -d '\r\n '
}

vram() {
  nvidia-smi --query-gpu=memory.used --format=csv,noheader 2>/dev/null | head -1 | tr -d '\r'
}

echo "[$(date +%H:%M:%S)] ESPERA: aguardando a banco_cli.py (Boletin Ideam)" > "$LOG"
while true; do
  n=$(vivos)
  [ -z "$n" ] && n=0
  if [ "$n" -eq 0 ]; then break; fi
  echo "[$(date +%H:%M:%S)] ESPERA: $n proceso(s) banco_cli.py activos" >> "$LOG"
  sleep 60
done
echo "[$(date +%H:%M:%S)] el otro trabajo termino" >> "$LOG"

# Los modelos locales eran para ParrillaPRO esta noche. Ya cumplieron, y Fabian
# autorizo cerrarlos: tenian 12,8 GB de los 16,3 GB de VRAM tomados.
echo "[$(date +%H:%M:%S)] VRAM antes de liberar: $(vram)" >> "$LOG"
powershell -NoProfile -Command "Get-Process -Name 'LM Studio','llama-server','ollama app','ollama' -ErrorAction SilentlyContinue | Stop-Process -Force" >> "$LOG" 2>&1
sleep 15
echo "[$(date +%H:%M:%S)] VRAM tras cerrar LM Studio y Ollama: $(vram)" >> "$LOG"

# El indice en disco es el roto (158k fragmentos, texto mutilado, sin passage:).
# Se aparta en vez de borrarse: la reanudacion saltaria esos fragmentos malos.
if [ -d "$REPO/index/chroma_db" ]; then
  mv "$REPO/index/chroma_db" "$REPO/index/chroma_db.roto_9sep" 2>>"$LOG" \
    && echo "[$(date +%H:%M:%S)] indice roto apartado en index/chroma_db.roto_9sep" >> "$LOG"
fi
rm -f "$REPO/index/fts_index.db"

cd "$REPO" || exit 1
echo "[$(date +%H:%M:%S)] INICIO reindexado (~849.000 fragmentos esperados)" >> "$LOG"
"$PY" reindexar_con_gpu.py >> "$LOG" 2>&1
codigo=$?
echo "[$(date +%H:%M:%S)] FIN reindexado, codigo de salida $codigo" >> "$LOG"
exit $codigo
