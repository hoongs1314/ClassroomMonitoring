import { resolveApiBase } from './apiBase'

const API_BASE = resolveApiBase(window.MONITOR_API_BASE, import.meta.env.DEV)
const ACCESS_TOKEN_KEY = 'monitor_access_token'
const REFRESH_TOKEN_KEY = 'monitor_refresh_token'
const USER_KEY = 'monitor_user'

export function getAccessToken() {
  return localStorage.getItem(ACCESS_TOKEN_KEY) || ''
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

export function useApi() {
  const apiUrl = (path) => `${API_BASE}${path}`

  const mediaUrl = (path) => {
    if (!path) return ''
    if (path.startsWith('http')) return path
    return `${API_BASE}${path}`
  }

  const requestJson = async (path, options = {}) => {
    const token = getAccessToken()
    const headers = {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    }
    const response = await fetch(apiUrl(path), {
      ...options,
      headers,
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
      if (response.status === 401) clearAuth()
      throw new Error(data.detail || data.message || '请求失败')
    }
    return data
  }

  return { API_BASE, apiUrl, mediaUrl, requestJson, saveAuth, clearAuth, getStoredUser, getAccessToken }
}
