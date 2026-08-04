param(
    [switch]$Install
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command,
        [Parameter(Mandatory = $true)]
        [string]$Description
    )

    Write-Host "`n==> $Description" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed (exit code: $LASTEXITCODE)."
    }
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    if (-not $Install) {
        throw ".venv was not found. Use -Install on the first run."
    }
    Invoke-Checked -Description "Creating Python virtual environment" -Command {
        python -m venv (Join-Path $repoRoot ".venv")
    }
}

if ($Install) {
    Invoke-Checked -Description "Installing backend dependencies" -Command {
        & $venvPython -m pip install -r (Join-Path $repoRoot "backend\requirements.txt")
    }
    Invoke-Checked -Description "Installing AI Gateway dependencies" -Command {
        & $venvPython -m pip install -r (Join-Path $repoRoot "ai-gateway\requirements.txt")
    }

    $frontendPath = Join-Path $repoRoot "frontend"
    Push-Location $frontendPath
    try {
        Invoke-Checked -Description "Installing frontend dependencies" -Command {
            npm.cmd ci
        }
    }
    finally {
        Pop-Location
    }
}

Push-Location (Join-Path $repoRoot "backend")
try {
    $env:AVATAR_DIR = Join-Path ([System.IO.Path]::GetTempPath()) "nexus-local-test-avatars"
    Invoke-Checked -Description "Running backend tests" -Command {
        & $venvPython -m unittest discover -s tests -p "test_*.py" -v
    }
    Invoke-Checked -Description "Validating the Alembic migration chain" -Command {
        & $venvPython -m alembic heads
    }
    Invoke-Checked -Description "Validating FastAPI route registration" -Command {
        & $venvPython -c "from app.main import app; app.openapi()"
    }
}
finally {
    Pop-Location
}

Push-Location (Join-Path $repoRoot "ai-gateway")
try {
    Invoke-Checked -Description "Running AI Gateway tests" -Command {
        & $venvPython -m unittest discover -s tests -p "test_*.py" -v
    }
}
finally {
    Pop-Location
}

Push-Location (Join-Path $repoRoot "frontend")
try {
    Invoke-Checked -Description "Running frontend TypeScript checks" -Command {
        npm.cmd run lint
    }
}
finally {
    Pop-Location
}

Write-Host "`nAll local automated checks passed." -ForegroundColor Green
