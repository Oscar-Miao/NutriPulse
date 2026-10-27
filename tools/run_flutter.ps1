param(
    [string]$FlutterSdk = (Join-Path $PSScriptRoot '..\tmp\flutter-sdk'),
    [string]$Device = 'emulator-5554'
)

$ErrorActionPreference = 'Stop'
$taskRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$taskFlutter = Join-Path $FlutterSdk 'bin\flutter.bat'
if (-not (Test-Path -LiteralPath $taskFlutter)) {
    throw '找不到 Flutter SDK。请用 -FlutterSdk 指定已安装的 SDK 目录。'
}
$taskFlutter = (Resolve-Path -LiteralPath $taskFlutter).Path
$taskTemporary = Join-Path $taskRoot 'tmp'
New-Item -ItemType Directory -Path $taskTemporary -Force | Out-Null
$env:TEMP = $taskTemporary
$env:TMP = $taskTemporary
$env:PUB_CACHE = Join-Path $taskTemporary 'pub-cache'
$env:JAVA_OPTS = "-Xms64m -Xmx2048m -Dfile.encoding=UTF-8 -Djava.io.tmpdir=$taskTemporary"
$env:GRADLE_OPTS = '-Dorg.gradle.daemon=false'
Push-Location (Join-Path $taskRoot 'client')
try {
    & $taskFlutter run -d $Device
    $taskExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $taskExitCode
