$ErrorActionPreference = "Stop"

Push-Location frontend-next
try {
    if (-not (Test-Path node_modules)) {
        npm install
    }
    npm run lint
    npm run typecheck
    npm run build
}
finally {
    Pop-Location
}
