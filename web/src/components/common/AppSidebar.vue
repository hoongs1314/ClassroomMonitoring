<script setup>
import { ref, computed, onMounted } from 'vue'
import {
  TeamOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  VideoCameraFilled,
  HistoryOutlined,
  LogoutOutlined,
  SettingOutlined,
  ReadOutlined,
  CalendarOutlined,
} from '@ant-design/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import { useWebSocket } from '@/composables/useWebSocket'
import { useApi, getStoredUser } from '@/composables/useApi'

defineProps({
  collapsed: Boolean,
  currentClass: String,
})

const emit = defineEmits(['toggle', 'select-class'])

const { isConnected, status } = useWebSocket()
const { requestJson, clearAuth } = useApi()
const router = useRouter()
const route = useRoute()

const classList = ref([])
const activeClass = ref('')
const currentUser = ref(getStoredUser())
const isAdmin = computed(() => currentUser.value?.roles?.includes('ADMIN'))

function normalizeClass(item) {
  if (typeof item === 'string') {
    return { class_name: item, class_code: '' }
  }
  return item || { class_name: '', class_code: '' }
}

onMounted(async () => {
  try {
    const data = await requestJson('/api/teacher/classes')
    classList.value = (data.classes || []).map(normalizeClass)
    activeClass.value = classList.value[0]?.class_name || ''
  } catch (error) {
	if (error.status !== 404) return
    try {
      const data = await requestJson('/api/classes')
      classList.value = (data.classes || []).map(normalizeClass)
      activeClass.value = data.current || classList.value[0]?.class_name || ''
    } catch {
      classList.value = []
      activeClass.value = ''
    }
  }
})

const currentClassName = computed(() => status.value?.current_class || activeClass.value)
const navSelected = computed(() => [route.name || 'monitor'])
const showDemoClassSelector = computed(() => route.name === 'monitor')

function handleSelect(cls) {
  const selected = classList.value.find((item) => item.class_name === cls) || normalizeClass(cls)
  activeClass.value = selected.class_name
  emit('select-class', selected.class_name, selected)
}

function handleLogout() {
  requestJson('/api/auth/logout', { method: 'POST' }).catch(() => {})
  clearAuth()
  router.push({ name: 'login' })
}
</script>

<template>
  <aside class="sidebar" :class="{ collapsed }">
    <div class="sidebar-logo">
      <div class="logo-icon">
        <VideoCameraFilled />
      </div>
      <span v-show="!collapsed" class="logo-text">课后教学分析</span>
    </div>

    <div class="sidebar-section">
      <a-menu
        :selected-keys="navSelected"
        :inline-collapsed="collapsed"
        mode="inline"
        theme="dark"
        class="sidebar-menu compact"
      >
        <a-menu-item key="classes" @click="router.push({ name: 'classes' })">
          <template #icon><ReadOutlined /></template>
          <span>我的班级</span>
        </a-menu-item>
        <a-menu-item v-if="isAdmin" key="history" @click="router.push({ name: 'history' })">
          <template #icon><HistoryOutlined /></template>
          <span>全局课次档案</span>
        </a-menu-item>
        <a-menu-item v-if="isAdmin" key="monitor" @click="router.push({ name: 'monitor' })">
          <template #icon><VideoCameraFilled /></template>
          <span>演示监控</span>
        </a-menu-item>
        <a-menu-item v-if="isAdmin" key="admin" @click="router.push({ name: 'admin' })">
          <template #icon><SettingOutlined /></template>
          <span>账号与班级管理</span>
        </a-menu-item>
        <a-menu-item v-if="isAdmin" key="teaching-setup" @click="router.push({ name: 'teaching-setup' })">
          <template #icon><CalendarOutlined /></template>
          <span>教学与设备配置</span>
        </a-menu-item>
      </a-menu>
      <span v-if="showDemoClassSelector" v-show="!collapsed" class="section-label">演示班级</span>
      <a-menu
        v-if="showDemoClassSelector"
        :selected-keys="[currentClassName]"
        :inline-collapsed="collapsed"
        mode="inline"
        theme="dark"
        class="sidebar-menu"
        @click="({ key }) => handleSelect(key)"
      >
        <a-menu-item v-for="cls in classList" :key="cls.class_name">
          <template #icon><TeamOutlined /></template>
          <span>{{ cls.class_name }}</span>
        </a-menu-item>
      </a-menu>
    </div>

    <div class="sidebar-footer">
      <div class="footer-main">
        <div class="status-row" :class="{ connected: isConnected }">
          <span class="status-dot"></span>
          <span v-show="!collapsed" class="status-text">
            {{ isConnected ? '已连接' : '未连接' }}
          </span>
        </div>
        <div v-show="!collapsed" class="user-name">{{ currentUser?.real_name || currentUser?.username || '未登录' }}</div>
      </div>
      <a-button
        type="text"
        class="toggle-btn"
        @click="emit('toggle')"
      >
        <MenuFoldOutlined v-if="!collapsed" />
        <MenuUnfoldOutlined v-else />
      </a-button>
      <a-button type="text" class="toggle-btn" title="退出登录" @click="handleLogout">
        <LogoutOutlined />
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
.sidebar-menu.compact {
  flex: 0 0 auto;
  padding-top: 0;
  border-bottom: 1px solid var(--border-default);
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
.footer-main {
  min-width: 0;
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
.user-name {
  margin-top: 4px;
  max-width: 128px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: var(--text-secondary);
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
