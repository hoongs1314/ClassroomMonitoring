-- 根据“高三___班课程表”图片生成的可编辑示例数据。
-- 未从图片推断班级编号、真实教师、假期课时、摄像设备，因此分别采用示范编号、示例教师，
-- 不填计划总课时，也不创建摄像头绑定。自习、升旗、课间操、就餐和休息不作为学科课程导入。
-- 本脚本可重复执行：仅新增缺失的基础数据，并按课程、星期和开始时间更新既有课表项。

SET NAMES utf8mb4;

INSERT INTO edu_academic_year (year_name, start_date, end_date, status)
SELECT '2026-2027学年', '2026-09-01', '2027-08-31', 'ENABLED'
WHERE NOT EXISTS (
  SELECT 1 FROM edu_academic_year WHERE year_name = '2026-2027学年'
);

INSERT INTO edu_academic_term (academic_year_id, term_name, start_date, end_date, status)
SELECT year.id, '第一学期', '2026-09-01', '2027-01-31', 'ENABLED'
FROM edu_academic_year year
WHERE year.year_name = '2026-2027学年'
  AND NOT EXISTS (
    SELECT 1 FROM edu_academic_term term
    WHERE term.academic_year_id = year.id AND term.term_name = '第一学期'
  );

INSERT INTO edu_class (class_code, class_name, grade_name, academic_year, enabled)
SELECT 'G3_DEMO_01', '高三示范班', '高三', '2026-2027', 1
WHERE NOT EXISTS (
  SELECT 1 FROM edu_class WHERE class_code = 'G3_DEMO_01'
);

INSERT INTO edu_subject (subject_code, subject_name, enabled)
SELECT 'CHEMISTRY', '化学', 1
WHERE NOT EXISTS (SELECT 1 FROM edu_subject WHERE subject_code = 'CHEMISTRY');
INSERT INTO edu_subject (subject_code, subject_name, enabled)
SELECT 'BIOLOGY', '生物', 1
WHERE NOT EXISTS (SELECT 1 FROM edu_subject WHERE subject_code = 'BIOLOGY');
INSERT INTO edu_subject (subject_code, subject_name, enabled)
SELECT 'PHYSICAL_EDUCATION', '体育', 1
WHERE NOT EXISTS (SELECT 1 FROM edu_subject WHERE subject_code = 'PHYSICAL_EDUCATION');

INSERT INTO edu_teacher (teacher_no, teacher_name, department, status)
SELECT 'DEMO_G3_CHINESE', '高三语文示例教师', '高三年级组', 'ENABLED'
WHERE NOT EXISTS (SELECT 1 FROM edu_teacher WHERE teacher_no = 'DEMO_G3_CHINESE');
INSERT INTO edu_teacher (teacher_no, teacher_name, department, status)
SELECT 'DEMO_G3_MATH', '高三数学示例教师', '高三年级组', 'ENABLED'
WHERE NOT EXISTS (SELECT 1 FROM edu_teacher WHERE teacher_no = 'DEMO_G3_MATH');
INSERT INTO edu_teacher (teacher_no, teacher_name, department, status)
SELECT 'DEMO_G3_ENGLISH', '高三英语示例教师', '高三年级组', 'ENABLED'
WHERE NOT EXISTS (SELECT 1 FROM edu_teacher WHERE teacher_no = 'DEMO_G3_ENGLISH');
INSERT INTO edu_teacher (teacher_no, teacher_name, department, status)
SELECT 'DEMO_G3_PHYSICS', '高三物理示例教师', '高三年级组', 'ENABLED'
WHERE NOT EXISTS (SELECT 1 FROM edu_teacher WHERE teacher_no = 'DEMO_G3_PHYSICS');
INSERT INTO edu_teacher (teacher_no, teacher_name, department, status)
SELECT 'DEMO_G3_CHEMISTRY', '高三化学示例教师', '高三年级组', 'ENABLED'
WHERE NOT EXISTS (SELECT 1 FROM edu_teacher WHERE teacher_no = 'DEMO_G3_CHEMISTRY');
INSERT INTO edu_teacher (teacher_no, teacher_name, department, status)
SELECT 'DEMO_G3_BIOLOGY', '高三生物示例教师', '高三年级组', 'ENABLED'
WHERE NOT EXISTS (SELECT 1 FROM edu_teacher WHERE teacher_no = 'DEMO_G3_BIOLOGY');
INSERT INTO edu_teacher (teacher_no, teacher_name, department, status)
SELECT 'DEMO_G3_PE', '高三体育示例教师', '高三年级组', 'ENABLED'
WHERE NOT EXISTS (SELECT 1 FROM edu_teacher WHERE teacher_no = 'DEMO_G3_PE');

INSERT INTO teaching_course (course_no, term_id, class_id, subject_id, teacher_id, course_name, start_date, end_date, status)
SELECT 'G3-2026-01-CHINESE', term.id, class.id, subject.id, teacher.id, '高三示范班语文', term.start_date, term.end_date, 'ACTIVE'
FROM edu_academic_term term JOIN edu_class class JOIN edu_subject subject JOIN edu_teacher teacher
WHERE term.term_name = '第一学期' AND class.class_code = 'G3_DEMO_01' AND subject.subject_code = 'CHINESE' AND teacher.teacher_no = 'DEMO_G3_CHINESE'
  AND NOT EXISTS (SELECT 1 FROM teaching_course WHERE course_no = 'G3-2026-01-CHINESE');
INSERT INTO teaching_course (course_no, term_id, class_id, subject_id, teacher_id, course_name, start_date, end_date, status)
SELECT 'G3-2026-01-MATH', term.id, class.id, subject.id, teacher.id, '高三示范班数学', term.start_date, term.end_date, 'ACTIVE'
FROM edu_academic_term term JOIN edu_class class JOIN edu_subject subject JOIN edu_teacher teacher
WHERE term.term_name = '第一学期' AND class.class_code = 'G3_DEMO_01' AND subject.subject_code = 'MATH' AND teacher.teacher_no = 'DEMO_G3_MATH'
  AND NOT EXISTS (SELECT 1 FROM teaching_course WHERE course_no = 'G3-2026-01-MATH');
INSERT INTO teaching_course (course_no, term_id, class_id, subject_id, teacher_id, course_name, start_date, end_date, status)
SELECT 'G3-2026-01-ENGLISH', term.id, class.id, subject.id, teacher.id, '高三示范班英语', term.start_date, term.end_date, 'ACTIVE'
FROM edu_academic_term term JOIN edu_class class JOIN edu_subject subject JOIN edu_teacher teacher
WHERE term.term_name = '第一学期' AND class.class_code = 'G3_DEMO_01' AND subject.subject_code = 'ENGLISH' AND teacher.teacher_no = 'DEMO_G3_ENGLISH'
  AND NOT EXISTS (SELECT 1 FROM teaching_course WHERE course_no = 'G3-2026-01-ENGLISH');
INSERT INTO teaching_course (course_no, term_id, class_id, subject_id, teacher_id, course_name, start_date, end_date, status)
SELECT 'G3-2026-01-PHYSICS', term.id, class.id, subject.id, teacher.id, '高三示范班物理', term.start_date, term.end_date, 'ACTIVE'
FROM edu_academic_term term JOIN edu_class class JOIN edu_subject subject JOIN edu_teacher teacher
WHERE term.term_name = '第一学期' AND class.class_code = 'G3_DEMO_01' AND subject.subject_code = 'PHYSICS' AND teacher.teacher_no = 'DEMO_G3_PHYSICS'
  AND NOT EXISTS (SELECT 1 FROM teaching_course WHERE course_no = 'G3-2026-01-PHYSICS');
INSERT INTO teaching_course (course_no, term_id, class_id, subject_id, teacher_id, course_name, start_date, end_date, status)
SELECT 'G3-2026-01-CHEMISTRY', term.id, class.id, subject.id, teacher.id, '高三示范班化学', term.start_date, term.end_date, 'ACTIVE'
FROM edu_academic_term term JOIN edu_class class JOIN edu_subject subject JOIN edu_teacher teacher
WHERE term.term_name = '第一学期' AND class.class_code = 'G3_DEMO_01' AND subject.subject_code = 'CHEMISTRY' AND teacher.teacher_no = 'DEMO_G3_CHEMISTRY'
  AND NOT EXISTS (SELECT 1 FROM teaching_course WHERE course_no = 'G3-2026-01-CHEMISTRY');
INSERT INTO teaching_course (course_no, term_id, class_id, subject_id, teacher_id, course_name, start_date, end_date, status)
SELECT 'G3-2026-01-BIOLOGY', term.id, class.id, subject.id, teacher.id, '高三示范班生物', term.start_date, term.end_date, 'ACTIVE'
FROM edu_academic_term term JOIN edu_class class JOIN edu_subject subject JOIN edu_teacher teacher
WHERE term.term_name = '第一学期' AND class.class_code = 'G3_DEMO_01' AND subject.subject_code = 'BIOLOGY' AND teacher.teacher_no = 'DEMO_G3_BIOLOGY'
  AND NOT EXISTS (SELECT 1 FROM teaching_course WHERE course_no = 'G3-2026-01-BIOLOGY');
INSERT INTO teaching_course (course_no, term_id, class_id, subject_id, teacher_id, course_name, start_date, end_date, status)
SELECT 'G3-2026-01-PE', term.id, class.id, subject.id, teacher.id, '高三示范班体育', term.start_date, term.end_date, 'ACTIVE'
FROM edu_academic_term term JOIN edu_class class JOIN edu_subject subject JOIN edu_teacher teacher
WHERE term.term_name = '第一学期' AND class.class_code = 'G3_DEMO_01' AND subject.subject_code = 'PHYSICAL_EDUCATION' AND teacher.teacher_no = 'DEMO_G3_PE'
  AND NOT EXISTS (SELECT 1 FROM teaching_course WHERE course_no = 'G3-2026-01-PE');

INSERT INTO edu_lesson_schedule (teaching_course_id, weekday, start_time, end_time, lesson_title, enabled)
SELECT course.id, slot.weekday, slot.start_time, slot.end_time, slot.lesson_title, 1
FROM teaching_course course
JOIN (
  SELECT 1 AS weekday, '08:10' AS start_time, '08:55' AS end_time, '第1节' AS lesson_title UNION ALL
  SELECT 1, '15:50', '16:35', '第7节' UNION ALL SELECT 2, '10:10', '10:55', '第3节' UNION ALL
  SELECT 4, '09:05', '09:50', '第2节' UNION ALL SELECT 5, '11:05', '11:50', '第4节' UNION ALL
  SELECT 6, '09:05', '09:50', '第2节' UNION ALL SELECT 7, '08:10', '08:55', '第1节'
) slot
WHERE course.course_no = 'G3-2026-01-CHINESE'
ON DUPLICATE KEY UPDATE end_time = VALUES(end_time), lesson_title = VALUES(lesson_title), enabled = VALUES(enabled);

INSERT INTO edu_lesson_schedule (teaching_course_id, weekday, start_time, end_time, lesson_title, enabled)
SELECT course.id, slot.weekday, slot.start_time, slot.end_time, slot.lesson_title, 1
FROM teaching_course course
JOIN (
  SELECT 1 AS weekday, '10:10' AS start_time, '10:55' AS end_time, '第3节' AS lesson_title UNION ALL
  SELECT 2, '08:10', '08:55', '第1节' UNION ALL SELECT 3, '11:05', '11:50', '第4节' UNION ALL
  SELECT 4, '11:05', '11:50', '第4节' UNION ALL SELECT 4, '14:55', '15:40', '第6节' UNION ALL
  SELECT 4, '15:50', '16:35', '第7节' UNION ALL SELECT 5, '15:50', '16:35', '第7节' UNION ALL
  SELECT 6, '08:10', '08:55', '第1节'
) slot
WHERE course.course_no = 'G3-2026-01-MATH'
ON DUPLICATE KEY UPDATE end_time = VALUES(end_time), lesson_title = VALUES(lesson_title), enabled = VALUES(enabled);

INSERT INTO edu_lesson_schedule (teaching_course_id, weekday, start_time, end_time, lesson_title, enabled)
SELECT course.id, slot.weekday, slot.start_time, slot.end_time, slot.lesson_title, 1
FROM teaching_course course
JOIN (
  SELECT 1 AS weekday, '09:05' AS start_time, '09:50' AS end_time, '第2节' AS lesson_title UNION ALL
  SELECT 2, '09:05', '09:50', '第2节' UNION ALL SELECT 2, '14:00', '14:45', '第5节' UNION ALL
  SELECT 3, '08:10', '08:55', '第1节' UNION ALL SELECT 4, '10:10', '10:55', '第3节' UNION ALL
  SELECT 5, '08:10', '08:55', '第1节' UNION ALL SELECT 7, '10:10', '10:55', '第3节' UNION ALL
  SELECT 7, '11:05', '11:50', '第4节'
) slot
WHERE course.course_no = 'G3-2026-01-ENGLISH'
ON DUPLICATE KEY UPDATE end_time = VALUES(end_time), lesson_title = VALUES(lesson_title), enabled = VALUES(enabled);

INSERT INTO edu_lesson_schedule (teaching_course_id, weekday, start_time, end_time, lesson_title, enabled)
SELECT course.id, slot.weekday, slot.start_time, slot.end_time, slot.lesson_title, 1
FROM teaching_course course
JOIN (
  SELECT 3 AS weekday, '09:05' AS start_time, '09:50' AS end_time, '第2节' AS lesson_title UNION ALL
  SELECT 4, '08:10', '08:55', '第1节' UNION ALL SELECT 5, '10:10', '10:55', '第3节' UNION ALL
  SELECT 6, '11:05', '11:50', '第4节' UNION ALL SELECT 6, '14:00', '14:45', '第5节'
) slot
WHERE course.course_no = 'G3-2026-01-PHYSICS'
ON DUPLICATE KEY UPDATE end_time = VALUES(end_time), lesson_title = VALUES(lesson_title), enabled = VALUES(enabled);

INSERT INTO edu_lesson_schedule (teaching_course_id, weekday, start_time, end_time, lesson_title, enabled)
SELECT course.id, slot.weekday, slot.start_time, slot.end_time, slot.lesson_title, 1
FROM teaching_course course
JOIN (
  SELECT 1 AS weekday, '11:05' AS start_time, '11:50' AS end_time, '第4节' AS lesson_title UNION ALL
  SELECT 2, '14:55', '15:40', '第6节' UNION ALL SELECT 3, '10:10', '10:55', '第3节' UNION ALL
  SELECT 3, '15:50', '16:35', '第7节' UNION ALL SELECT 5, '09:05', '09:50', '第2节' UNION ALL
  SELECT 6, '10:10', '10:55', '第3节'
) slot
WHERE course.course_no = 'G3-2026-01-CHEMISTRY'
ON DUPLICATE KEY UPDATE end_time = VALUES(end_time), lesson_title = VALUES(lesson_title), enabled = VALUES(enabled);

INSERT INTO edu_lesson_schedule (teaching_course_id, weekday, start_time, end_time, lesson_title, enabled)
SELECT course.id, slot.weekday, slot.start_time, slot.end_time, slot.lesson_title, 1
FROM teaching_course course
JOIN (
  SELECT 1 AS weekday, '14:55' AS start_time, '15:40' AS end_time, '第6节' AS lesson_title UNION ALL
  SELECT 2, '11:05', '11:50', '第4节' UNION ALL SELECT 2, '15:50', '16:35', '第7节' UNION ALL
  SELECT 4, '14:00', '14:45', '第5节' UNION ALL SELECT 5, '14:55', '15:40', '第6节' UNION ALL
  SELECT 6, '14:55', '15:40', '第6节' UNION ALL SELECT 7, '09:05', '09:50', '第2节'
) slot
WHERE course.course_no = 'G3-2026-01-BIOLOGY'
ON DUPLICATE KEY UPDATE end_time = VALUES(end_time), lesson_title = VALUES(lesson_title), enabled = VALUES(enabled);

INSERT INTO edu_lesson_schedule (teaching_course_id, weekday, start_time, end_time, lesson_title, enabled)
SELECT course.id, slot.weekday, slot.start_time, slot.end_time, slot.lesson_title, 1
FROM teaching_course course
JOIN (
  SELECT 1 AS weekday, '14:00' AS start_time, '14:45' AS end_time, '第5节' AS lesson_title UNION ALL
  SELECT 3, '14:55', '15:40', '第6节' UNION ALL SELECT 5, '14:00', '14:45', '第5节'
) slot
WHERE course.course_no = 'G3-2026-01-PE'
ON DUPLICATE KEY UPDATE end_time = VALUES(end_time), lesson_title = VALUES(lesson_title), enabled = VALUES(enabled);
