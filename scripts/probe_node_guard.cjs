const assert = require('node:assert/strict')
const dns = require('node:dns')
const net = require('node:net')

// Run under the gate's NODE_OPTIONS preload; never attempt external traffic.
function resolverEntryPoints(target) {
  const names = new Set()
  for (
    let current = target;
    current && current !== Object.prototype;
    current = Object.getPrototypeOf(current)
  ) {
    for (const name of Object.getOwnPropertyNames(current)) names.add(name)
  }
  return [...names].filter(
    name =>
      name === 'lookup' ||
      name === 'lookupService' ||
      name === 'reverse' ||
      name.startsWith('resolve'),
  )
}
function argumentsFor(name, callback) {
  if (name === 'lookupService') return ['203.0.113.1', 443, ...(callback ? [callback] : [])]
  if (name === 'reverse') return ['203.0.113.1', ...(callback ? [callback] : [])]
  return ['external.invalid', ...(callback ? [callback] : [])]
}
function probeCallbackResolvers(target) {
  for (const name of resolverEntryPoints(target)) {
    assert.throws(() => target[name](...argumentsFor(name, () => {})), /Gate blocks/)
  }
}
async function probePromiseResolvers(target) {
  for (const name of resolverEntryPoints(target)) {
    await assert.rejects(target[name](...argumentsFor(name)), /Gate blocks/)
  }
}
async function main() {
  probeCallbackResolvers(dns)
  probeCallbackResolvers(new dns.Resolver())
  await probePromiseResolvers(dns.promises)
  await probePromiseResolvers(new dns.promises.Resolver())
  const esmDns = await import('node:dns')
  assert.throws(() => esmDns.resolveMx('external.invalid', () => {}), /Gate blocks/)
  const esmDnsPromises = await import('node:dns/promises')
  await assert.rejects(esmDnsPromises.resolveTxt('external.invalid'), /Gate blocks/)

  const server = net.createServer(socket => socket.end())
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  const port = server.address().port
  try {
    for (const connect of [
      (...args) => new net.Socket().connect(...args),
      net.connect,
      net.createConnection,
    ]) {
      for (const args of [
        [port, '127.0.0.2'],
        [String(port), '127.0.0.2'],
        [String(port), '127.0.0.2', () => {}],
        [{ port: String(port), host: '127.0.0.2' }],
      ]) {
        assert.throws(() => connect(...args), /Gate blocks/)
      }
      for (const args of [[port, '127.0.0.1'], [String(port), '127.0.0.1']]) {
        await new Promise((resolve, reject) => {
          const socket = connect(...args)
          socket.on('error', reject)
          socket.on('connect', () => socket.end())
          socket.on('close', resolve)
        })
      }
    }
    console.log('Node TCP and DNS guard probes passed')
  } finally {
    await new Promise(resolve => server.close(resolve))
  }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
