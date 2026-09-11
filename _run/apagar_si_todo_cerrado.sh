#!/bin/bash
# Apaga el PC SOLO si la noche quedo realmente cerrada. Fabian lo autorizo
# expresamente ("cuando termines vas a apagar el pc"), pero un apagado con algo
# a medias destruye trabajo, asi que cada condicion se comprueba aqui y no de
# memoria. Si alguna falla, NO apaga y explica por que.
REPO="C:/Users/fabia/GitHub/aliado-libre"
cd "$REPO" || exit 1
fallos=0

comprobar() {
  if [ "$2" -eq 0 ]; then echo "  OK    $1"; else echo "  FALLA $1"; fallos=$((fallos+1)); fi
}

echo "=== Condiciones para apagar ==="

n=$(powershell -NoProfile -Command "(Get-CimInstance Win32_Process | Where-Object { \$_.Name -eq 'python.exe' -and \$_.CommandLine -match 'reindexar_con_gpu' -and \$_.CommandLine -notmatch 'Get-CimInstance' } | Measure-Object).Count" 2>/dev/null | tr -d '\r\n ')
[ -z "$n" ] && n=99
comprobar "ningun reindexado vivo (hay $n)" "$([ "$n" -eq 0 ] && echo 0 || echo 1)"

b=$(powershell -NoProfile -Command "(Get-CimInstance Win32_Process | Where-Object { \$_.Name -eq 'python.exe' -and \$_.CommandLine -match 'banco_cli' -and \$_.CommandLine -notmatch 'Get-CimInstance' } | Measure-Object).Count" 2>/dev/null | tr -d '\r\n ')
[ -z "$b" ] && b=99
comprobar "ningun trabajo de ParrillaPRO vivo (hay $b)" "$([ "$b" -eq 0 ] && echo 0 || echo 1)"

sucio=$(git status --porcelain | wc -l)
comprobar "arbol de git limpio ($sucio archivos sin commitear)" "$([ "$sucio" -eq 0 ] && echo 0 || echo 1)"

grep -q "FIN reindexado" _run/reindexado.log 2>/dev/null
comprobar "el reindexado dejo linea de FIN en la bitacora" $?

test -f _run/INFORME_NOCHE.md
comprobar "informe de la noche escrito" $?

echo
if [ "$fallos" -gt 0 ]; then
  echo "NO SE APAGA: $fallos condicion(es) sin cumplir. Queda todo como esta."
  exit 1
fi
echo "Todas las condiciones se cumplen. Apagando en 90 segundos."
echo "Para cancelar: shutdown /a"
# MSYS_NO_PATHCONV: Git Bash convierte /s y /t en rutas de Windows antes de
# pasarlas, y shutdown.exe responde imprimiendo su ayuda sin apagar nada.
MSYS_NO_PATHCONV=1 shutdown /s /t 90 /c "Aliado Libre: trabajo de la noche terminado"
