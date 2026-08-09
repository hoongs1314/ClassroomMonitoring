<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { useApi } from '@/composables/useApi'

const route = useRoute()
const router = useRouter()
const { requestJson } = useApi()

const loading = ref(false)
const saving = ref(false)
const course = ref(null)
const entries = ref([])
const actions = ref([])
const aggregates = ref([])
const reports = ref([])
const activeTab = ref('archive')
const archiveLoading = ref(false)
const archiveSessions = ref([])
const archiveTotal = ref(0)
const archivePageNo = ref(1)
const archivePageSize = ref(12)
const archiveDateRange = ref([])
const archiveSummary = ref({ session_count: 0, warning_count: 0, notice_count: 0, event_count: 0 })
const entryModalOpen = ref(false)
const actionModalOpen = ref(false)
const reportModalOpen = ref(false)
const editingEntry = ref(null)
const editingAction = ref(null)
const editingReport = ref(null)
const entryForm = ref({})
const actionForm = ref({})
const reportForm = ref({})

const courseId = computed(() => Number(route.params.courseId))
const reportReadOnly = computed(() => editingReport.value?.report_status === 'PUBLISHED')
const archivePagination = computed(() => ({
  current: archivePageNo.value,
  pageSize: archivePageSize.value,
  total: archiveTotal.value,
  showSizeChanger: true,
  pageSizeOptions: ['12', '24', '50'],
  showTotal: (value) => `共 ${value} 条`,
}))
const archiveColumns = [
  { title: '课次', dataIndex: 'lesson_title', width: 150 },
  { title: '状态', key: 'status', width: 110 },
  { title: '分析状态', key: 'analysis_status', width: 110 },
  { title: '开始时间', dataIndex: 'started_at', width: 180 },
  { title: '警告', dataIndex: 'warning_count', width: 70 },
  { title: '提示', dataIndex: 'notice_count', width: 70 },
  { title: '事件', dataIndex: 'event_count', width: 70 },
  { title: '操作', key: 'action', width: 130 },
]

function entryTitle(entry) {
  return `第 ${entry.lesson_index} 节 · ${entry.lesson_title || '未命名课次'}`
}

function qualityText(value) {
  return { GOOD: '数据质量良好', LIMITED: '数据质量受限', UNAVAILABLE: '暂无可用数据' }[value] || value
}

function qualityColor(value) {
  return { GOOD: 'green', LIMITED: 'orange', UNAVAILABLE: 'default' }[value] || 'default'
}

function actionText(value) {
  return { PLANNED: '待实施', IMPLEMENTED: '已实施', VERIFIED: '已验证', CLOSED: '已闭环' }[value] || value
}

function sessionStatusText(value) {
  return { SCHEDULED: '已排课', RUNNING: '监控中', STOPPED: '已结束', FAILED: '异常结束' }[value] || value
}

function analysisStatusText(value) {
  return { PENDING: '待分析', RUNNING: '分析中', COMPLETED: '已完成', FAILED: '分析失败' }[value] || value
}

// 班级详情必须携带教学课程标识，服务端据此排除同班其他学科的课次。
function archiveRequestOptions() {
  const headers = {
    'X-Teaching-Course-Id': String(courseId.value),
    'X-Page-No': String(archivePageNo.value),
    'X-Page-Size': String(archivePageSize.value),
  }
  if (archiveDateRange.value?.length === 2) {
    headers['X-Start-Date'] = archiveDateRange.value[0].format('YYYY-MM-DD')
    headers['X-End-Date'] = archiveDateRange.value[1].format('YYYY-MM-DD')
  }
  return { headers }
}

function applyArchiveData(data) {
  archiveSessions.value = data.items || []
  archiveTotal.value = data.total || 0
  archiveSummary.value = { ...archiveSummary.value, ...(data.summary || {}) }
}

async function loadArchive() {
  archiveLoading.value = true
  try {
    const data = await requestJson('/api/teacher/sessions', archiveRequestOptions())
    applyArchiveData(data)
  } catch (error) {
    message.error(error.message || '课次档案加载失败')
  } finally {
    archiveLoading.value = false
  }
}

function reloadArchiveFromFirstPage() {
  archivePageNo.value = 1
  loadArchive()
}

function handleArchiveTableChange(nextPagination) {
  archivePageNo.value = nextPagination.current || 1
  archivePageSize.value = nextPagination.pageSize || 12
  loadArchive()
}

function openSessionReview(session) {
  router.push({ name: 'review', query: { sessionId: session.id } })
}

async function loadData() {
  loading.value = true
  try {
    const [courseData, entryData, actionData, aggregateData, reportData, archiveData] = await Promise.all([
      requestJson('/api/teacher/teaching-courses'),
      requestJson(`/api/teacher/teaching-courses/${courseId.value}/entries`),
      requestJson(`/api/teacher/teaching-courses/${courseId.value}/improvement-actions`),
      requestJson(`/api/teacher/teaching-courses/${courseId.value}/aggregates`),
      requestJson(`/api/teacher/teaching-courses/${courseId.value}/reports`),
      requestJson('/api/teacher/sessions', archiveRequestOptions()),
    ])
    course.value = (courseData.items || []).find((item) => item.id === courseId.value) || null
    entries.value = entryData.items || []
    actions.value = actionData.items || []
    aggregates.value = aggregateData.items || []
    reports.value = reportData.items || []
    applyArchiveData(archiveData)
  } catch (error) {
    message.error(error.message || '课程分析加载失败')
  } finally {
    loading.value = false
  }
}

function openEntry(entry) {
  editingEntry.value = entry
  entryForm.value = {
    teacher_change_note: entry.teacher_change_note || '',
    is_baseline: entry.is_baseline,
    is_milestone: entry.is_milestone,
  }
  entryModalOpen.value = true
}

async function saveEntry() {
  saving.value = true
  try {
    await requestJson(`/api/teacher/course-analysis-entries/${editingEntry.value.id}`, {
      method: 'PUT',
      body: JSON.stringify(entryForm.value),
    })
    message.success('课程分析标注已保存')
    entryModalOpen.value = false
    await loadData()
  } catch (error) {
    message.error(error.message || '保存失败')
  } finally {
    saving.value = false
  }
}

function resetActionForm() {
  actionForm.value = {
    source_entry_id: entries.value[0]?.id,
    issue_type: '',
    issue_description: '',
    improvement_plan: '',
    action_status: 'PLANNED',
    verified_by_entry_id: undefined,
    verification_note: '',
  }
}

function openCreateAction(entry = null) {
  editingAction.value = null
  resetActionForm()
  if (entry) actionForm.value.source_entry_id = entry.id
  actionModalOpen.value = true
}

function openEditAction(action) {
  editingAction.value = action
  actionForm.value = {
    source_entry_id: action.source_entry_id,
    issue_type: action.issue_type,
    issue_description: action.issue_description,
    improvement_plan: action.improvement_plan,
    action_status: action.action_status,
    verified_by_entry_id: action.verified_by_entry_id,
    verification_note: action.verification_note,
  }
  actionModalOpen.value = true
}

async function saveAction() {
  if (!actionForm.value.source_entry_id || !actionForm.value.issue_description || !actionForm.value.improvement_plan) {
    message.warning('请选择来源课次并填写问题说明、改进措施')
    return
  }
  saving.value = true
  try {
    if (editingAction.value) {
      await requestJson(`/api/teacher/improvement-actions/${editingAction.value.id}`, {
        method: 'PUT',
        body: JSON.stringify(actionForm.value),
      })
    } else {
      await requestJson(`/api/teacher/teaching-courses/${courseId.value}/improvement-actions`, {
        method: 'POST',
        body: JSON.stringify(actionForm.value),
      })
    }
    message.success('教学改进措施已保存')
    actionModalOpen.value = false
    await loadData()
  } catch (error) {
    message.error(error.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function refreshAggregate() {
  saving.value = true
  try {
    await requestJson(`/api/teacher/teaching-courses/${courseId.value}/aggregates/refresh`, {
      method: 'POST',
      body: JSON.stringify({ scope_type: 'TERM' }),
    })
    message.success('课程汇总已刷新')
    await loadData()
  } catch (error) {
    message.error(error.message || '汇总刷新失败')
  } finally {
    saving.value = false
  }
}

async function createReport(aggregate) {
  saving.value = true
  try {
    await requestJson(`/api/teacher/teaching-courses/${courseId.value}/reports`, {
      method: 'POST',
      body: JSON.stringify({ aggregate_id: aggregate.id }),
    })
    message.success('课程阶段报告草稿已生成')
    await loadData()
  } catch (error) {
    message.error(error.message || '报告生成失败')
  } finally {
    saving.value = false
  }
}

function openReport(report) {
  editingReport.value = report
  reportForm.value = {
    finding_text: report.finding_text || '',
    suggestion_text: report.suggestion_text || '',
    teacher_conclusion: report.teacher_conclusion || '',
    publish: false,
  }
  reportModalOpen.value = true
}

async function saveReport() {
  if (reportReadOnly.value) return
  saving.value = true
  try {
    await requestJson(`/api/teacher/teaching-analysis-reports/${editingReport.value.id}`, {
      method: 'PUT',
      body: JSON.stringify(reportForm.value),
    })
    message.success(reportForm.value.publish ? '课程报告已发布' : '课程报告草稿已保存')
    reportModalOpen.value = false
    await loadData()
  } catch (error) {
    message.error(error.message || '报告保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(loadData)
</script>

<template>
  <div class="course-analysis-view">
    <a-button class="back-btn" @click="router.push({ name: 'classes' })">返回我的班级</a-button>
    <a-spin :spinning="loading">
      <template v-if="course">
        <header class="course-head">
          <div>
            <h1>{{ course.class_name }}</h1>
            <p>{{ course.academic_year_name || '未设置学年' }} 学年 · {{ course.term_name }} · {{ course.subject_name }} · {{ course.teacher_name }}</p>
          </div>
          <a-space>
            <a-button :loading="saving" @click="refreshAggregate">刷新课程汇总</a-button>
            <a-button type="primary" @click="openCreateAction()">新增改进措施</a-button>
          </a-space>
        </header>

        <section class="summary-grid">
          <div><span>已分析课次</span><strong>{{ entries.length }}</strong></div>
          <div><span>待分析课次</span><strong>{{ course.pending_analysis_count }}</strong></div>
          <div><span>待跟进措施</span><strong>{{ course.open_action_count }}</strong></div>
          <div><span>计划课次</span><strong>{{ course.planned_lesson_count ?? '-' }}</strong></div>
          <div><span>阶段报告</span><strong>{{ reports.filter((item) => item.report_scope === 'COURSE').length }}</strong></div>
        </section>

        <a-tabs v-model:active-key="activeTab" class="detail-tabs">
          <a-tab-pane key="archive" tab="课次档案">
            <section class="panel archive-panel">
              <div class="panel-bar archive-bar">
                <div><h2>课次档案</h2><span>仅显示当前班级、当前课程在课表中生成的课次。</span></div>
                <div class="archive-actions">
                  <a-range-picker v-model:value="archiveDateRange" :placeholder="['开始日期', '结束日期']" @change="reloadArchiveFromFirstPage" />
                  <a-button @click="reloadArchiveFromFirstPage">刷新</a-button>
                </div>
              </div>
              <div class="archive-summary-grid">
                <div><span>课次</span><strong>{{ archiveSummary.session_count }}</strong></div>
                <div><span>警告</span><strong>{{ archiveSummary.warning_count }}</strong></div>
                <div><span>提示</span><strong>{{ archiveSummary.notice_count }}</strong></div>
                <div><span>事件</span><strong>{{ archiveSummary.event_count }}</strong></div>
              </div>
              <a-table :columns="archiveColumns" :data-source="archiveSessions" :loading="archiveLoading" :pagination="archivePagination" row-key="id" @change="handleArchiveTableChange">
                <template #bodyCell="{ column, record }">
                  <template v-if="column.dataIndex === 'lesson_title'">{{ record.lesson_title || '未命名课次' }}</template>
                  <template v-else-if="column.key === 'status'"><a-tag>{{ sessionStatusText(record.status) }}</a-tag></template>
                  <template v-else-if="column.key === 'analysis_status'"><a-tag :color="record.analysis_status === 'COMPLETED' ? 'green' : 'default'">{{ analysisStatusText(record.analysis_status) }}</a-tag></template>
                  <template v-else-if="column.key === 'action'"><a-button type="link" @click="openSessionReview(record)">查看课程监控</a-button></template>
                </template>
              </a-table>
            </section>
          </a-tab-pane>

          <a-tab-pane key="analysis" tab="课程分析与报告">
            <main class="content-grid">
              <section class="panel timeline-panel">
                <div class="panel-bar"><h2>历次课后分析</h2><span>按课次查看数据变化与教学反思</span></div>
                <a-empty v-if="!entries.length" description="暂无已完成的课次分析。" />
                <div v-else class="entry-list">
                  <article v-for="entry in entries" :key="entry.id" class="entry-card">
                    <div class="entry-index">{{ entry.lesson_index }}</div>
                    <div class="entry-main">
                      <div class="entry-title">
                        <strong>{{ entryTitle(entry) }}</strong>
                        <span>{{ entry.lesson_date }}</span>
                        <a-tag :color="qualityColor(entry.data_quality_level)">{{ qualityText(entry.data_quality_level) }}</a-tag>
                        <a-tag v-if="entry.is_baseline" color="blue">基准课</a-tag>
                        <a-tag v-if="entry.is_milestone" color="purple">阶段课</a-tag>
                      </div>
                      <div class="entry-metrics">
                        <span>事件 {{ entry.event_count }}</span>
                        <span>VLM 确认 {{ entry.confirmed_event_count }}</span>
                        <span>有效分析 {{ entry.valid_analysis_seconds }} 秒</span>
                        <span v-for="stat in entry.behavior_stats.slice(0, 3)" :key="stat.behavior_code">{{ stat.behavior_code }} {{ stat.event_count }}</span>
                      </div>
                      <p v-if="entry.system_change_summary">{{ entry.system_change_summary }}</p>
                      <p v-if="entry.teacher_change_note" class="teacher-note">教师记录：{{ entry.teacher_change_note }}</p>
                    </div>
                    <div class="entry-actions">
                      <a-button v-if="entry.session_id" type="link" @click="router.push({ name: 'review', query: { sessionId: entry.session_id } })">查看课程监控</a-button>
                      <a-button type="link" @click="openEntry(entry)">标注</a-button>
                      <a-button type="link" @click="openCreateAction(entry)">提出措施</a-button>
                    </div>
                  </article>
                </div>
              </section>

              <aside class="side-column">
                <section class="panel">
                  <div class="panel-bar"><h2>教学改进闭环</h2></div>
                  <a-empty v-if="!actions.length" description="暂无教学改进措施" :image-style="{ height: '52px' }" />
                  <div v-else class="action-list">
                    <article v-for="action in actions" :key="action.id" class="action-card">
                      <div class="action-title"><strong>{{ action.issue_type || '教学观察' }}</strong><a-tag>{{ actionText(action.action_status) }}</a-tag></div>
                      <p>问题：{{ action.issue_description }}</p>
                      <p>措施：{{ action.improvement_plan }}</p>
                      <p v-if="action.verification_note">验证：{{ action.verification_note }}</p>
                      <a-button type="link" @click="openEditAction(action)">更新状态</a-button>
                    </article>
                  </div>
                </section>

                <section class="panel">
                  <div class="panel-bar"><h2>课程汇总与报告</h2></div>
                  <a-empty v-if="!aggregates.length" description="请先刷新课程汇总" :image-style="{ height: '52px' }" />
                  <div v-else class="aggregate-list">
                    <article v-for="aggregate in aggregates" :key="aggregate.id" class="aggregate-card">
                      <strong>{{ aggregate.scope_type }} 汇总</strong>
                      <p>已完成 {{ aggregate.completed_session_count }}/{{ aggregate.source_session_count }} 节 · {{ qualityText(aggregate.data_quality_level) }}</p>
                      <div class="tag-row"><a-tag v-for="stat in aggregate.behavior_stats" :key="stat.behavior_code">{{ stat.behavior_code }} {{ stat.event_count }}</a-tag></div>
                      <a-button v-if="aggregate.aggregate_status === 'READY'" type="link" @click="createReport(aggregate)">生成课程报告</a-button>
                    </article>
                  </div>
                  <div v-if="reports.length" class="report-list">
                    <a-divider>课程报告</a-divider>
                    <article v-for="report in reports.filter((item) => item.report_scope === 'COURSE')" :key="report.id" class="report-card">
                      <strong>{{ report.report_title }}</strong>
                      <span>{{ report.report_status === 'PUBLISHED' ? '已发布' : '草稿' }}</span>
                      <a-button type="link" @click="openReport(report)">{{ report.report_status === 'PUBLISHED' ? '查看' : '编辑与发布' }}</a-button>
                    </article>
                  </div>
                </section>
              </aside>
            </main>
          </a-tab-pane>
        </a-tabs>
      </template>
    </a-spin>

    <a-modal v-model:open="entryModalOpen" title="课程分析标注" :width="640" :confirm-loading="saving" @ok="saveEntry">
      <a-form layout="vertical" class="modal-form">
        <a-form-item label="教师记录"><a-textarea v-model:value="entryForm.teacher_change_note" :rows="4" placeholder="记录本节课的课堂观察和变化解释" /></a-form-item>
        <a-form-item label="课程基准"><a-checkbox v-model:checked="entryForm.is_baseline">设为后续比较基准</a-checkbox></a-form-item>
        <a-form-item label="阶段课"><a-checkbox v-model:checked="entryForm.is_milestone">标为阶段性关键课次</a-checkbox></a-form-item>
      </a-form>
    </a-modal>

    <a-modal v-model:open="actionModalOpen" :title="editingAction ? '更新教学改进措施' : '新增教学改进措施'" :width="700" :confirm-loading="saving" @ok="saveAction">
      <a-form layout="vertical" class="modal-form">
        <a-form-item label="来源课次"><a-select v-model:value="actionForm.source_entry_id"><a-select-option v-for="entry in entries" :key="entry.id" :value="entry.id">{{ entryTitle(entry) }}</a-select-option></a-select></a-form-item>
        <a-form-item label="问题类别"><a-input v-model:value="actionForm.issue_type" placeholder="例如：课堂互动、讲授节奏" /></a-form-item>
        <a-form-item label="问题说明"><a-textarea v-model:value="actionForm.issue_description" :rows="3" /></a-form-item>
        <a-form-item label="改进措施"><a-textarea v-model:value="actionForm.improvement_plan" :rows="3" /></a-form-item>
        <a-form-item v-if="editingAction" label="当前状态"><a-select v-model:value="actionForm.action_status"><a-select-option value="PLANNED">待实施</a-select-option><a-select-option value="IMPLEMENTED">已实施</a-select-option><a-select-option value="VERIFIED">已验证</a-select-option><a-select-option value="CLOSED">已闭环</a-select-option></a-select></a-form-item>
        <template v-if="editingAction && ['VERIFIED', 'CLOSED'].includes(actionForm.action_status)">
          <a-form-item label="验证课次"><a-select v-model:value="actionForm.verified_by_entry_id" allow-clear><a-select-option v-for="entry in entries" :key="entry.id" :value="entry.id">{{ entryTitle(entry) }}</a-select-option></a-select></a-form-item>
          <a-form-item label="验证说明"><a-textarea v-model:value="actionForm.verification_note" :rows="3" /></a-form-item>
        </template>
      </a-form>
    </a-modal>

    <a-modal v-model:open="reportModalOpen" title="课程阶段报告" :width="700" :confirm-loading="saving" :ok-text="reportReadOnly ? '已发布' : '保存'" :ok-button-props="{ disabled: reportReadOnly }" @ok="saveReport">
      <a-form layout="vertical" class="modal-form">
        <a-form-item label="阶段发现"><a-textarea v-model:value="reportForm.finding_text" :rows="4" :readonly="reportReadOnly" /></a-form-item>
        <a-form-item label="后续建议"><a-textarea v-model:value="reportForm.suggestion_text" :rows="4" :readonly="reportReadOnly" /></a-form-item>
        <a-form-item label="教师结论"><a-textarea v-model:value="reportForm.teacher_conclusion" :rows="4" :readonly="reportReadOnly" placeholder="由教师结合课程内容形成最终结论" /></a-form-item>
        <a-form-item v-if="editingReport?.report_status !== 'PUBLISHED'" label="发布报告"><a-checkbox v-model:checked="reportForm.publish">确认发布并冻结当前报告版本</a-checkbox></a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<style scoped>
.course-analysis-view { height: 100%; padding: 20px; overflow: auto; }
.back-btn { margin-bottom: 12px; }
.course-head, .panel-bar, .entry-title, .action-title, .report-card { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.course-head { padding: 18px; border: 1px solid var(--border-default); border-radius: var(--radius-lg); background: var(--bg-card); }
h1, h2, p { margin: 0; }
h1 { color: var(--text-primary); font-size: 24px; }
h2 { color: var(--text-primary); font-size: 17px; }
p { color: var(--text-secondary); }
.course-head p { margin-top: 6px; color: var(--text-muted); }
.summary-grid { display: grid; grid-template-columns: repeat(5, minmax(110px, 1fr)); gap: 12px; margin: 16px 0; }
.summary-grid div, .panel { padding: 16px; border: 1px solid var(--border-default); border-radius: var(--radius-lg); background: var(--bg-card); }
.summary-grid span { display: block; color: var(--text-muted); font-size: 12px; }
.summary-grid strong { display: block; margin-top: 4px; color: var(--color-primary); font-size: 24px; }
.detail-tabs { margin-top: 6px; }
.archive-panel { margin-top: 2px; }
.archive-bar { align-items: flex-start; }
.archive-actions { display: flex; flex-wrap: wrap; gap: 10px; }
.archive-summary-grid { display: grid; grid-template-columns: repeat(4, minmax(110px, 1fr)); gap: 12px; margin-bottom: 16px; }
.archive-summary-grid div { padding: 12px; border-radius: var(--radius-md); background: var(--bg-elevated); }
.archive-summary-grid span { display: block; color: var(--text-muted); font-size: 12px; }
.archive-summary-grid strong { display: block; margin-top: 4px; color: var(--color-primary); font-size: 22px; }
.content-grid { display: grid; grid-template-columns: minmax(0, 1fr) 390px; gap: 16px; }
.panel { min-width: 0; }
.panel-bar { margin-bottom: 12px; }
.panel-bar span { color: var(--text-muted); font-size: 12px; }
.entry-list, .action-list, .aggregate-list, .report-list { display: grid; gap: 10px; }
.entry-card { display: grid; grid-template-columns: 38px minmax(0, 1fr) auto; gap: 12px; padding: 12px; border: 1px solid var(--border-default); border-radius: var(--radius-md); background: var(--bg-elevated); }
.entry-index { display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; border-radius: 50%; background: var(--color-primary-soft); color: var(--color-primary); font-weight: 700; }
.entry-title { justify-content: flex-start; flex-wrap: wrap; color: var(--text-primary); }
.entry-title span, .entry-metrics { color: var(--text-muted); font-size: 12px; }
.entry-metrics { display: flex; flex-wrap: wrap; gap: 10px; margin: 7px 0; }
.entry-main p { margin-top: 6px; font-size: 13px; }
.teacher-note { color: var(--color-primary) !important; }
.entry-actions { display: grid; align-content: start; }
.side-column { display: grid; gap: 16px; align-content: start; }
.action-card, .aggregate-card, .report-card { padding: 10px; border: 1px solid var(--border-default); border-radius: var(--radius-md); background: var(--bg-elevated); }
.action-card p, .aggregate-card p { margin-top: 6px; font-size: 12px; }
.tag-row { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px; }
.report-card { display: grid; grid-template-columns: 1fr auto auto; }
@media (max-width: 1080px) { .content-grid { grid-template-columns: 1fr; } .summary-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 720px) { .course-head, .entry-card { grid-template-columns: 1fr; display: grid; } .course-head { align-items: flex-start; } .entry-actions { display: flex; flex-wrap: wrap; } .archive-bar { display: grid; } .archive-summary-grid { grid-template-columns: repeat(2, 1fr); } }
</style>
