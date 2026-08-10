<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { useApi } from '@/composables/useApi'

const router = useRouter()
const { requestJson } = useApi()
const loading = ref(false)
const classItems = ref([])
const keyword = ref('')

const filteredClasses = computed(() => {
  const value = keyword.value.trim().toLowerCase()
  if (!value) return classItems.value
  return classItems.value.filter((classItem) => [
    classItem.class_name,
    classItem.academic_year_name,
    classItem.term_name,
    classItem.current_course?.course_name,
  ].some((item) => String(item || '').toLowerCase().includes(value)))
})

async function loadClasses() {
  loading.value = true
  try {
    const data = await requestJson('/api/teacher/my-classes')
    classItems.value = data.items || []
  } catch (error) {
    message.error(error.message || '班级列表加载失败')
  } finally {
    loading.value = false
  }
}

function openClass(classItem) {
  if (!classItem.report_course_id) {
    message.warning('当前班级暂无可查看的教学课程')
    return
  }
  router.push({ name: 'class-course-analysis', params: { courseId: classItem.report_course_id } })
}

function currentCourseText(classItem) {
  return classItem.current_course?.course_name || '当前非排课时段'
}

onMounted(loadClasses)
</script>

<template>
  <div class="course-list-view">
    <header class="page-head">
      <div>
        <h1>我的班级</h1>
        <p>按班级查看课程监控和历次报告；当前课程会按获取时刻与固定周课表自动匹配。</p>
      </div>
      <div class="actions">
        <a-input v-model:value="keyword" allow-clear placeholder="班级、学年、学期或当前课程" style="width: 260px" />
        <a-button @click="loadClasses">刷新</a-button>
      </div>
    </header>

    <a-spin :spinning="loading">
      <section v-if="filteredClasses.length" class="course-grid">
        <article v-for="classItem in filteredClasses" :key="classItem.class_id" class="course-card" :class="{ 'is-active': Boolean(classItem.current_course) }" @click="openClass(classItem)">
          <div class="card-top">
            <div>
              <h2>{{ classItem.class_name }}</h2>
              <p>{{ classItem.academic_year_name || '未设置学年' }} 学年 · {{ classItem.term_name }}</p>
            </div>
            <a-tag :color="classItem.current_course ? 'green' : 'default'">{{ classItem.current_course ? '上课中' : '非上课时段' }}</a-tag>
          </div>
          <div class="course-info">
            <span>当前课程</span><strong>{{ currentCourseText(classItem) }}</strong>
            <small v-if="classItem.current_course">{{ classItem.current_course.start_time }}–{{ classItem.current_course.end_time }}{{ classItem.current_course.lesson_title ? ` · ${classItem.current_course.lesson_title}` : '' }}</small>
            <small v-else>刷新页面后会按当前时间重新匹配固定周课表</small>
          </div>
          <div class="teacher">任课教师：{{ classItem.teacher_name || '未分配' }}</div>
          <div class="metrics">
            <div class="metric-card metric-completed"><span>已分析课次</span><strong>{{ classItem.entry_count }}</strong></div>
            <div class="metric-card metric-pending"><span>待分析课次</span><strong>{{ classItem.pending_analysis_count }}</strong></div>
            <div class="metric-card metric-followup"><span>待跟进措施</span><strong>{{ classItem.open_action_count }}</strong></div>
            <div class="metric-card metric-planned"><span>计划课次</span><strong>{{ classItem.planned_lesson_count ?? '-' }}</strong></div>
          </div>
          <a-button class="card-action" type="link" @click.stop="openClass(classItem)">查看班级课程报告 <span aria-hidden="true">→</span></a-button>
        </article>
      </section>
      <a-empty v-else description="暂无可查看的授课班级。请由管理员先完成学期、课程与课表配置。" />
    </a-spin>
  </div>
</template>

<style scoped>
.course-list-view { height: 100%; padding: 20px; overflow: auto; }
.page-head { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 18px; }
h1, h2, p { margin: 0; }
h1 { color: var(--text-primary); font-size: 24px; }
p { margin-top: 6px; color: var(--text-muted); }
.actions { display: flex; gap: 10px; }
.course-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.course-card { position: relative; display: grid; gap: 16px; padding: 20px; overflow: hidden; border: 1px solid var(--border-default); border-radius: var(--radius-lg); background: linear-gradient(150deg, rgba(59, 130, 246, 0.07), transparent 42%), var(--bg-card); cursor: pointer; transition: border-color var(--duration-fast), transform var(--duration-fast), box-shadow var(--duration-fast); }
.course-card::before { position: absolute; top: 0; right: 20px; left: 20px; height: 3px; border-radius: 0 0 3px 3px; background: var(--color-primary); content: ''; opacity: 0.65; }
.course-card.is-active::before { background: var(--color-success); }
.course-card:hover { border-color: var(--border-active); box-shadow: var(--shadow-elevated); transform: translateY(-3px); }
.card-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; padding-top: 2px; }
h2 { color: var(--text-primary); font-size: 20px; }
.course-info { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 4px 8px; padding: 12px 14px; border-left: 3px solid var(--color-primary); border-radius: 0 var(--radius-sm) var(--radius-sm) 0; background: var(--bg-elevated); color: var(--text-secondary); }
.course-info span { padding-top: 2px; color: var(--text-muted); font-size: 12px; }
.course-info strong { overflow: hidden; color: var(--text-primary); font-size: 15px; text-overflow: ellipsis; white-space: nowrap; }
.course-info small { grid-column: 2; overflow: hidden; color: var(--text-muted); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.teacher { padding-top: 2px; border-top: 1px solid var(--border-default); color: var(--text-secondary); font-size: 13px; }
.metrics { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.metric-card { padding: 10px 12px; border: 1px solid transparent; border-radius: var(--radius-md); background: var(--bg-elevated); }
.metric-card span { display: block; color: var(--text-muted); font-size: 12px; }
.metric-card strong { display: block; margin-top: 4px; color: var(--color-primary); font-size: 24px; line-height: 1.1; }
.metric-pending { border-color: rgba(245, 158, 11, 0.2); }
.metric-pending strong { color: var(--color-warning); }
.metric-followup { border-color: rgba(239, 68, 68, 0.2); }
.metric-followup strong { color: var(--color-danger); }
.metric-planned strong { color: var(--text-secondary); }
.card-action { justify-self: start; padding: 0 !important; font-weight: 600; }
.card-action span { margin-left: 4px; transition: transform var(--duration-fast); }
.course-card:hover .card-action span { display: inline-block; transform: translateX(3px); }
@media (max-width: 760px) { .page-head { align-items: flex-start; flex-direction: column; } .actions { width: 100%; } .actions :deep(.ant-input-affix-wrapper) { flex: 1; min-width: 0; } }
</style>
