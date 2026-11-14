# Lanza la beta publica desde este PC: web en modo publico + Cloudflare Tunnel.
#
# El servidor escucha SOLO en 127.0.0.1; el tunel se conecta desde dentro, asi
# que no se abre ningun puerto del router y la IP de la casa no se publica.
#
# Requisitos (una vez):
#   winget install --id Cloudflare.cloudflared
#   Clave de IA en %USERPROFILE%\.aliado_libre\credenciales.json (la del piloto)
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File scripts\lanzar_publico.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\lanzar_publico.ps1 -Tunel juris
#
# Sin -Tunel, Cloudflare da una URL aleatoria *.trycloudflare.com que cambia en
# cada arranque. Con -Tunel se usa el tunel con nombre creado por
# scripts\configurar_dominio.ps1, que sirve siempre en el dominio propio.

param([string]$Tunel = "")

$ErrorActionPreference = "Stop"
$Raiz = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Raiz ".venv\Scripts\python.exe"
$Puerto = 8765

if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Write-Host "Falta cloudflared. Instalalo con:  winget install --id Cloudflare.cloudflared" -ForegroundColor Yellow
    exit 1
}
if (-not (Test-Path $Python)) {
    Write-Host "No encuentro el entorno en $Python" -ForegroundColor Red
    exit 1
}

# --- configuracion de la beta (ver docs/PLANES.md y gui/publico.py) ---
$env:ALIADO_PUBLICO = "1"
$env:ALIADO_NOMBRE = "Juris-consulta ColombIA"
$env:ALIADO_PUERTO = "$Puerto"
$env:ALIADO_TOPE_APORTE = "15"          # desde la consulta 16 se pide aporte
$env:ALIADO_TOPE_DIARIO_IP = "30"       # desde la 31, pausa hasta medianoche
$env:ALIADO_REDACCIONES_DIARIAS = "3"   # respuestas redactadas por IA gratis al dia
$env:ALIADO_TOPE_GASTO_MES_USD = "10"   # tope de gasto de IA del mes
$env:ALIADO_CONFIAR_PROXY = "1"         # la IP real llega en CF-Connecting-IP
$env:ALIADO_RERANKER_ACTIVO = "1"       # reordenador local en GPU (recall@5 21,5->34,5% en la ruta real)
$env:ALIADO_BUSQUEDA_ASISTIDA = "0"     # con 1, Sonnet en cada busqueda (~0,027 USD) agota el tope y apaga la redaccion
$env:PYTHONWARNINGS = "ignore"

Write-Host "Arrancando la web en modo publico en http://127.0.0.1:$Puerto ..."
$web = Start-Process -FilePath $Python -ArgumentList (Join-Path $Raiz "gui\server.py") `
    -WorkingDirectory $Raiz -PassThru -WindowStyle Minimized

try {
    Start-Sleep -Seconds 3
    Write-Host "Ctrl+C cierra el tunel y la web." -ForegroundColor Cyan
    if ($Tunel) {
        Write-Host "Abriendo el tunel con nombre '$Tunel' (dominio propio)."
        & cloudflared tunnel --no-autoupdate run --url "http://127.0.0.1:$Puerto" $Tunel
    } else {
        Write-Host "Abriendo el tunel rapido. La URL publica aparece abajo (https://...trycloudflare.com)."
        & cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:$Puerto"
    }
}
finally {
    if ($web -and -not $web.HasExited) { Stop-Process -Id $web.Id -Force }
    Write-Host "Web detenida."
}
