#!/bin/bash
# Apaga el MSI SOLO si la noche quedo cerrada para TODOS. Fabian pidio que yo
# apague por ser la ultima en usar la maquina, pero un apagado con otra sesion
# trabajando le destruye el trabajo a alguien. Cada condicion se comprueba aqui.
REPO="C:/Users/fabia/GitHub/aliado-libre"
COMPARATIVA="C:/Comparativa_modelos"
cd "$REPO" || exit 1
fallos=0

comprobar() {
  if [ "$2" -eq 0 ]; then echo "  OK    $1"; else echo "  FALLA $1"; fallos=$((fallos+1)); fi
}

contar_python() {  # $1 = patron en la linea de comandos
  # PowerShell, no pgrep: pgrep NO EXISTE en Git Bash y un comando inexistente
  # devuelve error, que un `while` interpreta como "ya no corre". Asi se apagaria
  # el equipo con la otra sesion viva. El -notmatch excluye a la propia consulta.
  local n
  n=$(powershell -NoProfile -Command "(Get-CimInstance Win32_Process | Where-Object { \$_.Name -eq 'python.exe' -and \$_.CommandLine -match '$1' -and \$_.CommandLine -notmatch 'Get-CimInstance' } | Measure-Object).Count" 2>/dev/null | tr -d '\r\n ')
  [ -z "$n" ] && n=99   # si la consulta falla, se asume lo peor
  echo "$n"
}

echo "=== Condiciones para apagar ==="

# --- La otra sesion: senal POSITIVA, no ausencia de proceso ---
# -F (cadena literal) y RUTA EXACTA, nunca un comodin: la frase existe tambien
# en el script ajeno que la escribe y en un log fallido que llego a escribirla
# con su corrida viva. Un *.log aqui habria dado el turno por bueno de mas.
if grep -qF "=== FIN DE MI PARTE (sin apagar) ===" "$COMPARATIVA/cierre.log" 2>/dev/null; then
  comprobar "la otra sesion dejo su senal de FIN en cierre.log" 0
else
  comprobar "la otra sesion NO ha dejado su senal en cierre.log" 1
fi

b=$(contar_python "banco_flujo")
comprobar "ningun banco_flujo vivo (hay $b)" "$([ "$b" -eq 0 ] && echo 0 || echo 1)"

# --- Lo mio ---
n=$(contar_python "reindexar_con_gpu")
comprobar "ningun reindexado vivo (hay $n)" "$([ "$n" -eq 0 ] && echo 0 || echo 1)"

sucio=$(git status --porcelain | wc -l)
comprobar "arbol de git limpio ($sucio sin commitear)" "$([ "$sucio" -eq 0 ] && echo 0 || echo 1)"

# Exito REAL, no cualquier linea de FIN: el intento que murio a las 15:31 con
# CUDA error tambien escribio "FIN reindexado 2", y con el grep ingenuo esta
# condicion pasaba estando el trabajo abortado.
grep -q "FIN reindexado 2, codigo de salida 0" _run/reindexado2.log 2>/dev/null
comprobar "el reindexado termino con codigo 0" $?

test -s index/fts_index.db
comprobar "el indice lexico FTS5 existe" $?

test -f _run/INFORME_12sep.md
comprobar "informe de la noche escrito" $?

echo
if [ "$fallos" -gt 0 ]; then
  echo "NO SE APAGA: $fallos condicion(es) sin cumplir. Queda todo como esta."
  exit 1
fi
echo "Todas las condiciones se cumplen. Apagando en 90 segundos."
echo "Para cancelar: shutdown /a"
# MSYS_NO_PATHCONV: Git Bash convierte /s y /t en rutas y shutdown imprime su ayuda.
MSYS_NO_PATHCONV=1 shutdown /s /t 90 /c "Aliado Libre: cadena nocturna terminada"
