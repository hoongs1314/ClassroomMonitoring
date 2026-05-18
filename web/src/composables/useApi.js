const API_BASE = window.MONITOR_API_BASE || 'http://localhost:8997'

export function useApi() {
  const apiUrl = (path) => `${API_BASE}${path}`

  const mediaUrl = (path) => {
    if (!path) return ''
    if (path.startsWith('http')) return path
    return `${API_BASE}${path}`
  }

  const requestJson = async (path, options = {}) => {
    const response = await fetch(apiUrl(path), {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new Error(data.detail || data.message || '请求失败')
    }
    return data
  }

  return { API_BASE, apiUrl, mediaUrl, requestJson }
}
