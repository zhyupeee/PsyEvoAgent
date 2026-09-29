param(
    [switch]$Initialize,
    [switch]$PrepareOnly,
    [switch]$LiveSupport = $true,
    [switch]$DisableSupport,
    [ValidateRange(1, 4096)][int]$MaxOutputTokens,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$BackendArgs
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$configPath = Join-Path $repo '.env.local.json'
$previousPassword = $env:PSYEVO_POSTGRES_PASSWORD
$previousDatabase = $env:PSYEVO_DATABASE_URL
$previousEnvironment = $env:PSYEVO_ENV
$previousSupport = $env:PSYEVO_SUPPORT_MODE
$previousProvider = @{}
Get-ChildItem Env:PSYEVO_PROVIDER_* | ForEach-Object { $previousProvider[$_.Name] = $_.Value }
$previousProbe = $env:PSYEVO_LIVE_PROBE_ENABLED
$previousOverride = $env:PSYEVO_OUTPUT_TOKEN_OVERRIDE

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
    if ($LiveSupport -and !$DisableSupport -and !$PrepareOnly) {
        $providerPath = Join-Path $repo '.env.step08.ps1'
        Get-ChildItem Env:PSYEVO_PROVIDER_* | ForEach-Object { Remove-Item -LiteralPath "Env:$($_.Name)" }
        if (Test-Path -LiteralPath $providerPath) { & { . $providerPath } *> $null }
        $env:PSYEVO_PROVIDER_CONFIG_FILE = $providerPath
        $env:PSYEVO_OUTPUT_TOKEN_OVERRIDE = $null
        if ($PSBoundParameters.ContainsKey('MaxOutputTokens')) {
            $env:PSYEVO_OUTPUT_TOKEN_OVERRIDE = [string]$MaxOutputTokens
            $env:PSYEVO_PROVIDER_MAX_OUTPUT_TOKENS = [string]$MaxOutputTokens
            Write-Host 'Explicit -MaxOutputTokens overrides the configuration file.'
        }
        $env:PSYEVO_SUPPORT_MODE = 'live'
    } else {
        $env:PSYEVO_SUPPORT_MODE = 'disabled'
        $env:PSYEVO_PROVIDER_CONFIG_FILE = $null
    }
    & docker compose -p psyevoagent up -d --wait --wait-timeout 120 postgres
    if ($LASTEXITCODE -ne 0) { throw 'Development PostgreSQL failed to start; check Docker and port 55432.' }
    Push-Location (Join-Path $repo 'backend')
    try {
        # Migration exceptions may include connection details: never print raw output.
        $ErrorActionPreference = 'Continue'
        $migrationSupport = $env:PSYEVO_SUPPORT_MODE
        $env:PSYEVO_SUPPORT_MODE = 'disabled'
        try { $migrationOutput = & uv run --no-sync alembic upgrade head 2>&1 }
        finally { $ErrorActionPreference = 'Stop'; $env:PSYEVO_SUPPORT_MODE = $migrationSupport }
        if ($LASTEXITCODE -ne 0) { throw 'Database migration failed. Check local credentials and database availability; no reset was performed.' }
        Write-Host 'Development database ready on 127.0.0.1:55432; migrations complete.'
        if (!$PrepareOnly) {
            if ($env:PSYEVO_SUPPORT_MODE -eq 'live') {
                $env:PSYEVO_SUPPORT_MODE = 'disabled'
                & uv run --no-sync python -m app.local_model_key
                if ($LASTEXITCODE -ne 0) { throw 'Encryption configuration unavailable; restore .env.local.json.' }
                $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
                $env:PSYEVO_PROVIDER_ENCRYPTION_KEY = $config.provider_encryption_key
                $env:PSYEVO_SUPPORT_MODE = 'live'
                & uv run --no-sync python -c 'from app.config import load_settings; load_settings()' *> $null
                if ($LASTEXITCODE -ne 0) { throw 'Live support configuration is invalid.' }
                Write-Host 'Live support enabled; API supervisor owns the independent Worker.'
                $BackendArgs = @('--support-worker') + $BackendArgs
            }
            & uv run --no-sync python -m app.dev @BackendArgs
            if ($LASTEXITCODE -ne 0) { throw 'Development API stopped with an error.' }
        }
    } finally { Pop-Location }
} finally {
    $env:PSYEVO_OUTPUT_TOKEN_OVERRIDE = $previousOverride
    $env:PSYEVO_SUPPORT_MODE = $previousSupport
    Get-ChildItem Env:PSYEVO_PROVIDER_* | ForEach-Object { Remove-Item -LiteralPath "Env:$($_.Name)" }
    foreach ($name in $previousProvider.Keys) { Set-Item -LiteralPath "Env:$name" -Value $previousProvider[$name] }
    $env:PSYEVO_LIVE_PROBE_ENABLED = $previousProbe
    $env:PSYEVO_POSTGRES_PASSWORD = $previousPassword
    $env:PSYEVO_DATABASE_URL = $previousDatabase
    $env:PSYEVO_ENV = $previousEnvironment
    Pop-Location
}
