<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { useApi } from '@/composables/useApi'
import WeeklyScheduleEditor from '@/components/teaching/WeeklyScheduleEditor.vue'
import { findLessonPeriod, lessonPeriods } from '@/constants/lessonPeriods'

const { requestJson } = useApi()
const activeTab = ref('calendar')
const years = ref([])
const terms = ref([])
const courses = ref([])
const schedules = ref([])
const cameras = ref([])
const bindings = ref([])
const classes = ref([])
const teachers = ref([])
const subjects = ref([])
const loading = ref(false)
const formOpen = ref(false)
const scheduleFormOpen = ref(false)
const scheduleBoard = ref(null)
const editing = ref(null)
const formType = ref('year')
const selectedScheduleClassId = ref(null)
const editingSchedule = ref(null)
const form = ref({})
const scheduleForm = ref({})

const titles = {
  year: ['学年', '学年名称'], term: ['学期', '学期名称'], course: ['教学课程', '课程名称'],
  camera: ['摄像设备', '设备编号'], binding: ['摄像头—班级绑定', '绑定关系'],
}
const modalTitle = computed(() => `${editing.value ? '编辑' : '新增'}${titles[formType.value][0]}`)
const weekdayOptions = [
  { value: 1, label: '周一' }, { value: 2, label: '周二' }, { value: 3, label: '周三' }, { value: 4, label: '周四' },
  { value: 5, label: '周五' }, { value: 6, label: '周六' }, { value: 7, label: '周日' },
]
const classScheduleSummaries = computed(() => {
  const schedulesByCourse = new Map()
  schedules.value.forEach((schedule) => {
    const count = schedulesByCourse.get(schedule.teaching_course_id) || 0
    schedulesByCourse.set(schedule.teaching_course_id, count + 1)
  })

  const summaries = new Map()
  courses.value.forEach((course) => {
    if (!summaries.has(course.class_id)) {
      summaries.set(course.class_id, {
        class_id: course.class_id,
        class_name: course.class_name || '未命名班级',
        course_count: 0,
        scheduled_lesson_count: 0,
        unassigned_course_count: 0,
        subject_names: new Set(),
      })
    }
    const summary = summaries.get(course.class_id)
    summary.course_count += 1
    summary.scheduled_lesson_count += schedulesByCourse.get(course.id) || 0
    summary.unassigned_course_count += course.teacher_id ? 0 : 1
    if (course.subject_name) summary.subject_names.add(course.subject_name)
  })

  return Array.from(summaries.values())
    .map(({ subject_names: subjectNames, ...summary }) => ({
      ...summary,
      subject_count: subjectNames.size,
      subject_names: Array.from(subjectNames).join('、') || '未设置',
    }))
    .sort((left, right) => left.class_name.localeCompare(right.class_name, 'zh-CN'))
})

const selectedClassCourses = computed(() => courses.value.filter(
  course => Number(course.class_id) === Number(selectedScheduleClassId.value),
))

const scheduleCourseOptions = computed(() => (
  selectedClassCourses.value.length ? selectedClassCourses.value : courses.value
))

async function loadData() {
  loading.value = true
  try {
    const [yearData, termData, courseData, scheduleData, cameraData, bindingData, classData, teacherData, subjectData] = await Promise.all([
      requestJson('/api/admin/academic-years'), requestJson('/api/admin/academic-terms'), requestJson('/api/admin/teaching-courses'),
      requestJson('/api/admin/schedules'),
      requestJson('/api/admin/cameras'), requestJson('/api/admin/camera-class-bindings'), requestJson('/api/admin/classes'),
      requestJson('/api/admin/teachers'), requestJson('/api/admin/subjects'),
    ])
    years.value = yearData.items || []
    terms.value = termData.items || []
    courses.value = courseData.items || []
    schedules.value = scheduleData.items || []
    cameras.value = cameraData.items || []
    bindings.value = bindingData.items || []
    classes.value = classData.classes || []
    teachers.value = (teacherData.teachers || []).filter((item) => item.status === 'ENABLED')
    subjects.value = subjectData.items || []
    if (!classScheduleSummaries.value.some(
      summary => Number(summary.class_id) === Number(selectedScheduleClassId.value),
    )) {
      selectedScheduleClassId.value = classScheduleSummaries.value[0]?.class_id || null
    }
  } catch (error) {
    message.error(error.message || '教学配置加载失败')
  } finally {
    loading.value = false
  }
}

function openForm(type, row = null) {
  formType.value = type
  editing.value = row
  if (row) {
    form.value = { ...row, enabled: row.enabled ?? row.status === 'ENABLED' }
  } else if (type === 'year') {
    form.value = { year_name: '', start_date: '', end_date: '', status: 'ENABLED' }
  } else if (type === 'term') {
    form.value = { academic_year_id: years.value[0]?.id, term_name: '', start_date: '', end_date: '', status: 'ENABLED' }
  } else if (type === 'course') {
    form.value = { course_no: '', term_id: terms.value[0]?.id, class_id: undefined, subject_id: undefined, teacher_id: undefined, course_name: '', planned_lesson_count: undefined, start_date: '', end_date: '', status: 'DRAFT' }
  } else if (type === 'camera') {
    form.value = { device_code: '', device_name: '', location: '', source_path: '', enabled: true, remark: '' }
  } else {
    form.value = { camera_id: cameras.value[0]?.id, class_id: undefined, effective_start_date: '', effective_end_date: '', enabled: true, remark: '' }
  }
  formOpen.value = true
}

function endpoint(type, id = null) {
  const base = { year: '/api/admin/academic-years', term: '/api/admin/academic-terms', course: '/api/admin/teaching-courses', camera: '/api/admin/cameras', binding: '/api/admin/camera-class-bindings' }[type]
  return id ? `${base}/${id}` : base
}

async function saveForm() {
  const type = formType.value
  const required = {
    year: ['year_name', 'start_date', 'end_date'], term: ['academic_year_id', 'term_name', 'start_date', 'end_date'],
    course: ['term_id', 'class_id', 'subject_id', 'course_name'], camera: ['device_code', 'device_name'],
    binding: ['camera_id', 'class_id', 'effective_start_date'],
  }[type]
  if (required.some((key) => form.value[key] === undefined || form.value[key] === null || form.value[key] === '')) {
    message.warning('请填写必填信息')
    return
  }
  try {
    await requestJson(endpoint(type, editing.value?.id), {
      method: editing.value ? 'PUT' : 'POST',
      body: JSON.stringify(form.value),
    })
    message.success(`${titles[type][0]}已保存`)
    formOpen.value = false
    await loadData()
  } catch (error) {
    message.error(error.message || '保存失败')
  }
}

function buildScheduleForm(seed = {}) {
  const period = lessonPeriods.find((item) => item.value === seed.lesson_period)
    || findLessonPeriod(seed.start_time || lessonPeriods[0].start_time)
  return {
    teaching_course_id: seed.teaching_course_id ?? selectedClassCourses.value[0]?.id ?? courses.value[0]?.id,
    weekday: seed.weekday ?? 1,
    lesson_period: period.value,
    start_time: seed.start_time || period.start_time,
    end_time: seed.end_time || period.end_time,
    lesson_title: seed.lesson_title || '',
    enabled: seed.enabled ?? true,
  }
}

function applyLessonPeriod(value) {
  const period = lessonPeriods.find((item) => item.value === value)
  if (!period) return
  scheduleForm.value.lesson_period = period.value
  // 节次是管理员唯一需要维护的排课维度，底层时间仅供课次调度服务匹配。
  scheduleForm.value.start_time = period.start_time
  scheduleForm.value.end_time = period.end_time
}

function showSchedules(courseOrClass) {
  selectedScheduleClassId.value = courseOrClass.class_id
  nextTick(() => scheduleBoard.value?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
}

function openScheduleForm(seed = {}) {
  if (!courses.value.length) {
    message.warning('请先新增教学课程')
    return
  }
  editingSchedule.value = null
  scheduleForm.value = buildScheduleForm(seed)
  scheduleFormOpen.value = true
}

async function saveSchedule() {
  const { lesson_period: lessonPeriod, ...payload } = scheduleForm.value
  const period = lessonPeriods.find((item) => item.value === lessonPeriod)
  if (!payload.teaching_course_id || !period) {
    message.warning('请选择教学课程和课次')
    return
  }
  payload.start_time = period.start_time
  payload.end_time = period.end_time
  try {
    await requestJson(editingSchedule.value ? `/api/admin/schedules/${editingSchedule.value.id}` : '/api/admin/schedules', {
      method: editingSchedule.value ? 'PUT' : 'POST', body: JSON.stringify(payload),
    })
    message.success('课表已保存')
    scheduleFormOpen.value = false
    await loadData()
  } catch (error) {
    message.error(error.message || '课表保存失败')
  }
}

function editSchedule(row) {
  editingSchedule.value = row
  scheduleForm.value = buildScheduleForm(row)
  scheduleFormOpen.value = true
}

function statusText(value) { return { DRAFT: '筹备中', ACTIVE: '进行中', FINISHED: '已结束', ARCHIVED: '已归档', ENABLED: '启用', DISABLED: '停用' }[value] || value }
</script>

<template>
  <div class="setup-view">
    <header class="page-head">
      <div><h1>教学与设备配置</h1><p>维护学年学期、教学课程、固定摄像设备及班级绑定关系。</p></div>
      <a-button @click="loadData">刷新</a-button>
    </header>

    <a-spin :spinning="loading">
      <a-tabs v-model:active-key="activeTab">
        <a-tab-pane key="calendar" tab="学年与学期">
          <section class="panel"><div class="toolbar"><span>学年</span><a-button type="primary" @click="openForm('year')">新增学年</a-button></div>
            <a-table :data-source="years" :pagination="false" row-key="id" size="small" :columns="[{ title: '学年', dataIndex: 'year_name' }, { title: '开始', dataIndex: 'start_date' }, { title: '结束', dataIndex: 'end_date' }, { title: '状态', dataIndex: 'status' }, { title: '操作', key: 'action' }]">
              <template #bodyCell="{ column, record }"><template v-if="column.dataIndex === 'status'"><a-tag :color="record.status === 'ENABLED' ? 'green' : 'default'">{{ statusText(record.status) }}</a-tag></template><template v-else-if="column.key === 'action'"><a-button type="link" @click="openForm('year', record)">编辑</a-button></template></template>
            </a-table>
          </section>
          <section class="panel"><div class="toolbar"><span>学期</span><a-button type="primary" :disabled="!years.length" @click="openForm('term')">新增学期</a-button></div>
            <a-table :data-source="terms" :pagination="false" row-key="id" size="small" :columns="[{ title: '所属学年', dataIndex: 'academic_year_name' }, { title: '学期', dataIndex: 'term_name' }, { title: '开始', dataIndex: 'start_date' }, { title: '结束', dataIndex: 'end_date' }, { title: '状态', dataIndex: 'status' }, { title: '操作', key: 'action' }]">
              <template #bodyCell="{ column, record }"><template v-if="column.dataIndex === 'status'"><a-tag :color="record.status === 'ENABLED' ? 'green' : 'default'">{{ statusText(record.status) }}</a-tag></template><template v-else-if="column.key === 'action'"><a-button type="link" @click="openForm('term', record)">编辑</a-button></template></template>
            </a-table>
          </section>
        </a-tab-pane>

        <a-tab-pane key="courses" tab="教学课程与课表">
          <section class="panel"><div class="toolbar"><span>按班级汇总课程配置；选择班级后查看其完整固定周课表。</span><a-button type="primary" :disabled="!terms.length" @click="openForm('course')">新增教学课程</a-button></div>
            <a-table :data-source="classScheduleSummaries" :pagination="false" row-key="class_id" size="small" :columns="[{ title: '班级', dataIndex: 'class_name' }, { title: '教学课程', dataIndex: 'course_count' }, { title: '覆盖科目', dataIndex: 'subject_names' }, { title: '已排课节数', dataIndex: 'scheduled_lesson_count' }, { title: '待分配课程', dataIndex: 'unassigned_course_count' }, { title: '操作', key: 'action' }]">
              <template #bodyCell="{ column, record }"><template v-if="column.key === 'action'"><a-button type="link" @click="showSchedules(record)">查看课表</a-button></template></template>
            </a-table>
          </section>
          <section ref="scheduleBoard" class="panel schedule-panel">
            <WeeklyScheduleEditor
              v-model:selected-class-id="selectedScheduleClassId"
              :courses="courses"
              :schedules="schedules"
              @create="openScheduleForm"
              @edit="editSchedule"
            />
          </section>
          <section v-if="selectedScheduleClassId" class="panel"><div class="toolbar"><span>{{ selectedClassCourses[0]?.class_name || '当前班级' }}的教学课程</span></div>
            <a-table :data-source="selectedClassCourses" :pagination="false" row-key="id" size="small" :columns="[{ title: '课程名称', dataIndex: 'course_name' }, { title: '学期', dataIndex: 'term_name' }, { title: '科目', dataIndex: 'subject_name' }, { title: '教师', dataIndex: 'teacher_name' }, { title: '状态', dataIndex: 'status' }, { title: '操作', key: 'action' }]">
              <template #bodyCell="{ column, record }"><template v-if="column.dataIndex === 'status'"><a-tag :color="record.status === 'ACTIVE' ? 'green' : 'default'">{{ statusText(record.status) }}</a-tag></template><template v-else-if="column.dataIndex === 'teacher_name'">{{ record.teacher_name || '未分配' }}</template><template v-else-if="column.key === 'action'"><a-space><a-button type="link" @click="openForm('course', record)">编辑</a-button><a-button type="link" @click="showSchedules(record)">查看课表</a-button></a-space></template></template>
            </a-table>
          </section>
        </a-tab-pane>

        <a-tab-pane key="cameras" tab="摄像设备">
          <section class="panel"><div class="toolbar"><span>摄像设备固定安装，视频来源仅为内部运行配置。</span><a-button type="primary" @click="openForm('camera')">新增设备</a-button></div>
            <a-table :data-source="cameras" :pagination="false" row-key="id" size="small" :columns="[{ title: '设备编号', dataIndex: 'device_code' }, { title: '设备名称', dataIndex: 'device_name' }, { title: '安装位置', dataIndex: 'location' }, { title: '状态', key: 'enabled' }, { title: '操作', key: 'action' }]">
              <template #bodyCell="{ column, record }"><template v-if="column.key === 'enabled'"><a-tag :color="record.enabled ? 'green' : 'default'">{{ record.enabled ? '启用' : '停用' }}</a-tag></template><template v-else-if="column.key === 'action'"><a-button type="link" @click="openForm('camera', record)">编辑</a-button></template></template>
            </a-table>
          </section>
        </a-tab-pane>

        <a-tab-pane key="bindings" tab="摄像头—班级绑定">
          <section class="panel"><div class="toolbar"><span>班级调整时结束旧绑定、新建绑定，保留历史归属。</span><a-button type="primary" :disabled="!cameras.length || !classes.length" @click="openForm('binding')">新增绑定</a-button></div>
            <a-table :data-source="bindings" :pagination="false" row-key="id" size="small" :columns="[{ title: '摄像设备', dataIndex: 'camera_name' }, { title: '服务班级', dataIndex: 'class_name' }, { title: '开始日期', dataIndex: 'effective_start_date' }, { title: '结束日期', dataIndex: 'effective_end_date' }, { title: '状态', key: 'enabled' }, { title: '操作', key: 'action' }]">
              <template #bodyCell="{ column, record }"><template v-if="column.key === 'enabled'"><a-tag :color="record.enabled ? 'green' : 'default'">{{ record.enabled ? '启用' : '停用' }}</a-tag></template><template v-else-if="column.key === 'action'"><a-button type="link" @click="openForm('binding', record)">编辑</a-button></template></template>
            </a-table>
          </section>
        </a-tab-pane>
      </a-tabs>
    </a-spin>

    <a-modal v-model:open="formOpen" :title="modalTitle" :width="680" @ok="saveForm">
      <a-form layout="vertical" class="modal-form">
        <template v-if="formType === 'year'"><a-form-item label="学年名称"><a-input v-model:value="form.year_name" placeholder="例如：2026-2027" /></a-form-item><a-form-item label="开始日期"><a-input v-model:value="form.start_date" placeholder="YYYY-MM-DD" /></a-form-item><a-form-item label="结束日期"><a-input v-model:value="form.end_date" placeholder="YYYY-MM-DD" /></a-form-item><a-form-item label="状态"><a-select v-model:value="form.status"><a-select-option value="ENABLED">启用</a-select-option><a-select-option value="DISABLED">停用</a-select-option></a-select></a-form-item></template>
        <template v-else-if="formType === 'term'"><a-form-item label="所属学年"><a-select v-model:value="form.academic_year_id"><a-select-option v-for="item in years" :key="item.id" :value="item.id">{{ item.year_name }}</a-select-option></a-select></a-form-item><a-form-item label="学期名称"><a-input v-model:value="form.term_name" placeholder="例如：第一学期" /></a-form-item><a-form-item label="开始日期"><a-input v-model:value="form.start_date" placeholder="YYYY-MM-DD" /></a-form-item><a-form-item label="结束日期"><a-input v-model:value="form.end_date" placeholder="YYYY-MM-DD" /></a-form-item><a-form-item label="状态"><a-select v-model:value="form.status"><a-select-option value="ENABLED">启用</a-select-option><a-select-option value="DISABLED">停用</a-select-option></a-select></a-form-item></template>
        <template v-else-if="formType === 'course'"><a-form-item label="课程编号"><a-input v-model:value="form.course_no" placeholder="留空自动生成" /></a-form-item><a-form-item label="所属学期"><a-select v-model:value="form.term_id"><a-select-option v-for="item in terms" :key="item.id" :value="item.id">{{ item.academic_year_name }} · {{ item.term_name }}</a-select-option></a-select></a-form-item><a-form-item label="授课班级"><a-select v-model:value="form.class_id"><a-select-option v-for="item in classes" :key="item.id" :value="item.id">{{ item.class_name }}</a-select-option></a-select></a-form-item><a-form-item label="授课科目"><a-select v-model:value="form.subject_id"><a-select-option v-for="item in subjects" :key="item.id" :value="item.id">{{ item.subject_name }}</a-select-option></a-select></a-form-item><a-form-item label="任课教师"><a-select v-model:value="form.teacher_id" allow-clear placeholder="暂不分配，可后续补充"><a-select-option v-for="item in teachers" :key="item.id" :value="item.id">{{ item.teacher_name }}</a-select-option></a-select></a-form-item><a-form-item label="课程名称"><a-input v-model:value="form.course_name" /></a-form-item><a-form-item label="计划课次"><a-input-number v-model:value="form.planned_lesson_count" :min="1" style="width: 100%" /></a-form-item><a-form-item label="开始日期"><a-input v-model:value="form.start_date" placeholder="可选，YYYY-MM-DD" /></a-form-item><a-form-item label="结束日期"><a-input v-model:value="form.end_date" placeholder="可选，YYYY-MM-DD" /></a-form-item><a-form-item label="状态"><a-select v-model:value="form.status"><a-select-option value="DRAFT">筹备中</a-select-option><a-select-option value="ACTIVE">进行中</a-select-option><a-select-option value="FINISHED">已结束</a-select-option><a-select-option value="ARCHIVED">已归档</a-select-option></a-select></a-form-item></template>
        <template v-else-if="formType === 'camera'"><a-form-item label="设备编号"><a-input v-model:value="form.device_code" /></a-form-item><a-form-item label="设备名称"><a-input v-model:value="form.device_name" /></a-form-item><a-form-item label="安装位置"><a-input v-model:value="form.location" /></a-form-item><a-form-item label="内部来源"><a-input v-model:value="form.source_path" placeholder="内部配置，不在教师端展示" /></a-form-item><a-form-item label="备注"><a-textarea v-model:value="form.remark" :rows="2" /></a-form-item><a-form-item label="启用状态"><a-switch v-model:checked="form.enabled" checked-children="启用" un-checked-children="停用" /></a-form-item></template>
        <template v-else><a-form-item label="摄像设备"><a-select v-model:value="form.camera_id"><a-select-option v-for="item in cameras" :key="item.id" :value="item.id">{{ item.device_code }} · {{ item.device_name }}</a-select-option></a-select></a-form-item><a-form-item label="服务班级"><a-select v-model:value="form.class_id"><a-select-option v-for="item in classes" :key="item.id" :value="item.id">{{ item.class_name }}</a-select-option></a-select></a-form-item><a-form-item label="生效开始"><a-input v-model:value="form.effective_start_date" placeholder="YYYY-MM-DD" /></a-form-item><a-form-item label="生效结束"><a-input v-model:value="form.effective_end_date" placeholder="可选，YYYY-MM-DD" /></a-form-item><a-form-item label="变更说明"><a-textarea v-model:value="form.remark" :rows="2" /></a-form-item><a-form-item label="启用状态"><a-switch v-model:checked="form.enabled" checked-children="启用" un-checked-children="停用" /></a-form-item></template>
      </a-form>
    </a-modal>

    <a-modal v-model:open="scheduleFormOpen" :title="editingSchedule ? '编辑固定课次' : '新增固定课次'" :width="640" @ok="saveSchedule">
      <a-form layout="vertical" class="modal-form">
        <a-form-item label="教学课程"><a-select v-model:value="scheduleForm.teaching_course_id"><a-select-option v-for="course in scheduleCourseOptions" :key="course.id" :value="course.id">{{ course.course_name }} · {{ course.class_name }} · {{ course.teacher_name || '未分配' }}</a-select-option></a-select></a-form-item>
        <a-form-item label="星期"><a-select v-model:value="scheduleForm.weekday"><a-select-option v-for="item in weekdayOptions" :key="item.value" :value="item.value">{{ item.label }}</a-select-option></a-select></a-form-item>
        <a-form-item label="课次"><a-select v-model:value="scheduleForm.lesson_period" @update:value="applyLessonPeriod"><a-select-option v-for="item in lessonPeriods" :key="item.value" :value="item.value">{{ item.session }}{{ item.label }}</a-select-option></a-select></a-form-item>
        <a-form-item label="排课说明"><span class="schedule-time-preview">课次时段将按校内默认作息自动用于监控课次生成。</span></a-form-item>
        <a-form-item label="课程主题"><a-input v-model:value="scheduleForm.lesson_title" placeholder="可选，例如：第 3 课时" /></a-form-item>
        <a-form-item label="启用状态"><a-switch v-model:checked="scheduleForm.enabled" checked-children="启用" un-checked-children="停用" /></a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<style scoped>
.setup-view { height: 100%; padding: 20px; overflow: auto; }
.page-head, .toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.page-head { margin-bottom: 16px; }
h1, p { margin: 0; }
h1 { color: var(--text-primary); font-size: 24px; }
p { margin-top: 6px; color: var(--text-muted); }
.panel { margin-bottom: 16px; padding: 16px; border: 1px solid var(--border-default); border-radius: var(--radius-lg); background: var(--bg-card); }
.toolbar { margin-bottom: 12px; color: var(--text-secondary); }
.schedule-panel { padding-bottom: 20px; }
.schedule-time-preview { color: var(--text-muted); font-size: 13px; }
@media (max-width: 760px) { .page-head, .toolbar { align-items: flex-start; flex-direction: column; } }
</style>
