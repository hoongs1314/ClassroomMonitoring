<script setup>
import { computed } from 'vue'
import { findLessonPeriod, lessonPeriodsBySession } from '@/constants/lessonPeriods'

const props = defineProps({
  courses: { type: Array, default: () => [] },
  schedules: { type: Array, default: () => [] },
  selectedClassId: { type: [Number, String], default: null },
})

const emit = defineEmits(['create', 'edit', 'update:selectedClassId'])

const weekdays = [
  { value: 1, label: '周一' }, { value: 2, label: '周二' }, { value: 3, label: '周三' }, { value: 4, label: '周四' },
  { value: 5, label: '周五' }, { value: 6, label: '周六' }, { value: 7, label: '周日' },
]

const courseById = computed(() => new Map(props.courses.map((course) => [course.id, course])))
const classOptions = computed(() => {
  const classMap = new Map()
  props.courses.forEach((course) => {
    if (!classMap.has(course.class_id)) {
      classMap.set(course.class_id, {
        id: course.class_id,
        name: course.class_name || '未命名班级',
      })
    }
  })
  return Array.from(classMap.values())
})

const selectedClassCourses = computed(() => props.courses.filter(
  course => Number(course.class_id) === Number(props.selectedClassId),
))

const visibleSchedules = computed(() => {
  if (!props.selectedClassId) return []
  const courseIds = new Set(selectedClassCourses.value.map(course => Number(course.id)))
  return props.schedules.filter(schedule => courseIds.has(Number(schedule.teaching_course_id)))
})

function courseTitle(schedule) {
  return courseById.value.get(schedule.teaching_course_id)?.course_name || '未命名教学课程'
}

function courseMeta(schedule) {
  const course = courseById.value.get(schedule.teaching_course_id)
  return [course?.class_name, course?.teacher_name].filter(Boolean).join(' · ')
}

function scheduleHint(schedule) {
  const period = findLessonPeriod(schedule.start_time)
  return [
    courseTitle(schedule),
    courseMeta(schedule),
    `${period.session}${period.label}（${schedule.start_time}–${schedule.end_time}）`,
    schedule.lesson_title,
  ].filter(Boolean).join('\n')
}

function courseColor(schedule) {
  const colors = ['#2f80ed', '#19a974', '#9b51e0', '#e67e22', '#eb5757', '#00a8a8', '#5470c6']
  return colors[Number(schedule.teaching_course_id) % colors.length]
}

function schedulesForSlot(weekday, period) {
  return visibleSchedules.value.filter((schedule) => (
    schedule.weekday === weekday && findLessonPeriod(schedule.start_time).value === period.value
  ))
}

function handleSlotClick(weekday, period) {
  if (!selectedClassCourses.value.length) return
  emit('create', {
    weekday,
    lesson_period: period.value,
    start_time: period.start_time,
    end_time: period.end_time,
  })
}

function updateFilter(value) {
  emit('update:selectedClassId', value || null)
}
</script>

<template>
  <div class="weekly-schedule-editor">
    <div class="schedule-toolbar">
      <div>
        <h2>固定周课表</h2>
        <p>按班级查看固定周课表；点击空白课次新增，点击课程卡片编辑。</p>
      </div>
      <a-space wrap>
        <a-select
          :value="selectedClassId"
          placeholder="请选择班级"
          style="width: 240px"
          @update:value="updateFilter"
        >
          <a-select-option v-for="classItem in classOptions" :key="classItem.id" :value="classItem.id">
            {{ classItem.name }}
          </a-select-option>
        </a-select>
        <a-button type="primary" :disabled="!selectedClassCourses.length" @click="emit('create', {})">新增课次</a-button>
      </a-space>
    </div>

    <a-empty v-if="!courses.length" description="请先新增教学课程，再维护固定周课表" />
    <div v-else class="timetable-scroll">
      <div class="week-header">
        <div class="period-header">课次</div>
        <div v-for="day in weekdays" :key="day.value" class="day-header">{{ day.label }}</div>
      </div>
      <section v-for="group in lessonPeriodsBySession" :key="group.label" class="period-section">
        <div class="session-label">{{ group.label }}</div>
        <div v-for="period in group.periods" :key="period.value" class="period-row">
          <div class="period-label">
            <strong>{{ period.label }}</strong>
            <span>{{ period.start_time }}–{{ period.end_time }}</span>
          </div>
          <div
            v-for="day in weekdays"
            :key="day.value"
            class="lesson-cell"
            @click="handleSlotClick(day.value, period)"
          >
            <button
              v-for="schedule in schedulesForSlot(day.value, period)"
              :key="schedule.id"
              type="button"
              class="schedule-card"
              :class="{ disabled: !schedule.enabled }"
              :style="{ '--schedule-color': courseColor(schedule) }"
              :title="scheduleHint(schedule)"
              @click.stop="emit('edit', schedule)"
            >
              <strong>{{ courseTitle(schedule) }}</strong>
              <small v-if="schedule.lesson_title">{{ schedule.lesson_title }}</small>
              <em v-if="!schedule.enabled">已停用</em>
            </button>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.schedule-toolbar { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 16px; }
.schedule-toolbar h2, .schedule-toolbar p { margin: 0; }
.schedule-toolbar h2 { color: var(--text-primary); font-size: 17px; }
.schedule-toolbar p { margin-top: 5px; color: var(--text-muted); font-size: 13px; }
.timetable-scroll { overflow: auto; border: 1px solid var(--border-default); border-radius: var(--radius-md); }
.week-header, .period-row { display: grid; grid-template-columns: 96px repeat(7, minmax(172px, 1fr)); min-width: 1300px; }
.week-header { position: sticky; top: 0; z-index: 3; background: var(--bg-card); border-bottom: 1px solid var(--border-default); }
.period-header, .day-header { padding: 10px 8px; color: var(--text-secondary); font-size: 13px; font-weight: 600; text-align: center; }
.day-header, .lesson-cell { border-left: 1px solid var(--border-default); }
.period-section + .period-section { border-top: 2px solid var(--border-default); }
.session-label { padding: 8px 12px; color: var(--text-secondary); font-size: 13px; font-weight: 600; background: var(--bg-elevated); border-bottom: 1px solid var(--border-default); }
.period-row { border-bottom: 1px solid var(--border-default); }
.period-label { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px; min-height: 94px; padding: 8px; color: var(--text-secondary); text-align: center; background: var(--bg-elevated); }
.period-label strong { color: var(--text-primary); font-size: 13px; }
.period-label span { font-size: 11px; }
.lesson-cell { display: flex; flex-direction: column; gap: 6px; min-height: 94px; padding: 7px; cursor: crosshair; background: var(--bg-card); }
.lesson-cell:hover { background: color-mix(in srgb, var(--color-primary) 4%, var(--bg-card)); }
.schedule-card { display: flex; flex-direction: column; width: 100%; min-width: 0; min-height: 54px; padding: 9px 10px; color: var(--text-primary); text-align: left; cursor: pointer; background: color-mix(in srgb, var(--schedule-color) 12%, var(--bg-card)); border: 1px solid color-mix(in srgb, var(--schedule-color) 55%, var(--border-default)); border-left: 4px solid var(--schedule-color); border-radius: 6px; box-shadow: 0 1px 4px rgb(15 23 42 / 8%); }
.schedule-card:hover { z-index: 2; box-shadow: 0 4px 10px rgb(15 23 42 / 15%); transform: translateY(-1px); }
.schedule-card strong { display: -webkit-box; overflow: hidden; color: var(--text-primary); font-size: 14px; line-height: 1.35; text-overflow: ellipsis; -webkit-line-clamp: 2; -webkit-box-orient: vertical; word-break: break-word; }
.schedule-card small { overflow: hidden; margin-top: 3px; color: var(--text-secondary); font-size: 11px; line-height: 1.35; text-overflow: ellipsis; white-space: nowrap; }
.schedule-card em { margin-top: 3px; color: var(--text-muted); font-size: 11px; font-style: normal; }
.schedule-card.disabled { opacity: 0.55; filter: grayscale(0.4); }
.schedule-card:focus-visible { outline: 2px solid var(--schedule-color); outline-offset: 2px; }
@media (max-width: 760px) { .schedule-toolbar { flex-direction: column; } }
</style>
