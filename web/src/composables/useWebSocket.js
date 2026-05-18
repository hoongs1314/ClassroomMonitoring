import { shallowRef, ref, onMounted, onUnmounted } from 'vue'

const status = shallowRef(null)
const isConnected = ref(false)
const error = ref(null)
const eventLog = ref([])

let ws = null
let reconnectTimer = null
let reconnectAttempts = 0
let activeUsers = 0
const MAX_RECONNECT_DELAY = 30000

function getWsUrl() {
  const API_BASE = window.MONITOR_API_BASE || 'http://localhost:8997'
  return `${API_BASE.replace(/^http/, 'ws')}/ws`
}

function scheduleReconnect(connectFn) {
  if (reconnectTimer) return
  const delay = Math.min(1000 * 2 ** reconnectAttempts, MAX_RECONNECT_DELAY)
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    connectFn()
  }, delay)
}

export function useWebSocket() {
  const connect = () => {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      return
    }

    error.value = null
    const url = getWsUrl()

    try {
      ws = new WebSocket(url)
    } catch (e) {
      error.value = 'WebSocket 连接失败'
      scheduleReconnect(connect)
      return
    }

    ws.onopen = () => {
      isConnected.value = true
      reconnectAttempts = 0
      error.value = null
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        status.value = data

        if (data.events && Array.isArray(data.events)) {
          for (const e of data.events) {
            const eid = e.event_id || e.id
            if (eid) {
              const exists = eventLog.value.some(
                (existing) => (existing.event_id || existing.id) === eid
              )
              if (exists) continue
            }
            eventLog.value.push({ ...e, _receivedAt: Date.now() })
          }
          if (eventLog.value.length > 1000) {
            eventLog.value = eventLog.value.slice(-500)
          }
        }
      } catch {
        // 忽略解析错误
      }
    }

    ws.onclose = () => {
      isConnected.value = false
      ws = null
      if (activeUsers > 0) {
        reconnectAttempts++
        scheduleReconnect(connect)
      }
    }

    ws.onerror = () => {
      // onclose 会随后触发，在那里处理重连
    }
  }

  const disconnect = () => {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (ws) {
      ws.onclose = null // 阻止重连
      ws.close()
      ws = null
    }
    isConnected.value = false
  }

  onMounted(() => {
    activeUsers++
    if (activeUsers === 1) {
      connect()
    }
  })

  onUnmounted(() => {
    activeUsers--
    if (activeUsers <= 0) {
      activeUsers = 0
      disconnect()
    }
  })

  return { status, isConnected, error, eventLog, connect, disconnect }
}
