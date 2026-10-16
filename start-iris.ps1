# Build and start IRIS for Health, wait until ready, create the empty FHIR server + tables.
$ErrorActionPreference = "Stop"
docker compose up --build -d
$sw = [System.Diagnostics.Stopwatch]::StartNew()
while (-not (docker exec ai-nor-iris iris session IRIS -U %SYS "write ""ready"",!" 2>$null)) {
    if ($sw.Elapsed.TotalSeconds -gt 300) { throw "IRIS not ready after 300 s, see: docker logs ai-nor-iris" }
    Write-Host "Waiting for IRIS... ($([int]$sw.Elapsed.TotalSeconds)s)"
    Start-Sleep -Seconds 3
}
Push-Location backend
.\.venv\Scripts\python.exe -m scripts.setup_iris
Pop-Location
Write-Host "FHIR: http://localhost:52773/fhir/r4/metadata  (SuperUser / SYS)"
