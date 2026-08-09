<script setup>
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { useApi } from '@/composables/useApi'
import AppSidebar from '@/components/common/AppSidebar.vue'

const { requestJson } = useApi()

const sidebarCollapsed = ref(false)
const currentClass = ref('1班')
const currentClassCode = ref('')

async function handleSelectClass(cls, classInfo = {}) {
	const previousClass = currentClass.value
	const previousClassCode = currentClassCode.value
  currentClass.value = cls
  currentClassCode.value = classInfo.class_code || ''
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
    flex-direction: column;
  }
}
</style>
