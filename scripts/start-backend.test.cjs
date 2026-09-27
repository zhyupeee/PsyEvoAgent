const assert = require('node:assert/strict')
const path = require('node:path')
const { test } = require('node:test')
const { startBackend } = require('./start-backend.cjs')

test('a fresh Windows terminal uses the existing database preparation entry', () => {
  const calls = []
  assert.equal(
    startBackend({
      platform: 'win32',
      env: {},
      args: ['--port', '8127'],
      spawn: (...args) => {
        calls.push(args)
        return { status: 0 }
      },
    }),
    0,
  )
  const [command, args, options] = calls[0]
  assert.equal(command, 'powershell.exe')
  assert.deepEqual(args, [
    '-NoProfile',
    '-File',
    path.join(options.cwd, 'scripts', 'start-dev.ps1'),
    '--port',
    '8127',
  ])
  assert.equal(options.stdio, 'inherit')
  assert.equal(calls.length, 1)
})

for (const platform of ['win32', 'linux']) {
  test(`an explicit database on ${platform} is inherited without local preparation`, () => {
    const env = {
      PSYEVO_DATABASE_URL: 'synthetic-test-value',
      PSYEVO_ENV: 'test',
    }
    assert.equal(
      startBackend({
        platform,
        env,
        args: ['--stop-on-stdin-eof'],
        spawn: (command, args, options) => {
          assert.equal(command, 'uv')
          assert.deepEqual(args, [
            'run',
            '--no-sync',
            'python',
            '-m',
            'app.dev',
            '--stop-on-stdin-eof',
          ])
          assert.equal(options.env, env)
          assert.equal(path.basename(options.cwd), 'backend')
          return { status: 7 }
        },
      }),
      7,
    )
  })
}

for (const [platform, env] of [
  ['linux', {}],
  ['win32', { PSYEVO_ENV: 'test' }],
  ['win32', { PSYEVO_ENV: 'production' }],
]) {
  test(`missing configuration fails closed on ${platform} in ${env.PSYEVO_ENV || 'default'}`, () => {
    const messages = []
    assert.equal(
      startBackend({
        platform,
        env,
        args: [],
        spawn: () => assert.fail('must not launch or prepare a database'),
        report: (message) => messages.push(message),
      }),
      1,
    )
    assert.match(messages[0], /Missing PSYEVO_DATABASE_URL/)
  })
}

test('spawn failure is actionable and does not expose raw errors', () => {
  const messages = []
  assert.equal(
    startBackend({
      platform: 'win32',
      env: {},
      args: [],
      spawn: () => ({ error: new Error('private-value') }),
      report: (message) => messages.push(message),
    }),
    1,
  )
  assert.match(messages[0], /powershell.exe/)
  assert.doesNotMatch(messages[0], /private-value/)
})
