-- 清空教学配置和课程分析数据，保留账号、教师档案与监控历史。
-- 生成高三1班、高三2班的完整周课表；课程不分配任课教师。

SET NAMES utf8mb4 COLLATE utf8mb4_general_ci;

-- 教学课程允许先排课、后分配教师；外键仍保留，后续分配时会校验教师存在。
ALTER TABLE teaching_course
  MODIFY COLUMN teacher_id BIGINT UNSIGNED NULL COMMENT 'Teacher ID, assigned after schedule setup when needed';

CREATE TEMPORARY TABLE tmp_unassigned_timetable (
  class_code VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  subject_code VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  weekday TINYINT UNSIGNED NOT NULL,
  lesson_period TINYINT UNSIGNED NOT NULL
);

INSERT INTO tmp_unassigned_timetable (class_code, subject_code, weekday, lesson_period) VALUES
  ('G3_01', 'CHINESE', 1, 1), ('G3_01', 'MATH', 1, 2), ('G3_01', 'ENGLISH', 1, 3), ('G3_01', 'PHYSICS', 1, 4), ('G3_01', 'CHEMISTRY', 1, 5), ('G3_01', 'PE', 1, 6), ('G3_01', 'MATH', 1, 7),
  ('G3_01', 'MATH', 2, 1), ('G3_01', 'CHINESE', 2, 2), ('G3_01', 'ENGLISH', 2, 3), ('G3_01', 'BIOLOGY', 2, 4), ('G3_01', 'PHYSICS', 2, 5), ('G3_01', 'HISTORY', 2, 6), ('G3_01', 'ENGLISH', 2, 7),
  ('G3_01', 'ENGLISH', 3, 1), ('G3_01', 'MATH', 3, 2), ('G3_01', 'CHINESE', 3, 3), ('G3_01', 'CHEMISTRY', 3, 4), ('G3_01', 'POLITICS', 3, 5), ('G3_01', 'PE', 3, 6), ('G3_01', 'GEOGRAPHY', 3, 7),
  ('G3_01', 'CHINESE', 4, 1), ('G3_01', 'ENGLISH', 4, 2), ('G3_01', 'MATH', 4, 3), ('G3_01', 'BIOLOGY', 4, 4), ('G3_01', 'PHYSICS', 4, 5), ('G3_01', 'HISTORY', 4, 6), ('G3_01', 'MATH', 4, 7),
  ('G3_01', 'MATH', 5, 1), ('G3_01', 'CHINESE', 5, 2), ('G3_01', 'ENGLISH', 5, 3), ('G3_01', 'CHEMISTRY', 5, 4), ('G3_01', 'POLITICS', 5, 5), ('G3_01', 'GEOGRAPHY', 5, 6), ('G3_01', 'CLASS_MEETING', 5, 7),
  ('G3_02', 'MATH', 1, 1), ('G3_02', 'CHINESE', 1, 2), ('G3_02', 'ENGLISH', 1, 3), ('G3_02', 'CHEMISTRY', 1, 4), ('G3_02', 'PHYSICS', 1, 5), ('G3_02', 'PE', 1, 6), ('G3_02', 'ENGLISH', 1, 7),
  ('G3_02', 'CHINESE', 2, 1), ('G3_02', 'MATH', 2, 2), ('G3_02', 'ENGLISH', 2, 3), ('G3_02', 'BIOLOGY', 2, 4), ('G3_02', 'CHEMISTRY', 2, 5), ('G3_02', 'HISTORY', 2, 6), ('G3_02', 'MATH', 2, 7),
  ('G3_02', 'ENGLISH', 3, 1), ('G3_02', 'CHINESE', 3, 2), ('G3_02', 'MATH', 3, 3), ('G3_02', 'PHYSICS', 3, 4), ('G3_02', 'POLITICS', 3, 5), ('G3_02', 'PE', 3, 6), ('G3_02', 'GEOGRAPHY', 3, 7),
  ('G3_02', 'MATH', 4, 1), ('G3_02', 'ENGLISH', 4, 2), ('G3_02', 'CHINESE', 4, 3), ('G3_02', 'BIOLOGY', 4, 4), ('G3_02', 'CHEMISTRY', 4, 5), ('G3_02', 'HISTORY', 4, 6), ('G3_02', 'ENGLISH', 4, 7),
  ('G3_02', 'CHINESE', 5, 1), ('G3_02', 'MATH', 5, 2), ('G3_02', 'ENGLISH', 5, 3), ('G3_02', 'PHYSICS', 5, 4), ('G3_02', 'POLITICS', 5, 5), ('G3_02', 'GEOGRAPHY', 5, 6), ('G3_02', 'CLASS_MEETING', 5, 7);

START TRANSACTION;

-- 删除课程分析链路，保留 monitor_session 及其事件、截图和复核记录。
DELETE FROM teaching_improvement_action;
DELETE FROM teaching_report_evidence;
DELETE FROM teaching_analysis_report;
DELETE FROM course_analysis_entry;
DELETE FROM course_aggregate_source;
DELETE FROM course_behavior_stat;
DELETE FROM course_analysis_aggregate;

-- 历史课次保留快照名称，但不再关联已清理的课程、课表与学期。
UPDATE monitor_session
SET teaching_course_id = NULL, schedule_id = NULL, term_id = NULL;

DELETE FROM edu_lesson_schedule;
DELETE FROM teaching_course;
DELETE FROM edu_teacher_class;
DELETE FROM camera_class_binding;
DELETE FROM edu_academic_term;
DELETE FROM edu_academic_year;

-- 历史课次和行为事件引用的班级不能物理删除；无历史引用的旧班级可以安全清理。
DELETE cls
FROM edu_class cls
LEFT JOIN monitor_session session ON session.class_id = cls.id
LEFT JOIN monitor_behavior_event event ON event.class_id = cls.id
WHERE session.id IS NULL AND event.id IS NULL;

UPDATE edu_class
SET enabled = 0, head_teacher_id = NULL, default_video_path = NULL;

INSERT INTO edu_class (class_code, class_name, grade_name, academic_year, enabled)
VALUES
  ('G3_01', '高三1班', '高三', '2026-2027', 1),
  ('G3_02', '高三2班', '高三', '2026-2027', 1)
ON DUPLICATE KEY UPDATE
  class_name = VALUES(class_name), grade_name = VALUES(grade_name), academic_year = VALUES(academic_year),
  head_teacher_id = NULL, default_video_path = NULL, enabled = 1;

-- 保留历史课次仍引用的科目字典，其余旧科目清理后重建为完整的课程科目集。
DELETE subject
FROM edu_subject subject
LEFT JOIN monitor_session session ON session.subject_id = subject.id
WHERE session.id IS NULL;

INSERT INTO edu_subject (subject_code, subject_name, enabled) VALUES
  ('CHINESE', '语文', 1), ('MATH', '数学', 1), ('ENGLISH', '英语', 1), ('PHYSICS', '物理', 1),
  ('CHEMISTRY', '化学', 1), ('BIOLOGY', '生物', 1), ('POLITICS', '政治', 1), ('HISTORY', '历史', 1),
  ('GEOGRAPHY', '地理', 1), ('PE', '体育', 1), ('CLASS_MEETING', '班会', 1)
ON DUPLICATE KEY UPDATE subject_name = VALUES(subject_name), enabled = 1;

INSERT INTO edu_academic_year (year_name, start_date, end_date, status)
VALUES ('2026-2027学年', '2026-09-01', '2027-08-31', 'ENABLED');

SET @year_id = LAST_INSERT_ID();

INSERT INTO edu_academic_term (academic_year_id, term_name, start_date, end_date, status)
VALUES (@year_id, '第一学期', '2026-09-01', '2027-01-31', 'ENABLED');

SET @term_id = LAST_INSERT_ID();

INSERT INTO teaching_course (
  course_no, term_id, class_id, subject_id, teacher_id, course_name,
  planned_lesson_count, start_date, end_date, status
)
SELECT
  CONCAT('UNASSIGNED-', plan.class_code, '-', plan.subject_code), @term_id, class.id, subject.id, NULL,
  CONCAT(class.class_name, subject.subject_name), plan.planned_lesson_count,
  term.start_date, term.end_date, 'ACTIVE'
FROM (
  SELECT class_code, subject_code, COUNT(*) AS planned_lesson_count
  FROM tmp_unassigned_timetable
  GROUP BY class_code, subject_code
) plan
JOIN edu_class class ON class.class_code = plan.class_code
JOIN edu_subject subject ON subject.subject_code = plan.subject_code
JOIN edu_academic_term term ON term.id = @term_id;

INSERT INTO edu_lesson_schedule (teaching_course_id, weekday, start_time, end_time, lesson_title, enabled)
SELECT
  course.id,
  timetable.weekday,
  CASE timetable.lesson_period
    WHEN 1 THEN '08:00' WHEN 2 THEN '09:00' WHEN 3 THEN '10:10' WHEN 4 THEN '11:05'
    WHEN 5 THEN '14:00' WHEN 6 THEN '14:55' WHEN 7 THEN '15:50'
  END,
  CASE timetable.lesson_period
    WHEN 1 THEN '08:45' WHEN 2 THEN '09:45' WHEN 3 THEN '10:55' WHEN 4 THEN '11:50'
    WHEN 5 THEN '14:45' WHEN 6 THEN '15:40' WHEN 7 THEN '16:35'
  END,
  CONCAT('第', timetable.lesson_period, '节'),
  1
FROM tmp_unassigned_timetable timetable
JOIN teaching_course course ON course.course_no = CONCAT('UNASSIGNED-', timetable.class_code, '-', timetable.subject_code);

COMMIT;

DROP TEMPORARY TABLE tmp_unassigned_timetable;
