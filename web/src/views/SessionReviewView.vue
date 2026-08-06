<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { useApi } from '@/composables/useApi'

const route = useRoute()
const router = useRouter()
const { requestJson, mediaUrl } = useApi()

const loading = ref(false)
const saving = ref(false)
const session = ref(null)
const events = ref([])
const review = ref({
  teaching_effect_score: null,
  focus_summary: '',
  problem_summary: '',
  improvement_plan: '',
})

const sessionId = () => route.query.sessionId

async function loadData() {
  if (!sessionId()) {
    message.error('缺少监控记录')
    router.replace({ name: 'history' })
    return
  }
  loading.value = true
  const headers = { 'X-Session-Id': String(sessionId()) }
  try {
    const [detailData, eventData, reviewData] = await Promise.all([
      requestJson('/api/teacher/session/detail', { headers }),
      requestJson('/api/teacher/session/events', { headers }),
      requestJson('/api/teacher/session/review', { headers }),
    ])
    session.value = detailData.session
    events.value = eventData.events || []
    if (reviewData.review) review.value = { ...review.value, ...reviewData.review }
  } catch (error) {
    message.error(error.message || '加载复盘数据失败')
  } finally {
    loading.value = false
  }
}

async function saveReview() {
  saving.value = true
  try {
    const data = await requestJson('/api/teacher/session/review', {
      method: 'POST',
      headers: { 'X-Session-Id': String(sessionId()) },
      body: JSON.stringify(review.value),
    })
    review.value = { ...review.value, ...(data.review || {}) }
    message.success('复盘已保存')
  } catch (error) {
    message.error(error.message || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(loadData)
</script>

<template>
  <div class="review-view">
    <a-button class="back-btn" @click="router.push({ name: 'history' })">返回历史</a-button>

    <a-spin :spinning="loading">
      <section v-if="session" class="summary-band">
        <div>
          <h1>{{ session.class_name }} 课堂复盘</h1>
          <p>开始时间：{{ session.started_at || '-' }}</p>
        </div>
        <div class="summary-grid">
          <div><span>学生</span><strong>{{ session.total_seat_count }}</strong></div>
          <div><span>警告</span><strong>{{ session.warning_count }}</strong></div>
          <div><span>提示</span><strong>{{ session.notice_count }}</strong></div>
          <div><span>事件</span><strong>{{ session.event_count }}</strong></div>
        </div>
      </section>

      <main class="review-grid">
        <section class="panel">
          <div class="panel-bar">
            <h2>异常事件</h2>
          </div>
          <div v-if="events.length" class="event-list">
            <article v-for="event in events" :key="event.id" class="event-row">
              <img v-if="event.url" :src="mediaUrl(event.url)" alt="event" />
              <div>
                <strong>{{ event.seat }} · {{ event.label || event.status }}</strong>
                <p>{{ event.reason || '等待模型分析' }}</p>
              </div>
              <a-tag :color="event.level === '警告' ? 'red' : 'orange'">{{ event.level }}</a-tag>
            </article>
          </div>
          <a-empty v-else description="暂无异常事件" />
        </section>

        <section class="panel">
          <div class="panel-bar">
            <h2>教学复盘</h2>
          </div>
          <div class="form-stack">
            <label>教学效果评分</label>
            <a-input-number v-model:value="review.teaching_effect_score" :min="0" :max="100" style="width: 160px" />
            <label>课堂专注情况</label>
            <a-textarea v-model:value="review.focus_summary" :rows="4" />
            <label>主要问题</label>
            <a-textarea v-model:value="review.problem_summary" :rows="4" />
            <label>改进计划</label>
            <a-textarea v-model:value="review.improvement_plan" :rows="4" />
            <a-button type="primary" :loading="saving" @click="saveReview">保存复盘</a-button>
          </div>
        </section>
      </main>
    </a-spin>
  </div>
</template>

<style scoped>
.review-view {
  height: 100%;
  padding: 20px;
  overflow: auto;
}
.back-btn {
  margin-bottom: 12px;
}
.summary-band {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  background: var(--bg-card);
  margin-bottom: 16px;
}
h1, h2, p {
  margin: 0;
}
h1 {
  color: var(--text-primary);
  font-size: 24px;
}
p {
  color: var(--text-secondary);
}
.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, 86px);
  gap: 10px;
}
.summary-grid div {
  padding: 10px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-elevated);
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
.review-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 420px;
  gap: 16px;
}
.panel {
  min-width: 0;
  padding: 16px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  background: var(--bg-card);
}
.panel-bar {
  margin-bottom: 12px;
}
.event-list {
  display: grid;
  gap: 10px;
}
.event-row {
  display: grid;
  grid-template-columns: 120px minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  padding: 10px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-elevated);
}
.event-row img {
  width: 120px;
  height: 68px;
  object-fit: contain;
  background: var(--bg-primary);
}
.form-stack {
  display: grid;
  gap: 10px;
}
label {
  color: var(--text-secondary);
  font-weight: 600;
}
@media (max-width: 1080px) {
  .review-grid,
  .summary-band {
    grid-template-columns: 1fr;
    display: grid;
  }
  .summary-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
