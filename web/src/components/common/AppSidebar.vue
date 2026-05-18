<script setup>
import { ref, computed, onMounted } from 'vue'
import {
  TeamOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  VideoCameraFilled,
} from '@ant-design/icons-vue'
import { useWebSocket } from '@/composables/useWebSocket'
import { useApi } from '@/composables/useApi'

defineProps({
  collapsed: Boolean,
  currentClass: String,
})

const emit = defineEmits(['toggle', 'select-class'])

const { isConnected, status } = useWebSocket()
const { requestJson } = useApi()

const classList = ref([])
const activeClass = ref('')

onMounted(async () => {
  try {
    const data = await requestJson('/api/classes')
    classList.value = data.classes || []
    activeClass.value = data.current || classList.value[0] || ''
  } catch {
    classList.value = ['1班', '2班', '3班', '4班']
    activeClass.value = '1班'
  }
})

const currentClassName = computed(() => status.value?.current_class || activeClass.value)

function handleSelect(cls) {
  activeClass.value = cls
  emit('select-class', cls)
}
</script>

<template>
  <aside class="sidebar" :class="{ collapsed }">
    <div class="sidebar-logo">
      <div class="logo-icon">
        <VideoCameraFilled />
      </div>
      <span v-show="!collapsed" class="logo-text">课堂监测</span>
    </div>

    <div class="sidebar-section">
      <span v-show="!collapsed" class="section-label">监控班级</span>
      <a-menu
        :selected-keys="[currentClassName]"
        :inline-collapsed="collapsed"
        mode="inline"
        theme="dark"
        class="sidebar-menu"
        @click="({ key }) => handleSelect(key)"
      >
        <a-menu-item v-for="cls in classList" :key="cls">
          <template #icon><TeamOutlined /></template>
          <span>{{ cls }}</span>
        </a-menu-item>
      </a-menu>
    </div>

    <div class="sidebar-footer">
      <div class="status-row" :class="{ connected: isConnected }">
        <span class="status-dot"></span>
        <span v-show="!collapsed" class="status-text">
          {{ isConnected ? '已连接' : '未连接' }}
        </span>
      </div>
      <a-button
        type="text"
        class="toggle-btn"
        @click="emit('toggle')"
      >
        <MenuFoldOutlined v-if="!collapsed" />
        <MenuUnfoldOutlined v-else />
      </a-button>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  display: flex;
  flex-direction: column;
  width: var(--sidebar-width);
  height: 100%;
  background: var(--bg-sidebar);
  border-right: 1px solid var(--border-default);
  transition: width var(--duration-normal) var(--ease-out);
  overflow: hidden;
  flex-shrink: 0;
}
.sidebar.collapsed {
  width: var(--sidebar-collapsed-width);
}

.sidebar-logo {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 56px;
  padding: 0 16px;
  cursor: pointer;
  flex-shrink: 0;
}
.logo-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: linear-gradient(135deg, var(--color-primary), #1D4ED8);
  color: #fff;
  font-size: 16px;
  flex-shrink: 0;
}
.logo-text {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  white-space: nowrap;
}

.sidebar-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.section-label {
  padding: 8px 16px 0;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.sidebar-menu {
  flex: 1;
  padding-top: 4px;
  border-inline-end: none !important;
  overflow-y: auto;
}

.sidebar-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  border-top: 1px solid var(--border-default);
  flex-shrink: 0;
  min-height: 48px;
}

.status-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-danger);
  flex-shrink: 0;
}
.status-row.connected .status-dot {
  background: var(--color-success);
  box-shadow: 0 0 6px var(--color-success-glow);
}
.status-text {
  font-size: 12px;
  color: var(--text-muted);
  white-space: nowrap;
}

.toggle-btn {
  color: var(--text-muted) !important;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
}
.toggle-btn:hover {
  color: var(--text-primary) !important;
}
</style>
