import { resolveApiBase } from './apiBase'

const API_BASE = resolveApiBase(window.MONITOR_API_BASE, import.meta.env.DEV)
const ACCESS_TOKEN_KEY = 'monitor_access_token'
const REFRESH_TOKEN_KEY = 'monitor_refresh_token'
const USER_KEY = 'monitor_user'
let unauthorizedHandler = null
let refreshInFlight = null

export function getAccessToken() {
  return localStorage.getItem(ACCESS_TOKEN_KEY) || ''
}

export function getRefreshToken() {
  return localStorage.getItem(REFRESH_TOKEN_KEY) || ''
}

export function getStoredUser() {
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

export function saveAuth(data) {
  if (data?.access_token) localStorage.setItem(ACCESS_TOKEN_KEY, data.access_token)
  if (data?.refresh_token) localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh_token)
  if (data?.user) localStorage.setItem(USER_KEY, JSON.stringify(data.user))
}

export function clearAuth() {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = handler
}

export function handleUnauthorized() {
  clearAuth()
  unauthorizedHandler?.()
}

async function refreshAccessToken() {
  const refreshToken = getRefreshToken()
  if (!refreshToken) return false
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const response = await fetch(`${API_BASE}/api/auth/refresh`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Refresh-Token': refreshToken,
          },
        })
        const data = await response.json().catch(() => ({}))
        if (!response.ok || !data.access_token || !data.refresh_token) return false
        saveAuth(data)
        return true
      } catch {
        return false
      } finally {
        refreshInFlight = null
      }
    })()
  }
  return refreshInFlight
}

export function useApi() {
  const apiUrl = (path) => `${API_BASE}${path}`

  const mediaUrl = (path) => {
    if (!path) return ''
    if (path.startsWith('http')) return path
    const url = `${API_BASE}${path}`
    if (!path.startsWith('/event_crops/')) return url
    const token = getAccessToken()
    if (!token) return url
    return `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(token)}`
  }

  const requestJson = async (path, options = {}) => {
    const send = async () => {
      const token = getAccessToken()
      const headers = {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options.headers || {}),
      }
      return fetch(apiUrl(path), { ...options, headers })
    }
    let response = await send()
    const shouldRefresh = response.status === 401
      && !options.skipAuthRefresh
      && !path.startsWith('/api/auth/')
    if (shouldRefresh && await refreshAccessToken()) {
      response = await send()
    }
    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
      if (response.status === 401 && !path.startsWith('/api/auth/')) handleUnauthorized()
      const error = new Error(data.detail || data.message || '请求失败')
      error.status = response.status
      throw error
    }
    return data
  }

  return { API_BASE, apiUrl, mediaUrl, requestJson, saveAuth, clearAuth, getStoredUser, getAccessToken, getRefreshToken }
}
