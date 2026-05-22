<script setup>
import { ref, computed } from 'vue'
import { BulbOutlined, SafetyCertificateOutlined } from '@ant-design/icons-vue'
import { useApi } from '@/composables/useApi'

const props = defineProps({
  events: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  counts: { type: Object, default: () => ({ total: 0, focus: 0, normal: 0 }) },
})

const emit = defineEmits(['select'])

const { mediaUrl } = useApi()

const filterStatus = ref('')

const filteredEvents = computed(() => {
  if (!filterStatus.value) return props.events
  return props.events.filter((e) => e.status === filterStatus.value)
})

const totalCount = computed(() => props.events.length)
const deskLyingCount = computed(() => props.events.filter((e) => e.status === 'DESK_LYING').length)
const headDownCount = computed(() => props.events.filter((e) => e.status === 'HEAD_DOWN').length)

const statusColor = (status) => (status === 'DESK_LYING' ? 'red' : 'blue')

function getEventId(e) {
  return e.event_id || e.id
}

function getLabel(e) {
  if (e.label) return e.label
  if (e.status === 'DESK_LYING') return '疑似趴桌'
  if (e.status === 'HEAD_DOWN') return '疑似低头'
  return e.list_title || '异常行为'
}

function getSeatName(e) {
  return e.seat_name || e.seat || '-'
}
</script>

<template>
  <div class="event-list">
    <div class="filter-bar">
      <a-radio-group v-model:value="filterStatus" size="small" button-style="solid">
        <a-radio-button value="">全部 ({{ totalCount }})</a-radio-button>
        <a-radio-button value="DESK_LYING">趴桌 ({{ deskLyingCount }})</a-radio-button>
        <a-radio-button value="HEAD_DOWN">低头 ({{ headDownCount }})</a-radio-button>
      </a-radio-group>
    </div>

    <div v-if="loading" class="event-items">
      <div v-for="i in 3" :key="i" class="event-skeleton"></div>
    </div>

    <div v-else-if="filteredEvents.length" class="event-items" role="listbox">
      <article
        v-for="item in filteredEvents"
        :key="getEventId(item)"
        class="event-card"
        role="option"
        tabindex="0"
        @click="emit('select', getEventId(item))"
        @keydown.enter="emit('select', getEventId(item))"
      >
        <div v-if="item.list_image_url || item.url" class="event-image">
          <img
            :src="mediaUrl(item.list_image_url || item.url)"
            :alt="getLabel(item)"
          />
          <span class="event-time">{{
            item.alert_start_time || item.time || ''
          }}</span>
        </div>

        <div class="event-body">
          <div class="event-seat">座位：{{ getSeatName(item) }}</div>
          <div class="event-action">
            行为：<strong>{{ getLabel(item) }}</strong>
          </div>
        </div>

        <a-tag :color="statusColor(item.status)">
          {{ getLabel(item) }}
        </a-tag>
      </article>
    </div>

    <div v-else class="event-empty">
      <SafetyCertificateOutlined class="empty-icon" />
      <p>暂无异常事件</p>
    </div>
  </div>
</template>

<style scoped>
.event-list {
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1;
}

.filter-bar {
  margin-bottom: 12px;
  flex-shrink: 0;
}

.event-items {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-right: 2px;
}

.event-card {
  display: grid;
  grid-template-columns: 120px minmax(0, 1fr) auto;
  align-items: center;
  gap: 14px;
  padding: 10px 12px 10px 10px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-elevated);
  cursor: pointer;
  transition: transform var(--duration-fast) var(--ease-out),
    box-shadow var(--duration-fast) var(--ease-out),
    border-color var(--duration-fast) var(--ease-out);
}
.event-card:hover,
.event-card:focus-visible {
  transform: translateY(-1px);
  border-color: var(--border-hover);
  box-shadow: var(--shadow-glow-primary);
}

.event-image {
  position: relative;
  width: 120px;
  height: 68px;
  border-radius: 6px;
  overflow: hidden;
  background: var(--bg-primary);
}
.event-image img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.event-time {
  position: absolute;
  right: 4px;
  bottom: 4px;
  padding: 1px 5px;
  border-radius: 3px;
  background: rgba(0,0,0,0.65);
  color: #fff;
  font-size: 11px;
  font-weight: 600;
}

.event-body {
  min-width: 0;
}
.event-seat,
.event-action {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.7;
}
.event-action strong {
  color: var(--color-danger);
  font-weight: 700;
}

.event-skeleton {
  height: 88px;
  border-radius: var(--radius-md);
  background: linear-gradient(90deg, var(--bg-elevated) 25%, var(--bg-card-hover) 50%, var(--bg-elevated) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.2s ease-in-out infinite;
}
@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.event-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 180px;
  border: 1px dashed var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-muted);
}
.empty-icon {
  font-size: 40px;
  opacity: 0.3;
  margin-bottom: 10px;
}
</style>
