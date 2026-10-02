$ErrorActionPreference = "Stop"
$backendPath = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\backend"))
$pythonPath = Join-Path $backendPath ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "README.mdの手順でbackend\.venvを作成し、依存ライブラリをインストールしてください。"
}
Push-Location $backendPath
try { & $pythonPath -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log }
finally { Pop-Location }
