$ErrorActionPreference = "Stop"

Push-Location frontend-next
try {
    if (-not (Test-Path node_modules)) {
        npm install
        if ($LASTEXITCODE -ne 0) { throw "npm install failed" }
    }
    npm run lint
    if ($LASTEXITCODE -ne 0) { throw "frontend-next lint failed" }
    npm run typecheck
    if ($LASTEXITCODE -ne 0) { throw "frontend-next typecheck failed" }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "frontend-next build failed" }
}
finally {
    Pop-Location
}
