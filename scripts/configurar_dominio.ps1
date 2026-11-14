# Configura UNA SOLA VEZ el tunel con nombre de Cloudflare para servir la web
# en un dominio propio (el dominio debe estar ya en la cuenta de Cloudflare).
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File scripts\configurar_dominio.ps1 -Dominio jurisconsulta.co
#
# Pasos que hace:
#   1. cloudflared tunnel login  -> abre el navegador; elegir el dominio y autorizar
#   2. cloudflared tunnel create -> credenciales en %USERPROFILE%\.cloudflared (NO van al repo)
#   3. cloudflared tunnel route dns -> registros CNAME para el dominio y www
# Despues: scripts\lanzar_publico.ps1 -Tunel <nombre>

param(
    [Parameter(Mandatory = $true)][string]$Dominio,
    [string]$Tunel = "juris"
)

$ErrorActionPreference = "Stop"
$Cert = Join-Path $env:USERPROFILE ".cloudflared\cert.pem"

if (-not (Test-Path $Cert)) {
    Write-Host "1/3 Se abre el navegador: entra a tu cuenta de Cloudflare, elige $Dominio y pulsa Authorize." -ForegroundColor Cyan
    & cloudflared tunnel login
    if (-not (Test-Path $Cert)) { Write-Host "No se completo el login." -ForegroundColor Red; exit 1 }
} else {
    Write-Host "1/3 Ya hay sesion de Cloudflare ($Cert)."
}

$existentes = & cloudflared tunnel list --output json | ConvertFrom-Json
if ($existentes | Where-Object { $_.name -eq $Tunel }) {
    Write-Host "2/3 El tunel '$Tunel' ya existe."
} else {
    Write-Host "2/3 Creando el tunel '$Tunel'..."
    & cloudflared tunnel create $Tunel
}

Write-Host "3/3 Apuntando $Dominio y www.$Dominio al tunel..."
& cloudflared tunnel route dns $Tunel $Dominio
& cloudflared tunnel route dns $Tunel "www.$Dominio"

Write-Host ""
Write-Host "Listo. Para servir la web en https://$Dominio :" -ForegroundColor Green
Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\lanzar_publico.ps1 -Tunel $Tunel"
