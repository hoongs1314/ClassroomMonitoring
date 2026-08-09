export const lessonPeriods = Object.freeze([
  { value: 1, session: '上午', label: '第一节', start_time: '08:00', end_time: '08:45' },
  { value: 2, session: '上午', label: '第二节', start_time: '09:00', end_time: '09:45' },
  { value: 3, session: '上午', label: '第三节', start_time: '10:10', end_time: '10:55' },
  { value: 4, session: '上午', label: '第四节', start_time: '11:05', end_time: '11:50' },
  { value: 5, session: '下午', label: '第一节', start_time: '14:00', end_time: '14:45' },
  { value: 6, session: '下午', label: '第二节', start_time: '14:55', end_time: '15:40' },
  { value: 7, session: '下午', label: '第三节', start_time: '15:50', end_time: '16:35' },
])

export const lessonPeriodsBySession = Object.freeze([
  { label: '上午', periods: lessonPeriods.filter((item) => item.session === '上午') },
  { label: '下午', periods: lessonPeriods.filter((item) => item.session === '下午') },
])

function toMinutes(value) {
  const [hours, minutes] = String(value || '00:00').split(':').map(Number)
  return hours * 60 + minutes
}

export function findLessonPeriod(startTime) {
  const exact = lessonPeriods.find((item) => item.start_time === startTime)
  if (exact) return exact

  const target = toMinutes(startTime)
  return lessonPeriods.reduce((closest, item) => (
    Math.abs(toMinutes(item.start_time) - target) < Math.abs(toMinutes(closest.start_time) - target) ? item : closest
  ))
}
