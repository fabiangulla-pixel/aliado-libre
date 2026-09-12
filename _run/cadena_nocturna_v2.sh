#!/bin/bash
# Cadena del 11 al 12-sep, v2. Archivo NUEVO a proposito: bash lee los scripts
# de forma incremental, asi que reescribir uno que esta corriendo hace que el
# proceso vivo ejecute una mezcla de dos versiones.
#
# NO usa pgrep: no existe en Git Bash, y un comando inexistente devuelve error,
# que un `while` lee como "ya no corre". Se espera una linea concreta en el log
# ajeno, que es senal POSITIVA.
REPO="C:/Users/fabia/GitHub/aliado-libre"
LOG="$REPO/_run/reindexado2.log"
CADENA="$REPO/_run/cadena.log"
SENAL="C:/Comparativa_modelos/cierre.log"
FRASE="=== FIN DE MI PARTE (sin apagar) ==="
PY="$REPO/.venv/Scripts/python.exe"

apunta() { echo "[$(date +%H:%M:%S)] $1" >> "$CADENA"; }

suyos_vivos() {
  local n
  n=$(powershell -NoProfile -Command "(Get-CimInstance Win32_Process | Where-Object { \$_.Name -eq 'python.exe' -and \$_.CommandLine -match 'banco_flujo' -and \$_.CommandLine -notmatch 'Get-CimInstance' } | Measure-Object).Count" 2>/dev/null | tr -d '\r\n ')
  case "$n" in
    ''|*[!0-9]*) echo 99 ;;   # si no sé, asumo que siguen: nunca doy paso a ciegas
    *) echo "$n" ;;
  esac
}

echo "[$(date +%H:%M:%S)] esperando la senal de la otra sesion" > "$CADENA"
while ! grep -qF "$FRASE" "$SENAL" 2>/dev/null; do
  sleep 60
done
apunta "senal recibida"

# Cinturon y tirantes. La v1 esperaba 30 minutos y DESPUES seguia igual, tuviera
# o no la GPU libre: si la consulta fallaba y devolvia 99, arrancaba contra una
# GPU ocupada. Ahora, si tras la espera siguen vivos, NO se procede.
espera=0
while [ "$(suyos_vivos)" -ne 0 ]; do
  espera=$((espera+1))
  if [ "$espera" -gt 60 ]; then
    apunta "ABORTO: su senal esta, pero tras 60 min siguen apareciendo procesos suyos."
    apunta "No arranco: prefiero no reindexar a competir por la GPU o a leer mal el estado."
    exit 1
  fi
  apunta "su senal esta, pero quedan procesos suyos; espero ($espera min)"
  sleep 60
done

apunta "GPU libre, retomando reindexado"
cd "$REPO" || exit 1
echo "[$(date +%H:%M:%S)] REANUDANDO reindexado 2 (turno recibido)" >> "$LOG"
"$PY" reindexar_con_gpu.py >> "$LOG" 2>&1
codigo=$?
echo "[$(date +%H:%M:%S)] FIN reindexado 2, codigo de salida $codigo" >> "$LOG"
apunta "reindexado terminado con codigo $codigo"
exit $codigo
