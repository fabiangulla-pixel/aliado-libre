# Lanza (o no) el trabajador de OCR de la Corte Suprema. Lo llama la tarea
# programada "AliadoLibre-OCR" al iniciar sesion y cada 5 minutos; es seguro
# llamarlo de mas: si ya hay un trabajador vivo, no hace nada.
#
#   Pausar:   crear data\ocr_corte_suprema\PAUSA  (el trabajador termina la
#             sentencia en curso y sale; la tarea no lo relanza)
#   Reanudar: borrar ese archivo
#   Quitar:   scripts\ocr_cs_tarea.ps1 -Quitar

$ErrorActionPreference = "Stop"
$Raiz = Split-Path -Parent $PSScriptRoot
$Carpeta = Join-Path $Raiz "data\ocr_corte_suprema"
$Python = "C:\dev\venv-paddle\Scripts\python.exe"
$Log = Join-Path $Raiz "_run\ocr_cs_trabajador.log"

if (Test-Path (Join-Path $Carpeta "_terminado")) { exit 0 }
if (Test-Path (Join-Path $Carpeta "PAUSA")) { exit 0 }
if (-not (Test-Path (Join-Path $Carpeta "pendientes.jsonl"))) { exit 0 }

$procesos = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Select-Object ProcessId, CommandLine
# El reindexado necesita la GPU entera: se espera a que termine.
if ($procesos | Where-Object { $_.CommandLine -like "*reindexar_con_gpu*" }) { exit 0 }

# Cuantos procesos comparten la GPU (archivo _partes; 1 si no existe).
$Partes = 1
$ArchivoPartes = Join-Path $Carpeta "_partes"
if (Test-Path $ArchivoPartes) { $Partes = [int](Get-Content $ArchivoPartes -TotalCount 1) }

New-Item -ItemType Directory -Force (Split-Path $Log) | Out-Null
for ($i = 0; $i -lt $Partes; $i++) {
    if ($procesos | Where-Object { $_.CommandLine -like "*ocr_cs_trabajador*--parte $i --partes*" }) { continue }
    $LogParte = $Log -replace "\.log$", "_p$i.log"
    $cmd = "`"$Python`" -u `"$Raiz\scripts\ocr_cs_trabajador.py`" --parte $i --partes $Partes >> `"$LogParte`" 2>&1"
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "`"$cmd`"" -WorkingDirectory $Raiz -WindowStyle Hidden
}
