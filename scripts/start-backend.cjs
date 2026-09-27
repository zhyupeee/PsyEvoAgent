const { spawnSync } = require('node:child_process')
const path = require('node:path')

function startBackend({
  platform = process.platform,
  env = process.env,
  args = process.argv.slice(2),
  spawn = spawnSync,
  report = console.error,
} = {}) {
  const repo = path.resolve(__dirname, '..')
  let command = 'uv'
  let commandArgs = ['run', '--no-sync', 'python', '-m', 'app.dev', ...args]
  let cwd = path.join(repo, 'backend')

  if (!env.PSYEVO_DATABASE_URL) {
    if (
      platform !== 'win32' ||
      (env.PSYEVO_ENV && env.PSYEVO_ENV !== 'development')
    ) {
      report(
        'Missing PSYEVO_DATABASE_URL. Set it as described in DEVELOPMENT.md.',
      )
      return 1
    }
    command = 'powershell.exe'
    commandArgs = [
      '-NoProfile',
      '-File',
      path.join(repo, 'scripts', 'start-dev.ps1'),
      ...args,
    ]
    cwd = repo
  }

  const result = spawn(command, commandArgs, { cwd, env, stdio: 'inherit' })
  if (result.error) {
    report(
      `Unable to start ${command}. Check that it is installed and available on PATH.`,
    )
    return 1
  }
  return result.status ?? 1
}

if (require.main === module) process.exitCode = startBackend()

module.exports = { startBackend }
