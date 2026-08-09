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
        <article v-for="classItem in filteredClasses" :key="classItem.class_id" class="course-card" @click="openClass(classItem)">
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
            <div><span>已分析课次</span><strong>{{ classItem.entry_count }}</strong></div>
            <div><span>待分析课次</span><strong>{{ classItem.pending_analysis_count }}</strong></div>
            <div><span>待跟进措施</span><strong>{{ classItem.open_action_count }}</strong></div>
            <div><span>计划课次</span><strong>{{ classItem.planned_lesson_count ?? '-' }}</strong></div>
          </div>
          <a-button type="link" @click.stop="openClass(classItem)">查看班级课程报告 →</a-button>
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
.course-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }
.course-card { display: grid; gap: 14px; padding: 18px; border: 1px solid var(--border-default); border-radius: var(--radius-lg); background: var(--bg-card); cursor: pointer; transition: border-color var(--duration-fast), transform var(--duration-fast); }
.course-card:hover { border-color: var(--border-active); transform: translateY(-2px); }
.card-top { display: flex; justify-content: space-between; gap: 10px; }
h2 { color: var(--text-primary); font-size: 18px; }
.course-info { display: flex; align-items: baseline; flex-wrap: wrap; gap: 6px; color: var(--text-secondary); }
.course-info span { color: var(--text-muted); font-size: 12px; }
.course-info strong { color: var(--text-primary); font-size: 15px; }
.course-info small { width: 100%; color: var(--text-muted); font-size: 12px; }
.teacher { color: var(--text-secondary); font-size: 13px; }
.metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
.metrics div { padding: 10px; border-radius: var(--radius-md); background: var(--bg-elevated); }
.metrics span { display: block; color: var(--text-muted); font-size: 12px; }
.metrics strong { display: block; margin-top: 4px; color: var(--color-primary); font-size: 22px; }
@media (max-width: 760px) { .page-head { align-items: flex-start; flex-direction: column; } .actions { width: 100%; } }
</style>
