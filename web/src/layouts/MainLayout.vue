<script setup>
import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import AppSidebar from '@/components/common/AppSidebar.vue'
import MonitorView from '@/views/MonitorView.vue'

const { requestJson } = useApi()

const sidebarCollapsed = ref(false)
const currentClass = ref('1班')

async function handleSelectClass(cls) {
  currentClass.value = cls
  try {
    await requestJson('/api/switch_class', {
      method: 'POST',
      body: JSON.stringify({ class: cls }),
    })
  } catch {
    // 切换失败不影响前端显示
  }
}
</script>

<template>
  <div class="app-layout">
    <AppSidebar
      :collapsed="sidebarCollapsed"
      :current-class="currentClass"
      @toggle="sidebarCollapsed = !sidebarCollapsed"
      @select-class="handleSelectClass"
    />
    <main class="app-content">
      <MonitorView :current-class="currentClass" />
    </main>
  </div>
</template>

<style scoped>
.app-layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

.app-content {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

@media (max-width: 768px) {
  .app-layout {
    flex-direction: column;
  }
}
</style>
