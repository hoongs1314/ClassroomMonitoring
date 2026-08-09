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
const detailLoading = ref(false)
const detailOpen = ref(false)
const eventDetail = ref(null)
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
    message.error('缺少课次记录')
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
    message.error(error.message || '加载课后分析数据失败')
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
    message.success('课后记录已保存')
  } catch (error) {
    message.error(error.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function openEventDetail(event) {
  detailOpen.value = true
  detailLoading.value = true
  eventDetail.value = null
  try {
    const data = await requestJson('/api/teacher/event/detail', {
      headers: { 'X-Event-Id': String(event.id) },
    })
    eventDetail.value = data.event || null
  } catch (error) {
    message.error(error.message || '加载事件详情失败')
    detailOpen.value = false
  } finally {
    detailLoading.value = false
  }
}

onMounted(loadData)
</script>

<template>
  <div class="review-view">
    <a-button class="back-btn" @click="router.push({ name: 'history' })">返回课次档案</a-button>

    <a-spin :spinning="loading">
      <section v-if="session" class="summary-band">
        <div>
          <h1>{{ session.class_name }} 课后分析报告</h1>
          <p>开始时间：{{ session.started_at || '-' }}</p>
          <p>结束时间：{{ session.ended_at || '课次尚未正常结束' }}</p>
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
              <a-button type="link" @click="openEventDetail(event)">查看详情</a-button>
            </article>
          </div>
          <a-empty v-else description="暂无异常事件" />
        </section>

        <section class="panel">
          <div class="panel-bar">
            <h2>教师课后记录</h2>
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
            <a-button type="primary" :loading="saving" @click="saveReview">保存记录</a-button>
          </div>
        </section>
      </main>
    </a-spin>

    <a-modal v-model:open="detailOpen" title="异常事件详情" width="900px" :footer="null">
      <a-spin :spinning="detailLoading">
        <div v-if="eventDetail" class="event-detail">
          <div class="detail-summary">
            <strong>{{ eventDetail.seat }} · {{ eventDetail.label || eventDetail.status }}</strong>
            <a-tag :color="eventDetail.level === '警告' ? 'red' : 'orange'">{{ eventDetail.level }}</a-tag>
            <span>{{ eventDetail.alert_start_time }}</span>
          </div>
          <p>{{ eventDetail.reason || '暂无复核说明' }}</p>
          <div v-if="eventDetail.frames?.length" class="frame-grid">
            <article v-for="frame in eventDetail.frames" :key="frame.frame_index" class="frame-card">
              <img v-if="frame.focus_image_url" :src="mediaUrl(frame.focus_image_url)" alt="event frame" />
              <strong>帧 {{ frame.frame_index + 1 }} · {{ frame.seat?.status_text || frame.seat?.status }}</strong>
              <span>{{ frame.time || '-' }}</span>
            </article>
          </div>
          <a-empty v-else description="暂无关联截图帧" />
        </div>
      </a-spin>
    </a-modal>
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
  grid-template-columns: 120px minmax(0, 1fr) auto auto;
  gap: 12px;
  align-items: center;
  padding: 10px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-elevated);
}
.event-detail {
  display: grid;
  gap: 14px;
}
.detail-summary {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.frame-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.frame-card {
  display: grid;
  gap: 6px;
  padding: 10px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-elevated);
}
.frame-card img {
  width: 100%;
  max-height: 260px;
  object-fit: contain;
  background: var(--bg-primary);
}
.frame-card span {
  color: var(--text-muted);
  font-size: 12px;
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
  .event-row,
  .frame-grid {
    grid-template-columns: 1fr;
  }
}
</style>
