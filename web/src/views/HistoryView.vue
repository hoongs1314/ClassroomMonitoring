<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { useApi } from '@/composables/useApi'

const { requestJson } = useApi()
const router = useRouter()

const loading = ref(false)
const classes = ref([])
const selectedClassId = ref('')
const sessions = ref([])
const total = ref(0)

const columns = [
  { title: '班级', dataIndex: 'class_name', width: 120 },
  { title: '教师', dataIndex: 'teacher_name', width: 120 },
  { title: '课程', dataIndex: 'subject_name', width: 120 },
  { title: '课堂主题', dataIndex: 'lesson_title' },
  { title: '状态', dataIndex: 'status', width: 100 },
  { title: '开始时间', dataIndex: 'started_at', width: 180 },
  { title: '警告', dataIndex: 'warning_count', width: 80 },
  { title: '提示', dataIndex: 'notice_count', width: 80 },
  { title: '操作', key: 'action', width: 110 },
]

async function loadClasses() {
  const data = await requestJson('/api/teacher/classes')
  classes.value = data.classes || []
}

async function loadSessions() {
  loading.value = true
  try {
    const headers = {
      'X-Page-No': '1',
      'X-Page-Size': '50',
    }
    if (selectedClassId.value) headers['X-Class-Id'] = String(selectedClassId.value)
    const data = await requestJson('/api/teacher/sessions', { headers })
    sessions.value = data.items || []
    total.value = data.total || 0
  } catch (error) {
    message.error(error.message || '加载历史记录失败')
  } finally {
    loading.value = false
  }
}

function openReview(row) {
  router.push({ name: 'review', query: { sessionId: row.id } })
}

onMounted(async () => {
  try {
    await loadClasses()
    await loadSessions()
  } catch (error) {
    message.error(error.message || '加载数据失败')
  }
})
</script>

<template>
  <div class="history-view">
    <header class="page-head">
      <div>
        <h1>历史监控</h1>
        <p>共 {{ total }} 条课堂监控记录</p>
      </div>
      <div class="filters">
        <a-select
          v-model:value="selectedClassId"
          allow-clear
          placeholder="全部班级"
          style="width: 220px"
          @change="loadSessions"
        >
          <a-select-option v-for="cls in classes" :key="cls.id" :value="cls.id">
            {{ cls.class_name }}
          </a-select-option>
        </a-select>
        <a-button @click="loadSessions">刷新</a-button>
      </div>
    </header>

    <a-table
      :columns="columns"
      :data-source="sessions"
      :loading="loading"
      :pagination="{ pageSize: 12 }"
      row-key="id"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'action'">
          <a-button type="link" @click="openReview(record)">复盘</a-button>
        </template>
      </template>
    </a-table>
  </div>
</template>

<style scoped>
.history-view {
  height: 100%;
  padding: 20px;
  overflow: auto;
}
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}
h1 {
  margin: 0;
  font-size: 24px;
  color: var(--text-primary);
}
p {
  margin: 6px 0 0;
  color: var(--text-muted);
}
.filters {
  display: flex;
  gap: 10px;
  align-items: center;
}
@media (max-width: 760px) {
  .page-head {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
