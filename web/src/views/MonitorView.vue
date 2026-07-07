<script setup>
import { ref, computed, watch } from 'vue'
import { message } from 'ant-design-vue'
import {
  DesktopOutlined,
  DashboardOutlined,
  BulbOutlined,
  TeamOutlined,
  AlertOutlined,
  BellOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons-vue'
import { useWebSocket } from '@/composables/useWebSocket'
import { getStoredUser, useApi } from '@/composables/useApi'
import VideoPlayer from '@/components/monitor/VideoPlayer.vue'
import StatsCard from '@/components/monitor/StatsCard.vue'
import EventList from '@/components/monitor/EventList.vue'
import SeatMapModal from '@/components/monitor/SeatMapModal.vue'

const { status, isConnected } = useWebSocket()
const { requestJson } = useApi()

const props = defineProps({
  currentClass: { type: String, default: '' },
  currentClassCode: { type: String, default: '' },
})

const starting = ref(false)
const monitorStarted = ref(false)
const showSeatMap = ref(false)

watch(() => status.value?.is_running, (val) => {
  if (val != null) monitorStarted.value = val
})

const counts = computed(() => status.value?.counts || { total: 0, focus: 0, normal: 0 })

function statusLabel(statusCode) {
  const map = {
    HEAD_DOWN: '疑似低头',
    DESK_LYING: '疑似睡觉',
    TURNING_HEAD: '疑似转头',
    EATING: '疑似吃东西',
    UNCERTAIN: '无法确定',
    EMPTY: '未看到可分析学生',
    NORMAL: '正常或未见明显异常',
  }
  return map[statusCode] || '异常行为'
}

const events = computed(() => {
  const raw = status.value?.events || []
  return raw.map((e) => {
    return {
      ...e,
      event_id: e.event_id || e.id,
      list_image_url: e.list_image_url || e.url,
      seat_name: e.seat_name || e.seat || '-',
      list_title: e.list_title || e.label || statusLabel(e.status),
      alert_start_time: e.alert_start_time || e.time,
      source: e.source || e.analysis_source || '-',
      analysis_source: e.analysis_source || e.source || '-',
    }
  })
})

const phaseText = computed(() => {
  if (!status.value) return '-'
  const map = {
    init: '正在建立座位图',
    monitor: '正在监控',
    done: '监控完成',
    error: '运行失败',
  }
  return map[status.value.phase] || (status.value.is_running ? '正在监控' : '待启动')
})

const phaseType = computed(() => {
  if (!status.value) return ''
  if (status.value.phase === 'error') return 'danger'
  if (status.value.phase === 'monitor' || status.value.is_running) return 'success'
  if (status.value.phase === 'init') return 'warning'
  return ''
})

const seatMapUrl = computed(() => status.value?.seat_map_url || '')

const imgSize = computed(() => ({
  w: status.value?.img_w || 1920,
  h: status.value?.img_h || 1080,
}))

const seats = computed(() => status.value?.seats || [])

function encodeHeaderText(value) {
  return encodeURIComponent(value || '')
}

async function startMonitor() {
  starting.value = true
  try {
    const user = getStoredUser()
    const className = props.currentClass || status.value?.current_class || ''
    const headers = {
      ...(props.currentClassCode ? { 'X-Class-Code': props.currentClassCode } : {}),
      ...(!props.currentClassCode && className ? { 'X-Class-Name': encodeHeaderText(className) } : {}),
      ...(user?.teacher?.id ? { 'X-Teacher-Id': String(user.teacher.id) } : {}),
      'X-Operator-Name': encodeHeaderText(user?.real_name || user?.username || ''),
      ...(user?.id ? { 'X-Operator-User-Id': String(user.id) } : {}),
    }
    let result
    try {
      result = await requestJson('/api/start', { method: 'POST', headers })
    } catch {
      result = await requestJson('/api/monitor/start', { method: 'POST', headers })
    }
    monitorStarted.value = true
    message.success(result?.message || '监控已启动')
  } catch (error) {
    message.error(error.message || '启动失败')
  } finally {
    starting.value = false
  }
}

async function stopMonitor() {
  try {
    try {
      await requestJson('/api/stop', { method: 'POST' })
    } catch {
      await requestJson('/api/monitor/stop', { method: 'POST' })
    }
  } catch {
    // ignore
  }
  monitorStarted.value = false
  message.success('监控已停止')
}

function openSeatMap() {
  showSeatMap.value = true
}
</script>

<template>
  <div class="monitor-view">
    <!-- 顶部状态栏 -->
    <header class="topbar">
      <div class="brand">
        <div class="brand-icon">
          <SafetyCertificateOutlined />
        </div>
        <div>
          <h1 class="brand-title">课堂异常行为监测系统</h1>
          <p class="brand-subtitle">AI 智能识别 · 实时预警 · 规范课堂秩序</p>
        </div>
      </div>

      <div class="top-actions">
        <a-badge
          :status="isConnected ? 'success' : 'error'"
          :text="isConnected ? '已连接' : '未连接'"
        />
        <a-tag v-if="phaseText !== '-'" :color="phaseType || 'default'">
          {{ phaseText }}
        </a-tag>
        <a-button v-if="!monitorStarted && !status?.is_running" type="primary" :loading="starting" @click="startMonitor">
          启动监控
        </a-button>
        <a-button v-else danger @click="stopMonitor">停止监控</a-button>
      </div>
    </header>

    <!-- 主网格 -->
    <main class="main-grid">
      <!-- 左：视频 -->
      <section class="panel video-panel">
        <div class="panel-bar">
          <h2 class="panel-title">
            <span class="title-icon"><DesktopOutlined /></span>
            主监控画面
          </h2>
          <span class="panel-time">{{ status?.current_time || status?.time || '--:--:--' }}</span>
        </div>

        <VideoPlayer
          mode="mjpeg"
          mjpeg-url="/video_feed"
          :live="monitorStarted"
          :img-w="imgSize.w"
          :img-h="imgSize.h"
          :seats="seats"
        />
      </section>

      <!-- 右：统计 + 事件 -->
      <aside class="side-rail">
        <section class="panel stats-panel">
          <div class="panel-bar">
            <h2 class="panel-title">
              <span class="title-icon"><DashboardOutlined /></span>
              实时统计
            </h2>
          </div>
          <div class="stats-grid">
            <StatsCard
              :label="'学生人数'"
              :value="counts.total"
              type="primary"
              :icon="TeamOutlined"
clickable
              @click="openSeatMap"
            />
            <StatsCard
              :label="'警告'"
              :value="counts.focus"
              type="danger"
              :icon="AlertOutlined"
            />
            <StatsCard
              :label="'提示'"
              :value="counts.normal"
              type="warning"
              :icon="BellOutlined"
            />
          </div>
        </section>

        <section class="panel event-panel">
          <div class="panel-bar">
            <h2 class="panel-title">
              <span class="title-icon"><BulbOutlined /></span>
              异常行为通知
            </h2>
          </div>
          <EventList :events="events" />
        </section>
      </aside>
    </main>
    <SeatMapModal v-model:open="showSeatMap" :seat-map-url="seatMapUrl" :current-class="status?.current_class || ''" :seats="seats" :img-w="imgSize.w" :img-h="imgSize.h" />
  </div>
</template>

<style scoped>
.monitor-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 12px 20px;
  overflow: hidden;
}

/* === 顶栏 === */
.topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
  min-height: 72px;
  padding: 12px 24px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
  flex-shrink: 0;
  margin-bottom: 12px;
}
.brand {
  display: flex;
  align-items: center;
  gap: 16px;
  min-width: 0;
}
.brand-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 10px;
  background: linear-gradient(135deg, var(--color-primary), #1D4ED8);
  color: #fff;
  font-size: 20px;
  flex-shrink: 0;
}
.brand-title {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.2;
}
.brand-subtitle {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--text-muted);
  font-weight: 500;
}
.top-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}
.clock {
  font-family: var(--font-mono);
  font-size: 15px;
  font-weight: 600;
  color: var(--text-secondary);
  min-width: 80px;
}

/* === 主网格 === */
.main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.8fr) minmax(380px, 1fr);
  gap: 16px;
  flex: 1;
  min-height: 0;
}

.side-rail {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 12px;
  min-height: 0;
}

/* === 面板 === */
.panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 16px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
}

.panel-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 14px;
  margin-bottom: 12px;
  flex-shrink: 0;
}
.panel-title {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--color-primary);
}
.title-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--color-primary-soft);
  color: var(--color-primary);
  font-size: 16px;
}
.panel-time {
  font-family: var(--font-mono);
  font-size: 14px;
  color: var(--text-secondary);
  font-weight: 600;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.video-panel {
  flex: 1;
}

/* === 响应式 === */
@media (max-width: 1100px) {
  .main-grid {
    grid-template-columns: 1fr;
  }
  .side-rail {
    grid-template-rows: auto auto;
    max-height: none;
  }
}

@media (max-width: 768px) {
  .monitor-view {
    padding: 8px;
  }
  .topbar {
    padding: 12px 16px;
  }
  .brand-title {
    font-size: 18px;
  }
  .brand-subtitle {
    display: none;
  }
  .top-actions {
    flex-wrap: wrap;
    gap: 8px;
  }
  .stats-grid {
    grid-template-columns: 1fr;
  }
}
</style>
