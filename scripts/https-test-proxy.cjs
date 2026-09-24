// Test-only TLS termination, bound to loopback; never used as a deployment server.
const https = require('node:https')
const http = require('node:http')
const fs = require('node:fs')
const server = https.createServer({
  cert: fs.readFileSync(process.env.PSYEVO_TEST_TLS_CERT),
  key: fs.readFileSync(process.env.PSYEVO_TEST_TLS_KEY),
}, (request, response) => {
  const upstream = http.request({
    hostname: '127.0.0.1',
    port: request.url.startsWith('/api/v1/') ? process.env.PSYEVO_TEST_API_PORT : process.env.PSYEVO_TEST_WEB_PORT,
    path: request.url,
    method: request.method,
    headers: request.headers,
  }, (result) => {
    response.writeHead(result.statusCode, result.headers)
    result.pipe(response)
  })
  upstream.on('error', () => { response.writeHead(502); response.end() })
  request.pipe(upstream)
})
server.listen(Number(process.env.PSYEVO_TEST_TLS_PORT), '127.0.0.1')
