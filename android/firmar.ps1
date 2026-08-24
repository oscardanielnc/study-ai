# Firma el APK ya compilado. Se ejecuta a mano porque pide la contrasena del
# keystore: esa contrasena es de Oscar y no debe pasar por ningun otro sitio.
#
#   powershell -ExecutionPolicy Bypass -File .\firmar.ps1
#
# Deja `estudia.apk` en esta misma carpeta, listo para instalar en el movil.

$ErrorActionPreference = "Stop"

$sdk = "C:\Users\LENOVO\.bubblewrap\android-sdk"
$env:JAVA_HOME = "C:\Users\LENOVO\.bubblewrap\jdk"
$herramientas = "$sdk\build-tools\36.1.0"

$aqui = Split-Path -Parent $MyInvocation.MyCommand.Path
$sinFirmar = "$aqui\app\build\outputs\apk\release\app-release-unsigned.apk"
$alineado = "$aqui\app-release-aligned.apk"
$final = "$aqui\estudia.apk"

if (-not (Test-Path $sinFirmar)) {
    throw "Falta el APK compilado. Ejecuta antes: .\gradlew.bat assembleRelease"
}

Write-Host "1/3  Alineando..." -ForegroundColor Cyan
if (Test-Path $alineado) { Remove-Item $alineado -Force }
& "$herramientas\zipalign.exe" -p 4 $sinFirmar $alineado

Write-Host "2/3  Firmando (te va a pedir la contrasena del keystore)..." -ForegroundColor Cyan
& "$herramientas\apksigner.bat" sign `
    --ks "$aqui\android.keystore" `
    --ks-key-alias estudia `
    --out $final `
    $alineado

Write-Host "3/3  Verificando la firma..." -ForegroundColor Cyan
& "$herramientas\apksigner.bat" verify --print-certs $final

Remove-Item $alineado -Force
Write-Host ""
Write-Host "Listo: $final" -ForegroundColor Green
Write-Host "La huella SHA-256 de arriba tiene que coincidir con la de assetlinks.json." -ForegroundColor Yellow
