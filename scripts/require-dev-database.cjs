if (!process.env.PSYEVO_DATABASE_URL) {
  console.error(
    'Missing PSYEVO_DATABASE_URL. On Windows, run powershell -NoProfile -File scripts/start-dev.ps1 from the repository root. On WSL, set the variable as described in DEVELOPMENT.md.',
  )
  process.exit(1)
}
