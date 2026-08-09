<script setup>
import { ref, watch, onMounted } from 'vue'

const props = defineProps({
  label: { type: String, required: true },
  value: { type: Number, default: 0 },
  type: { type: String, default: 'primary' },
  trend: { type: Number, default: null },
  icon: { type: [Object, Function], default: null },
  clickable: { type: Boolean, default: false },
})

const emit = defineEmits(['click'])

const displayValue = ref(0)
let animFrame = null

onMounted(() => {
  animateValue(0, props.value)
})

watch(() => props.value, (next, prev) => {
  animateValue(displayValue.value, next)
})

function animateValue(from, to) {
  if (animFrame) cancelAnimationFrame(animFrame)
  const duration = 400
  const start = performance.now()
  function step(now) {
    const elapsed = now - start
    const progress = Math.min(elapsed / duration, 1)
    const eased = 1 - Math.pow(1 - progress, 3)
    displayValue.value = Math.round(from + (to - from) * eased)
    if (progress < 1) {
      animFrame = requestAnimationFrame(step)
    }
  }
  animFrame = requestAnimationFrame(step)
}

const colorClass = {
  primary: 'card-primary',
  danger: 'card-danger',
  success: 'card-success',
  warning: 'card-warning',
}
</script>

<template>
  <article
    class="stats-card"
    :class="[colorClass[type] || 'card-primary', { clickable }]"
    role="status"
    :aria-label="`${label}: ${value}`"
    @click="emit('click')"
    @keydown.enter="emit('click')"
    :tabindex="clickable ? 0 : -1"
  >
    <div class="stats-head">
      <div class="stats-icon">
        <component :is="icon" v-if="icon" />
      </div>
      <span class="stats-label">{{ label }}</span>
    </div>
    <div class="stats-value">{{ displayValue }}</div>
    <div v-if="trend !== null" class="stats-trend" :class="trend >= 0 ? 'up' : 'down'">
      <span class="trend-arrow">{{ trend >= 0 ? '↑' : '↓' }}</span>
      {{ Math.abs(trend) }}
    </div>
  </article>
</template>

<style scoped>
.stats-card {
  position: relative;
  min-height: 118px;
  padding: 12px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border-default);
  background: var(--bg-card);
  overflow: hidden;
}
.stats-card.card-primary {
  border-color: rgba(59, 130, 246, 0.15);
  background: radial-gradient(circle at 100% 0, rgba(59, 130, 246, 0.1), transparent 40%), var(--bg-card);
}
.stats-card.card-danger {
  border-color: rgba(239, 68, 68, 0.15);
  background: radial-gradient(circle at 100% 0, rgba(239, 68, 68, 0.1), transparent 40%), var(--bg-card);
}
.stats-card.card-success {
  border-color: rgba(34, 197, 94, 0.15);
  background: radial-gradient(circle at 100% 0, rgba(34, 197, 94, 0.1), transparent 40%), var(--bg-card);
}
.stats-card.card-warning {
  border-color: rgba(245, 158, 11, 0.15);
  background: radial-gradient(circle at 100% 0, rgba(245, 158, 11, 0.1), transparent 40%), var(--bg-card);
}

.stats-card.clickable {
  cursor: pointer;
  transition: transform var(--duration-fast) var(--ease-out), box-shadow var(--duration-fast) var(--ease-out);
}
.stats-card.clickable:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-glow-primary);
}
.stats-card.clickable:focus-visible {
  border-color: var(--color-primary);
}

.stats-head {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 28px;
}
.stats-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--color-primary-soft);
  color: var(--color-primary);
  font-size: 15px;
}
.card-danger .stats-icon {
  background: var(--color-danger-soft);
  color: var(--color-danger);
}
.card-success .stats-icon {
  background: var(--color-success-soft);
  color: var(--color-success);
}
.card-warning .stats-icon {
  background: var(--color-warning-soft);
  color: var(--color-warning);
}

.stats-label {
  overflow: hidden;
  font-size: 12px;
  font-weight: 600;
  text-overflow: ellipsis;
  color: var(--text-secondary);
  white-space: nowrap;
}

.stats-value {
  margin-top: 10px;
  font-family: var(--font-mono);
  font-size: clamp(34px, 3vw, 46px);
  font-weight: 700;
  line-height: 1.1;
  color: var(--color-primary);
}
.card-danger .stats-value { color: var(--color-danger); }
.card-success .stats-value { color: var(--color-success); }
.card-warning .stats-value { color: var(--color-warning); }

.stats-trend {
  margin-top: 6px;
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 600;
}
.stats-trend.up { color: var(--color-success); }
.stats-trend.down { color: var(--color-danger); }
.trend-arrow {
  margin-right: 2px;
}
</style>
