<script setup>
import { ref, watch } from 'vue'
import { useApi } from '@/composables/useApi'

const props = defineProps({
  open: Boolean,
  eventId: [Number, String],
  eventData: { type: Object, default: null },
})

const emit = defineEmits(['update:open', 'close'])

const { mediaUrl, requestJson } = useApi()

const loading = ref(false)
const fetchedData = ref(null)

watch(() => props.open, (val) => {
  if (!val) {
    fetchedData.value = null
  }
})

watch([() => props.open, () => props.eventData, () => props.eventId], async ([isOpen, inlineData, id]) => {
  if (!isOpen) return
  if (inlineData) {
    fetchedData.value = inlineData
    loading.value = false
    return
  }
  if (!id) return
  loading.value = true
  try {
    fetchedData.value = await requestJson(`/api/events/${id}`)
  } catch {
    fetchedData.value = null
  } finally {
    loading.value = false
  }
}, { immediate: true })

const levelColor = (level) => {
  if (level === 'STRONG') return 'red'
  if (level === 'WEAK') return 'gold'
  if (level === 'NORMAL') return 'green'
  return 'default'
}

const statusText = (v) => {
  const map = {
    DESK_LYING: '疑似趴桌',
    HEAD_DOWN: '疑似低头',
    NORMAL: '正常',
    UNCERTAIN: '无法确定',
    EMPTY: '空位',
    STRONG: '明显异常',
    WEAK: '轻度异常',
    INVALID: '关键点不足',
  }
  return map[v] || v || '-'
}

const statusColor = (v) => (v === 'DESK_LYING' ? 'red' : 'blue')

const formatRatio = (v) => (v != null ? Number(v).toFixed(4) : '-')
</script>

<template>
  <a-modal
    :open="open"
    :footer="null"
    width="1100px"
    centered
    destroyOnClose
    @cancel="emit('update:open', false)"
  >
    <template #title>
      <span v-if="fetchedData">{{ fetchedData.list_title || fetchedData.label || '异常详情' }}</span>
      <span v-else>异常详情</span>
    </template>

    <div v-if="loading" class="detail-loading">
      <div class="loading-shimmer"></div>
    </div>

    <template v-else-if="fetchedData">
      <div class="detail-shell">
        <div class="detail-top">
          <div>
            <h3 class="detail-seat">{{ fetchedData.seat_name || fetchedData.seat || '-' }}</h3>
            <p class="detail-summary">{{ fetchedData.summary_text || fetchedData.reason || '-' }}</p>
          </div>
          <a-tag :color="statusColor(fetchedData.status)">
            {{ fetchedData.label || statusText(fetchedData.status) }}
          </a-tag>
        </div>

        <div class="detail-cards">
          <div class="info-card">
            <div class="info-label">座位号</div>
            <div class="info-value">{{ fetchedData.seat_name || fetchedData.seat || '-' }}</div>
          </div>
          <div class="info-card">
            <div class="info-label">开始时间</div>
            <div class="info-value">{{ fetchedData.alert_start_time || fetchedData.start_time }}</div>
          </div>
          <div class="info-card">
            <div class="info-label">结束时间</div>
            <div class="info-value">{{ fetchedData.end_time || '-' }}</div>
          </div>
          <div class="info-card">
            <div class="info-label">持续秒数</div>
            <div class="info-value">{{ fetchedData.duration_seconds ?? '-' }}</div>
          </div>
          <div class="info-card">
            <div class="info-label">峰值比例</div>
            <div class="info-value">{{ formatRatio(fetchedData.peak_ratio) }}</div>
          </div>
        </div>

        <div v-if="fetchedData.frames && fetchedData.frames.length" class="frame-grid">
          <article
            v-for="frame in fetchedData.frames"
            :key="frame.frame_index + '-' + (frame.seat?.seat_id || '')"
            class="frame-card"
          >
            <div v-if="frame.focus_image_url" class="frame-image">
              <img :src="mediaUrl(frame.focus_image_url)" alt="seat-focus" />
            </div>
            <div class="frame-info">
              <div class="frame-top">
                <strong>第 {{ frame.frame_index }} 帧</strong>
                <a-tag :color="levelColor(frame.seat?.status)">
                  {{ frame.seat?.status_text || statusText(frame.seat?.status) }}
                </a-tag>
              </div>
              <div class="frame-meta">
                <div>时间: {{ frame.time }}</div>
                <div>座位: {{ frame.seat?.seat_name }}</div>
                <div>比例: {{ formatRatio(frame.seat?.ratio) }}</div>
                <div>置信度: {{ frame.seat?.box_conf ?? '-' }}</div>
              </div>
            </div>
          </article>
        </div>

        <div v-else class="no-frames">暂无帧详情</div>
      </div>
    </template>

    <div v-else class="no-data">事件详情暂时不可用</div>
  </a-modal>
</template>

<style scoped>
.detail-loading {
  min-height: 380px;
  display: flex;
}
.loading-shimmer {
  flex: 1;
  border-radius: var(--radius-lg);
  background: linear-gradient(90deg, var(--bg-elevated) 25%, var(--bg-card-hover) 50%, var(--bg-elevated) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.2s ease-in-out infinite;
}
@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.detail-shell {
  max-height: 72vh;
  overflow: auto;
  padding-right: 4px;
}

.detail-top {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}
.detail-seat {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
}
.detail-summary {
  margin-top: 6px;
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.detail-cards {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 10px;
  margin-top: 16px;
}
.info-card {
  padding: 12px 14px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-elevated);
}
.info-label {
  font-size: 12px;
  color: var(--text-muted);
}
.info-value {
  margin-top: 6px;
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  font-family: var(--font-mono);
}

.frame-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  margin-top: 20px;
}
.frame-card {
  overflow: hidden;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-elevated);
}
.frame-image {
  width: 100%;
  aspect-ratio: 16 / 10;
  background: var(--bg-primary);
}
.frame-image img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.frame-info {
  padding: 10px 12px;
}
.frame-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
.frame-meta {
  margin-top: 6px;
  display: grid;
  gap: 2px;
  font-size: 12px;
  color: var(--text-secondary);
}
.frame-meta b {
  color: var(--text-primary);
  font-weight: 600;
}

.no-frames,
.no-data {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 160px;
  color: var(--text-muted);
}

@media (max-width: 820px) {
  .detail-cards { grid-template-columns: repeat(2, 1fr); }
  .frame-grid { grid-template-columns: 1fr 1fr; }
}
</style>
