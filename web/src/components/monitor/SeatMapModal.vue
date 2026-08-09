<script setup>
import { computed } from 'vue'
import { useApi } from '@/composables/useApi'

const props = defineProps({
  open: Boolean,
  seatMapUrl: String,
  currentClass: { type: String, default: '' },
  seats: { type: Array, default: () => [] },
  imgW: { type: Number, default: 1920 },
  imgH: { type: Number, default: 1080 },
})

const emit = defineEmits(['update:open'])

const { mediaUrl } = useApi()

const statusMap = {
  NORMAL: { c: '#22C55E', t: '正常' },
  HEAD_DOWN: { c: '#F59E0B', t: '提醒' },
  DESK_LYING: { c: '#EF4444', t: '异常' },
  UNCERTAIN: { c: '#64748B', t: '模糊' },
  SUSPECTED: { c: '#0b90f5', t: '疑似' },
}
const getS = (s) => statusMap[s] || statusMap.NORMAL

const frameUrl = computed(() => {
  const cacheKey = [props.currentClass, props.open, props.imgW, props.imgH, props.seats.length].join('-')
  const params = new URLSearchParams({
    class: props.currentClass,
    v: cacheKey,
    t: String(Date.now()),
  })
	return `${mediaUrl('/api/latest_frame')}?${params.toString()}`
})

function boxStyle(box) {
  if (!box || !props.imgW) return { display: 'none' }
  return {
    left: `${(box[0] / props.imgW) * 100}%`,
    top: `${(box[1] / props.imgH) * 100}%`,
    width: `${((box[2] - box[0]) / props.imgW) * 100}%`,
    height: `${((box[3] - box[1]) / props.imgH) * 100}%`,
  }
}
</script>

<template>
  <a-modal
    :open="open"
    :footer="null"
    width="1100px"
    centered
    destroyOnClose
    title="整体课堂识别"
    @cancel="emit('update:open', false)"
  >
    <div v-if="seatMapUrl" class="seat-map-wrap">
      <img :src="mediaUrl(seatMapUrl)" alt="当前课堂识别" class="seat-map-img" />
    </div>
    <div v-else-if="seats.length" class="seat-grid-wrap">
      <p class="seat-grid-hint">整体课堂检测图</p>
      <div class="seat-viewport" :style="{ aspectRatio: `${imgW}/${imgH}` }">
        <img
          :src="frameUrl"
          alt="教室画面"
          class="seat-frame-bg"
        />
        <div
          v-for="s in seats"
          :key="s.seat_id"
          class="seat-rect"
          :style="[boxStyle(s.box), { borderColor: getS(s.status).c }]"
        >
          <span class="seat-label" :style="{ background: getS(s.status).c }">
            {{ s.seat_code }}
          </span>
        </div>
      </div>
      <div class="seat-legend">
        <span v-for="(v, k) in statusMap" :key="k" class="legend-item">
          <span class="legend-dot" :style="{ background: v.c }"></span>
          {{ v.t }}
        </span>
      </div>
    </div>
    <div v-else class="seat-map-empty">
      请先启动监控，等待座位检测完成
    </div>
  </a-modal>
</template>

<style scoped>
.seat-map-wrap {
  width: 100%;
  max-height: 74vh;
  overflow: auto;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-primary);
}
.seat-map-img {
  display: block;
  width: 100%;
  height: auto;
  object-fit: contain;
}

.seat-grid-wrap {
  width: 100%;
  max-height: 74vh;
  overflow: auto;
}
.seat-grid-hint {
  color: var(--text-muted);
  font-size: 13px;
  margin-bottom: 12px;
}
.seat-viewport {
  position: relative;
  width: 100%;
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  overflow: hidden;
}
.seat-frame-bg {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.seat-rect {
  position: absolute;
  border: 2px solid var(--color-primary);
  background: rgba(59, 130, 246, 0.06);
}
.seat-label {
  position: absolute;
  top: -20px;
  left: -2px;
  padding: 0 6px;
  height: 18px;
  line-height: 18px;
  font-size: 11px;
  font-weight: 700;
  color: #fff;
  border-radius: 4px 4px 0 0;
  white-space: nowrap;
}
.seat-legend {
  display: flex;
  gap: 16px;
  margin-top: 12px;
  flex-wrap: wrap;
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-secondary);
}
.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 2px;
}

.seat-map-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: var(--text-muted);
}
</style>
