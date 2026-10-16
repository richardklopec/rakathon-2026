# Build and start IRIS for Health, wait until ready, create the empty FHIR server + tables.
# Note: no $ErrorActionPreference = "Stop" - in Windows PowerShell 5.1 docker's progress output on
# stderr would abort the script. Exit codes are checked explicitly instead.
Set-Location $PSScriptRoot

docker compose up --build -d
if ($LASTEXITCODE -ne 0) { Write-Error "docker compose failed (exit $LASTEXITCODE)"; exit 1 }

$sw = [System.Diagnostics.Stopwatch]::StartNew()
# wait for the container healthcheck: the superserver (1972) accepts connections only after that
while ((docker inspect -f '{{.State.Health.Status}}' ai-nor-iris 2>$null) -ne "healthy") {
    if ($sw.Elapsed.TotalSeconds -gt 300) { Write-Error "IRIS not ready after 300 s, see: docker logs ai-nor-iris"; exit 1 }
    Write-Host "Waiting for IRIS... ($([int]$sw.Elapsed.TotalSeconds)s)"
    Start-Sleep -Seconds 3
}

Push-Location backend
& .\.venv\Scripts\python.exe -m scripts.setup_iris
$code = $LASTEXITCODE
Pop-Location
if ($code -ne 0) { Write-Error "setup_iris failed (exit $code)"; exit 1 }
Write-Host "FHIR: http://localhost:52773/fhir/r4/metadata  (SuperUser / SYS)"
