const DEVELOPMENT_API_BASE = 'http://localhost:8997'

export function resolveApiBase(configuredBase, isDevelopment) {
  const normalizedBase = String(configuredBase || '').trim().replace(/\/+$/, '')
  if (normalizedBase) return normalizedBase
  return isDevelopment ? DEVELOPMENT_API_BASE : ''
}

export function resolveWebSocketBase(apiBase, browserOrigin) {
  const base = (apiBase || browserOrigin || '').replace(/\/+$/, '')
  return base.replace(/^http/i, 'ws')
}
