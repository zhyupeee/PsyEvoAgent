// Gate-only guard for Node TCP/UDP/DNS and built-in fetch (which uses TCP).
// This is not an OS sandbox for arbitrary untrusted/native subprocesses.
const net = require('node:net')
const dns = require('node:dns')
const dgram = require('node:dgram')
const { syncBuiltinESMExports } = require('node:module')
const allowed = new Set(['127.0.0.1', '::1', 'localhost'])
function check(host) {
  if (!allowed.has(host ?? 'localhost')) throw new Error('Gate blocks non-loopback network access')
}
const connect = net.Socket.prototype.connect
net.Socket.prototype.connect = function (...args) {
  // Use Node's normalization to include numeric-string ports and internal arrays.
  const [options] = Array.isArray(args[0]) ? args[0] : net._normalizeArgs(args)
  // Node and Playwright use local IPC pipes in addition to TCP.
  if (!options.path) check(options.host)
  return connect.apply(this, args)
}
function resolverEntryPoints(target) {
  return Object.getOwnPropertyNames(target).filter(
    name =>
      name === 'lookup' ||
      name === 'lookupService' ||
      name === 'reverse' ||
      name.startsWith('resolve'),
  )
}
function guardResolvers(target, asPromise = false) {
  for (const name of resolverEntryPoints(target)) {
    const original = target[name]
    target[name] = asPromise
      ? async function (host, ...args) {
          check(host)
          return original.call(this, host, ...args)
        }
      : function (host, ...args) {
          check(host)
          return original.call(this, host, ...args)
        }
  }
}
guardResolvers(dns)
guardResolvers(dns.promises, true)
guardResolvers(dns.Resolver.prototype)
guardResolvers(dns.promises.Resolver.prototype, true)
syncBuiltinESMExports()
dgram.Socket.prototype.send = function () { throw new Error('Gate blocks UDP') }
