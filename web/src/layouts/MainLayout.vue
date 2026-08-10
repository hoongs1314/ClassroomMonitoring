<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { syncMediaSession, useApi } from '@/composables/useApi'
import AppSidebar from '@/components/common/AppSidebar.vue'

const { requestJson } = useApi()

const sidebarCollapsed = ref(false)
const currentClass = ref('')
const currentClassCode = ref('')
let mobileQuery

function syncSidebarForViewport(event) {
  // 小屏以图标栏起始，展开时作为覆盖式导航，避免挤压内容区。
  sidebarCollapsed.value = event.matches
}

onMounted(() => {
  mobileQuery = window.matchMedia('(max-width: 768px)')
  syncSidebarForViewport(mobileQuery)
	mobileQuery.addEventListener('change', syncSidebarForViewport)
	void syncMediaSession()
})

onBeforeUnmount(() => {
  mobileQuery?.removeEventListener('change', syncSidebarForViewport)
})

async function handleSelectClass(cls, classInfo = {}, synchronizeRuntime = true) {
	const previousClass = currentClass.value
	const previousClassCode = currentClassCode.value
	currentClass.value = cls
	currentClassCode.value = classInfo.class_code || ''
	if (!synchronizeRuntime) return
  try {
    await requestJson('/api/switch_class', {
      method: 'POST',
      body: JSON.stringify({ class: cls }),
    })
  } catch (error) {
	currentClass.value = previousClass
	currentClassCode.value = previousClassCode
	message.error(error.message || '班级切换失败')
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
      <router-view :current-class="currentClass" :current-class-code="currentClassCode" />
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
    display: block;
  }

  .app-content {
    height: 100%;
    width: calc(100% - var(--sidebar-collapsed-width));
    margin-left: var(--sidebar-collapsed-width);
  }
}
</style>
