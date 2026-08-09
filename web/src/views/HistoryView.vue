<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { useApi } from '@/composables/useApi'

const { requestJson } = useApi()
const router = useRouter()

const loading = ref(false)
const classes = ref([])
const selectedClassId = ref('')
const selectedDateRange = ref([])
const sessions = ref([])
const total = ref(0)
const pageNo = ref(1)
const pageSize = ref(12)
const summary = ref({
  session_count: 0,
  class_count: 0,
  warning_count: 0,
  notice_count: 0,
  event_count: 0,
})

const columns = [
  { title: '班级', dataIndex: 'class_name', width: 120 },
  { title: '教师', dataIndex: 'teacher_name', width: 120 },
  { title: '状态', dataIndex: 'status', width: 100 },
  { title: '开始时间', dataIndex: 'started_at', width: 180 },
  { title: '结束时间', dataIndex: 'ended_at', width: 180 },
  { title: '警告', dataIndex: 'warning_count', width: 80 },
  { title: '提示', dataIndex: 'notice_count', width: 80 },
  { title: '操作', key: 'action', width: 110 },
]

const pagination = computed(() => ({
  current: pageNo.value,
  pageSize: pageSize.value,
  total: total.value,
  showSizeChanger: true,
  pageSizeOptions: ['12', '24', '50'],
  showTotal: (value) => `共 ${value} 条`,
}))

async function loadClasses() {
  const data = await requestJson('/api/teacher/classes')
  classes.value = data.classes || []
}

async function loadSessions() {
  loading.value = true
  try {
    const headers = {
      'X-Page-No': String(pageNo.value),
      'X-Page-Size': String(pageSize.value),
    }
    if (selectedClassId.value) headers['X-Class-Id'] = String(selectedClassId.value)
    if (selectedDateRange.value?.length === 2) {
      headers['X-Start-Date'] = selectedDateRange.value[0].format('YYYY-MM-DD')
      headers['X-End-Date'] = selectedDateRange.value[1].format('YYYY-MM-DD')
    }
    const data = await requestJson('/api/teacher/sessions', { headers })
    sessions.value = data.items || []
    total.value = data.total || 0
    summary.value = { ...summary.value, ...(data.summary || {}) }
  } catch (error) {
    message.error(error.message || '加载历史记录失败')
  } finally {
    loading.value = false
  }
}

function reloadFromFirstPage() {
  pageNo.value = 1
  loadSessions()
}

function handleTableChange(nextPagination) {
  pageNo.value = nextPagination.current || 1
  pageSize.value = nextPagination.pageSize || 12
  loadSessions()
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
        <h1>全局课次档案</h1>
        <p>跨班级查看共 {{ total }} 条可用于管理员排查的课次记录</p>
      </div>
      <div class="filters">
        <a-select
          v-model:value="selectedClassId"
          allow-clear
          placeholder="全部班级"
          style="width: 220px"
          @change="reloadFromFirstPage"
        >
          <a-select-option v-for="cls in classes" :key="cls.id" :value="cls.id">
            {{ cls.class_name }}
          </a-select-option>
        </a-select>
        <a-range-picker
          v-model:value="selectedDateRange"
          :placeholder="['开始日期', '结束日期']"
          @change="reloadFromFirstPage"
        />
        <a-button @click="reloadFromFirstPage">刷新</a-button>
      </div>
    </header>

    <section class="summary-grid">
      <div><span>课堂数</span><strong>{{ summary.session_count }}</strong></div>
      <div><span>班级数</span><strong>{{ summary.class_count }}</strong></div>
      <div><span>警告</span><strong>{{ summary.warning_count }}</strong></div>
      <div><span>提示</span><strong>{{ summary.notice_count }}</strong></div>
      <div><span>事件</span><strong>{{ summary.event_count }}</strong></div>
    </section>

    <a-table
      :columns="columns"
      :data-source="sessions"
      :loading="loading"
      :pagination="pagination"
      row-key="id"
      @change="handleTableChange"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'action'">
          <a-button type="link" @click="openReview(record)">查看报告</a-button>
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
.summary-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(110px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.summary-grid div {
  padding: 14px 16px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-card);
}
.summary-grid span {
  display: block;
  color: var(--text-muted);
  font-size: 12px;
}
.summary-grid strong {
  display: block;
  margin-top: 4px;
  color: var(--color-primary);
  font-size: 24px;
}
@media (max-width: 760px) {
  .page-head {
    align-items: flex-start;
    flex-direction: column;
  }
  .filters {
    width: 100%;
    flex-wrap: wrap;
  }
  .summary-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
