-- 教师端班级视图的最小可重复测试数据。
-- teacher1 和 tearch2 的测试密码均为 Teacher123!；admin 密码保持现有部署配置。
-- 保留既有监控历史、汇总和事件；旧“高三示范班”七科课程仅归档停用，不删除引用链。

SET NAMES utf8mb4;

START TRANSACTION;

UPDATE edu_lesson_schedule schedule
JOIN teaching_course course ON course.id = schedule.teaching_course_id
SET schedule.enabled = 0
WHERE course.course_no LIKE 'G3-2026-01-%';

UPDATE teaching_course
SET status = 'ARCHIVED'
WHERE course_no LIKE 'G3-2026-01-%';

UPDATE edu_teacher
SET status = 'DISABLED'
WHERE teacher_no IN (
  'DEMO_G3_CHINESE', 'DEMO_G3_MATH', 'DEMO_G3_ENGLISH', 'DEMO_G3_PHYSICS',
  'DEMO_G3_CHEMISTRY', 'DEMO_G3_BIOLOGY', 'DEMO_G3_PE'
)
  AND user_id IS NULL;

UPDATE edu_class SET enabled = 0 WHERE class_code = 'G3_DEMO_01';

UPDATE edu_class
SET class_code = 'G3_01', class_name = '高三1班', grade_name = '高三', academic_year = '2026-2027', enabled = 1
WHERE class_code = 'CLASS_1';

UPDATE edu_class
SET class_code = 'G3_02', class_name = '高三2班', grade_name = '高三', academic_year = '2026-2027', enabled = 1
WHERE class_code = 'CLASS_2';

INSERT INTO edu_class (class_code, class_name, grade_name, academic_year, enabled)
SELECT 'G3_01', '高三1班', '高三', '2026-2027', 1
WHERE NOT EXISTS (SELECT 1 FROM edu_class WHERE class_code = 'G3_01');

INSERT INTO edu_class (class_code, class_name, grade_name, academic_year, enabled)
SELECT 'G3_02', '高三2班', '高三', '2026-2027', 1
WHERE NOT EXISTS (SELECT 1 FROM edu_class WHERE class_code = 'G3_02');

UPDATE edu_class SET enabled = 0 WHERE class_code IN ('CLASS_3', 'CLASS_4');
UPDATE monitor_session SET class_name = '高三1班' WHERE class_id = (SELECT id FROM edu_class WHERE class_code = 'G3_01');
UPDATE monitor_session SET class_name = '高三2班' WHERE class_id = (SELECT id FROM edu_class WHERE class_code = 'G3_02');

INSERT INTO edu_academic_year (year_name, start_date, end_date, status)
SELECT '2026-2027学年', '2026-09-01', '2027-08-31', 'ENABLED'
WHERE NOT EXISTS (SELECT 1 FROM edu_academic_year WHERE year_name = '2026-2027学年');

INSERT INTO edu_academic_term (academic_year_id, term_name, start_date, end_date, status)
SELECT year.id, '第一学期', '2026-09-01', '2027-01-31', 'ENABLED'
FROM edu_academic_year year
WHERE year.year_name = '2026-2027学年'
  AND NOT EXISTS (
    SELECT 1 FROM edu_academic_term term
    WHERE term.academic_year_id = year.id AND term.term_name = '第一学期'
  );

INSERT INTO sys_user (username, password_hash, real_name, status, failed_login_count, password_changed_at)
VALUES
  ('teacher1', '$2b$12$/JvYsX23bOg42UR.hBTLYei6iQOyZTneDoZ0RDRRREAmkJej6LruG', '数学教师', 'ENABLED', 0, NOW()),
  ('tearch2', '$2b$12$/JvYsX23bOg42UR.hBTLYei6iQOyZTneDoZ0RDRRREAmkJej6LruG', '英语教师', 'ENABLED', 0, NOW())
ON DUPLICATE KEY UPDATE
  password_hash = VALUES(password_hash),
  real_name = VALUES(real_name),
  status = 'ENABLED',
  failed_login_count = 0,
  locked_until = NULL,
  password_changed_at = VALUES(password_changed_at);

INSERT IGNORE INTO sys_user_role (user_id, role_id)
SELECT user.id, role.id
FROM sys_user user
JOIN sys_role role ON role.role_code = 'ADMIN'
WHERE user.username = 'admin';

DELETE user_role
FROM sys_user_role user_role
JOIN sys_user user ON user.id = user_role.user_id
JOIN sys_role role ON role.id = user_role.role_id
WHERE user.username IN ('teacher1', 'tearch2')
  AND role.role_code <> 'TEACHER';

INSERT IGNORE INTO sys_user_role (user_id, role_id)
SELECT user.id, role.id
FROM sys_user user
JOIN sys_role role ON role.role_code = 'TEACHER'
WHERE user.username IN ('teacher1', 'tearch2');

INSERT INTO edu_teacher (user_id, teacher_no, teacher_name, department, status)
SELECT user.id, 'TEACHER1', '数学教师', '高三年级组', 'ENABLED'
FROM sys_user user
WHERE user.username = 'teacher1'
ON DUPLICATE KEY UPDATE
  user_id = VALUES(user_id), teacher_name = VALUES(teacher_name), department = VALUES(department), status = VALUES(status);

INSERT INTO edu_teacher (user_id, teacher_no, teacher_name, department, status)
SELECT user.id, 'TEARCH2', '英语教师', '高三年级组', 'ENABLED'
FROM sys_user user
WHERE user.username = 'tearch2'
ON DUPLICATE KEY UPDATE
  user_id = VALUES(user_id), teacher_name = VALUES(teacher_name), department = VALUES(department), status = VALUES(status);

INSERT INTO teaching_course (course_no, term_id, class_id, subject_id, teacher_id, course_name, planned_lesson_count, start_date, end_date, status)
SELECT 'TEST-2026-MATH-G3-01', term.id, class.id, subject.id, teacher.id, '高三1班数学', 20, term.start_date, term.end_date, 'ACTIVE'
FROM edu_academic_term term
JOIN edu_academic_year year ON year.id = term.academic_year_id
JOIN edu_class class ON class.class_code = 'G3_01'
JOIN edu_subject subject ON subject.subject_code = 'MATH'
JOIN edu_teacher teacher ON teacher.teacher_no = 'TEACHER1'
WHERE year.year_name = '2026-2027学年' AND term.term_name = '第一学期'
ON DUPLICATE KEY UPDATE
  term_id = VALUES(term_id), class_id = VALUES(class_id), subject_id = VALUES(subject_id), teacher_id = VALUES(teacher_id),
  course_name = VALUES(course_name), planned_lesson_count = VALUES(planned_lesson_count),
  start_date = VALUES(start_date), end_date = VALUES(end_date), status = VALUES(status);

INSERT INTO teaching_course (course_no, term_id, class_id, subject_id, teacher_id, course_name, planned_lesson_count, start_date, end_date, status)
SELECT 'TEST-2026-MATH-G3-02', term.id, class.id, subject.id, teacher.id, '高三2班数学', 20, term.start_date, term.end_date, 'ACTIVE'
FROM edu_academic_term term
JOIN edu_academic_year year ON year.id = term.academic_year_id
JOIN edu_class class ON class.class_code = 'G3_02'
JOIN edu_subject subject ON subject.subject_code = 'MATH'
JOIN edu_teacher teacher ON teacher.teacher_no = 'TEACHER1'
WHERE year.year_name = '2026-2027学年' AND term.term_name = '第一学期'
ON DUPLICATE KEY UPDATE
  term_id = VALUES(term_id), class_id = VALUES(class_id), subject_id = VALUES(subject_id), teacher_id = VALUES(teacher_id),
  course_name = VALUES(course_name), planned_lesson_count = VALUES(planned_lesson_count),
  start_date = VALUES(start_date), end_date = VALUES(end_date), status = VALUES(status);

INSERT INTO teaching_course (course_no, term_id, class_id, subject_id, teacher_id, course_name, planned_lesson_count, start_date, end_date, status)
SELECT 'TEST-2026-ENGLISH-G3-02', term.id, class.id, subject.id, teacher.id, '高三2班英语', 20, term.start_date, term.end_date, 'ACTIVE'
FROM edu_academic_term term
JOIN edu_academic_year year ON year.id = term.academic_year_id
JOIN edu_class class ON class.class_code = 'G3_02'
JOIN edu_subject subject ON subject.subject_code = 'ENGLISH'
JOIN edu_teacher teacher ON teacher.teacher_no = 'TEARCH2'
WHERE year.year_name = '2026-2027学年' AND term.term_name = '第一学期'
ON DUPLICATE KEY UPDATE
  term_id = VALUES(term_id), class_id = VALUES(class_id), subject_id = VALUES(subject_id), teacher_id = VALUES(teacher_id),
  course_name = VALUES(course_name), planned_lesson_count = VALUES(planned_lesson_count),
  start_date = VALUES(start_date), end_date = VALUES(end_date), status = VALUES(status);

INSERT INTO edu_teacher_class (teacher_id, class_id, subject_id, relation_type, can_view_monitor, can_start_monitor, can_review, enabled)
SELECT teacher.id, class.id, subject.id, 'SUBJECT_TEACHER', 1, 0, 1, 1
FROM edu_teacher teacher
JOIN edu_class class ON class.class_code = 'G3_01'
JOIN edu_subject subject ON subject.subject_code = 'MATH'
WHERE teacher.teacher_no = 'TEACHER1'
ON DUPLICATE KEY UPDATE can_view_monitor = VALUES(can_view_monitor), can_start_monitor = VALUES(can_start_monitor), can_review = VALUES(can_review), enabled = VALUES(enabled);

INSERT INTO edu_teacher_class (teacher_id, class_id, subject_id, relation_type, can_view_monitor, can_start_monitor, can_review, enabled)
SELECT teacher.id, class.id, subject.id, 'SUBJECT_TEACHER', 1, 0, 1, 1
FROM edu_teacher teacher
JOIN edu_class class ON class.class_code = 'G3_02'
JOIN edu_subject subject ON subject.subject_code = 'MATH'
WHERE teacher.teacher_no = 'TEACHER1'
ON DUPLICATE KEY UPDATE can_view_monitor = VALUES(can_view_monitor), can_start_monitor = VALUES(can_start_monitor), can_review = VALUES(can_review), enabled = VALUES(enabled);

INSERT INTO edu_teacher_class (teacher_id, class_id, subject_id, relation_type, can_view_monitor, can_start_monitor, can_review, enabled)
SELECT teacher.id, class.id, subject.id, 'SUBJECT_TEACHER', 1, 0, 1, 1
FROM edu_teacher teacher
JOIN edu_class class ON class.class_code = 'G3_02'
JOIN edu_subject subject ON subject.subject_code = 'ENGLISH'
WHERE teacher.teacher_no = 'TEARCH2'
ON DUPLICATE KEY UPDATE can_view_monitor = VALUES(can_view_monitor), can_start_monitor = VALUES(can_start_monitor), can_review = VALUES(can_review), enabled = VALUES(enabled);

INSERT INTO edu_lesson_schedule (teaching_course_id, weekday, start_time, end_time, lesson_title, enabled)
SELECT course.id, 1, '08:00', '08:45', '第1节', 1
FROM teaching_course course
WHERE course.course_no = 'TEST-2026-MATH-G3-01'
ON DUPLICATE KEY UPDATE end_time = VALUES(end_time), lesson_title = VALUES(lesson_title), enabled = VALUES(enabled);

INSERT INTO edu_lesson_schedule (teaching_course_id, weekday, start_time, end_time, lesson_title, enabled)
SELECT course.id, 2, '08:00', '08:45', '第1节', 1
FROM teaching_course course
WHERE course.course_no = 'TEST-2026-MATH-G3-02'
ON DUPLICATE KEY UPDATE end_time = VALUES(end_time), lesson_title = VALUES(lesson_title), enabled = VALUES(enabled);

INSERT INTO edu_lesson_schedule (teaching_course_id, weekday, start_time, end_time, lesson_title, enabled)
SELECT course.id, 1, '09:00', '09:45', '第2节', 1
FROM teaching_course course
WHERE course.course_no = 'TEST-2026-ENGLISH-G3-02'
ON DUPLICATE KEY UPDATE end_time = VALUES(end_time), lesson_title = VALUES(lesson_title), enabled = VALUES(enabled);

COMMIT;
