# Registra (o quita con -Quitar) la tarea programada "AliadoLibre-OCR": corre
# scripts\ocr_cs_lanzar.ps1 al iniciar sesion y cada 5 minutos, para que el OCR
# de la Corte Suprema se retome solo tras cerrar sesion, reiniciar o apagar.
# No requiere permisos de administrador (tarea del usuario actual).
param([switch]$Quitar)

$Nombre = "AliadoLibre-OCR"
if ($Quitar) {
    Unregister-ScheduledTask -TaskName $Nombre -Confirm:$false
    Write-Output "Tarea $Nombre quitada."
    exit 0
}

$Lanzador = Join-Path $PSScriptRoot "ocr_cs_lanzar.ps1"
$accion = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Lanzador`""
$alIniciar = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$periodico = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 5)
# Sin limite de tiempo; no arranca en bateria (el trabajador ademas se pausa solo si pasa a bateria).
$ajustes = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $Nombre -Action $accion -Trigger $alIniciar, $periodico -Settings $ajustes `
    -Principal $principal -Force | Out-Null
Write-Output "Tarea $Nombre registrada: al iniciar sesion y cada 5 minutos."
