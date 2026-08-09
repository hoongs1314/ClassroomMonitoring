const DEVELOPMENT_API_PORT = 8997

export function resolveApiBase(configuredBase, isDevelopment, browserLocation = null) {
	const normalizedBase = String(configuredBase || '').trim().replace(/\/+$/, '')
	if (normalizedBase) return normalizedBase
	if (!isDevelopment) return ''
	// 让 Vite 页面和 API 使用同一主机名，避免 localhost 与 127.0.0.1 被浏览器判定为跨站 Cookie。
	const protocol = browserLocation?.protocol || 'http:'
	const host = browserLocation?.hostname || 'localhost'
	return `${protocol}//${host}:${DEVELOPMENT_API_PORT}`
}

export function resolveWebSocketBase(apiBase, browserOrigin) {
  const base = (apiBase || browserOrigin || '').replace(/\/+$/, '')
  return base.replace(/^http/i, 'ws')
}
