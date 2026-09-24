param([switch]$Initialize, [switch]$PrepareOnly)

$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$configPath = Join-Path $repo '.env.local.json'
$previousPassword = $env:PSYEVO_POSTGRES_PASSWORD
$previousDatabase = $env:PSYEVO_DATABASE_URL
$previousEnvironment = $env:PSYEVO_ENV

Push-Location $repo
try {
    if (!(Test-Path -LiteralPath $configPath)) {
        if (!$Initialize) {
            throw 'Local configuration missing. Run scripts/start-dev.ps1 -Initialize once.'
        }
        $volumes = & docker volume ls --format '{{.Name}}'
        if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect Docker volumes.' }
        if ($volumes -contains 'psyevoagent_postgres_data') {
            throw 'Existing development volume found. Restore .env.local.json with its original password; do not reset the volume.'
        }
        $bytes = New-Object byte[] 32
        $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
        $password = [Convert]::ToBase64String($bytes)
        @{ postgres_password = $password } | ConvertTo-Json | Set-Content -LiteralPath $configPath -Encoding UTF8
    }
    try {
        $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($config.postgres_password -isnot [string] -or !$config.postgres_password) { throw 'Invalid password' }
    } catch { throw 'Invalid local configuration. Expected a nonempty postgres_password in .env.local.json.' }
    $env:PSYEVO_POSTGRES_PASSWORD = $config.postgres_password
    $encodedPassword = [Uri]::EscapeDataString($config.postgres_password)
    $env:PSYEVO_DATABASE_URL = "postgresql+psycopg://psyevo:${encodedPassword}@127.0.0.1:55432/psyevo_synthetic_dev?connect_timeout=3"
    $env:PSYEVO_ENV = 'development'
    & docker compose -p psyevoagent up -d --wait --wait-timeout 120 postgres
    if ($LASTEXITCODE -ne 0) { throw 'Development PostgreSQL failed to start; check Docker and port 55432.' }
    Push-Location (Join-Path $repo 'backend')
    try {
        # Migration exceptions may include connection details: never print raw output.
        $ErrorActionPreference = 'Continue'
        try { $migrationOutput = & uv run --no-sync alembic upgrade head 2>&1 }
        finally { $ErrorActionPreference = 'Stop' }
        if ($LASTEXITCODE -ne 0) { throw 'Database migration failed. Check local credentials and database availability; no reset was performed.' }
        Write-Host 'Development database ready on 127.0.0.1:55432; migrations complete.'
        if (!$PrepareOnly) {
            & uv run --no-sync python -m app.dev
            if ($LASTEXITCODE -ne 0) { throw 'Development API stopped with an error.' }
        }
    } finally { Pop-Location }
} finally {
    $env:PSYEVO_POSTGRES_PASSWORD = $previousPassword
    $env:PSYEVO_DATABASE_URL = $previousDatabase
    $env:PSYEVO_ENV = $previousEnvironment
    Pop-Location
}
