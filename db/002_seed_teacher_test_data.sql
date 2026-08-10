-- Seed 20 teacher test accounts, profiles, roles, and class permissions.
-- Default password for all teacher accounts: Teacher@123456
-- This file is intended for local/test environments only.

SET NAMES utf8mb4;
START TRANSACTION;

INSERT IGNORE INTO sys_role (role_code, role_name, description, enabled) VALUES
('TEACHER', '教师', '查看授权班级监控记录并提交教学复盘', 1),
('OPERATOR', '监控操作员', '启动和停止课堂监控任务', 1);

INSERT IGNORE INTO sys_user (username, password_hash, real_name, phone, email, status, password_changed_at) VALUES
('teacher001', '$2b$12$fWWaa.HVQ9REe0SwLg6.Her22uy7g2Ef2jhxwK1fRQWcLcK7stZUu', '张明远', '13800010001', 'teacher001@classroom.test', 'ENABLED', NOW()),
('teacher002', '$2b$12$fWWaa.HVQ9REe0SwLg6.Her22uy7g2Ef2jhxwK1fRQWcLcK7stZUu', '李婉晴', '13800010002', 'teacher002@classroom.test', 'ENABLED', NOW()),
('teacher003', '$2b$12$fWWaa.HVQ9REe0SwLg6.Her22uy7g2Ef2jhxwK1fRQWcLcK7stZUu', '王子轩', '13800010003', 'teacher003@classroom.test', 'ENABLED', NOW()),
('teacher004', '$2b$12$fWWaa.HVQ9REe0SwLg6.Her22uy7g2Ef2jhxwK1fRQWcLcK7stZUu', '赵雨涵', '13800010004', 'teacher004@classroom.test', 'ENABLED', NOW()),
('teacher005', '$2b$12$fWWaa.HVQ9REe0SwLg6.Her22uy7g2Ef2jhxwK1fRQWcLcK7stZUu', '陈思远', '13800010005', 'teacher005@classroom.test', 'ENABLED', NOW()),
('teacher006', '$2b$12$fWWaa.HVQ9REe0SwLg6.Her22uy7g2Ef2jhxwK1fRQWcLcK7stZUu', '刘雅婷', '13800010006', 'teacher006@classroom.test', 'ENABLED', NOW()),
('teacher007', '$2b$12$fWWaa.HVQ9REe0SwLg6.Her22uy7g2Ef2jhxwK1fRQWcLcK7stZUu', '周浩然', '13800010007', 'teacher007@classroom.test', 'ENABLED', NOW()),
('teacher008', '$2b$12$fWWaa.HVQ9REe0SwLg6.Her22uy7g2Ef2jhxwK1fRQWcLcK7stZUu', '吴佳宁', '13800010008', 'teacher008@classroom.test', 'ENABLED', NOW()),
('teacher009', '$2b$12$fWWaa.HVQ9REe0SwLg6.Her22uy7g2Ef2jhxwK1fRQWcLcK7stZUu', '郑博文', '13800010009', 'teacher009@classroom.test', 'ENABLED', NOW()),
('teacher010', '$2b$12$fWWaa.HVQ9REe0SwLg6.Her22uy7g2Ef2jhxwK1fRQWcLcK7stZUu', '孙若溪', '13800010010', 'teacher010@classroom.test', 'ENABLED', NOW()),
('teacher011', '$2b$12$fWWaa.HVQ9REe0SwLg6.Her22uy7g2Ef2jhxwK1fRQWcLcK7stZUu', '马俊驰', '13800010011', 'teacher011@classroom.test', 'ENABLED', NOW()),
('teacher012', '$2b$12$fWWaa.HVQ9REe0SwLg6.Her22uy7g2Ef2jhxwK1fRQWcLcK7stZUu', '朱清扬', '13800010012', 'teacher012@classroom.test', 'ENABLED', NOW()),
('teacher013', '$2b$12$fWWaa.HVQ9REe0SwLg6.Her22uy7g2Ef2jhxwK1fRQWcLcK7stZUu', '胡嘉豪', '13800010013', 'teacher013@classroom.test', 'ENABLED', NOW()),
('teacher014', '$2b$12$fWWaa.HVQ9REe0SwLg6.Her22uy7g2Ef2jhxwK1fRQWcLcK7stZUu', '林舒雅', '13800010014', 'teacher014@classroom.test', 'ENABLED', NOW()),
('teacher015', '$2b$12$fWWaa.HVQ9REe0SwLg6.Her22uy7g2Ef2jhxwK1fRQWcLcK7stZUu', '高启航', '13800010015', 'teacher015@classroom.test', 'ENABLED', NOW()),
('teacher016', '$2b$12$fWWaa.HVQ9REe0SwLg6.Her22uy7g2Ef2jhxwK1fRQWcLcK7stZUu', '何诗雨', '13800010016', 'teacher016@classroom.test', 'ENABLED', NOW()),
('teacher017', '$2b$12$fWWaa.HVQ9REe0SwLg6.Her22uy7g2Ef2jhxwK1fRQWcLcK7stZUu', '郭晨曦', '13800010017', 'teacher017@classroom.test', 'ENABLED', NOW()),
('teacher018', '$2b$12$fWWaa.HVQ9REe0SwLg6.Her22uy7g2Ef2jhxwK1fRQWcLcK7stZUu', '罗可欣', '13800010018', 'teacher018@classroom.test', 'ENABLED', NOW()),
('teacher019', '$2b$12$fWWaa.HVQ9REe0SwLg6.Her22uy7g2Ef2jhxwK1fRQWcLcK7stZUu', '梁宇航', '13800010019', 'teacher019@classroom.test', 'ENABLED', NOW()),
('teacher020', '$2b$12$fWWaa.HVQ9REe0SwLg6.Her22uy7g2Ef2jhxwK1fRQWcLcK7stZUu', '唐若楠', '13800010020', 'teacher020@classroom.test', 'ENABLED', NOW());

INSERT IGNORE INTO sys_user_role (user_id, role_id)
SELECT u.id, r.id
FROM sys_user u
JOIN sys_role r ON r.role_code = 'TEACHER'
WHERE u.username IN (
  'teacher001', 'teacher002', 'teacher003', 'teacher004', 'teacher005',
  'teacher006', 'teacher007', 'teacher008', 'teacher009', 'teacher010',
  'teacher011', 'teacher012', 'teacher013', 'teacher014', 'teacher015',
  'teacher016', 'teacher017', 'teacher018', 'teacher019', 'teacher020'
);

INSERT IGNORE INTO sys_user_role (user_id, role_id)
SELECT u.id, r.id
FROM sys_user u
JOIN sys_role r ON r.role_code = 'OPERATOR'
WHERE u.username IN ('teacher001', 'teacher006', 'teacher011', 'teacher016');

INSERT IGNORE INTO edu_teacher (user_id, teacher_no, teacher_name, gender, phone, email, department, title, status) VALUES
((SELECT id FROM sys_user WHERE username = 'teacher001'), 'T2026001', '张明远', '男', '13800010001', 'teacher001@classroom.test', '综合教研组', '高级教师', 'ENABLED'),
((SELECT id FROM sys_user WHERE username = 'teacher002'), 'T2026002', '李婉晴', '女', '13800010002', 'teacher002@classroom.test', '语文组', '一级教师', 'ENABLED'),
((SELECT id FROM sys_user WHERE username = 'teacher003'), 'T2026003', '王子轩', '男', '13800010003', 'teacher003@classroom.test', '数学组', '一级教师', 'ENABLED'),
((SELECT id FROM sys_user WHERE username = 'teacher004'), 'T2026004', '赵雨涵', '女', '13800010004', 'teacher004@classroom.test', '英语组', '一级教师', 'ENABLED'),
((SELECT id FROM sys_user WHERE username = 'teacher005'), 'T2026005', '陈思远', '男', '13800010005', 'teacher005@classroom.test', '理综组', '一级教师', 'ENABLED'),
((SELECT id FROM sys_user WHERE username = 'teacher006'), 'T2026006', '刘雅婷', '女', '13800010006', 'teacher006@classroom.test', '综合教研组', '高级教师', 'ENABLED'),
((SELECT id FROM sys_user WHERE username = 'teacher007'), 'T2026007', '周浩然', '男', '13800010007', 'teacher007@classroom.test', '语文组', '一级教师', 'ENABLED'),
((SELECT id FROM sys_user WHERE username = 'teacher008'), 'T2026008', '吴佳宁', '女', '13800010008', 'teacher008@classroom.test', '数学组', '一级教师', 'ENABLED'),
((SELECT id FROM sys_user WHERE username = 'teacher009'), 'T2026009', '郑博文', '男', '13800010009', 'teacher009@classroom.test', '英语组', '二级教师', 'ENABLED'),
((SELECT id FROM sys_user WHERE username = 'teacher010'), 'T2026010', '孙若溪', '女', '13800010010', 'teacher010@classroom.test', '理综组', '一级教师', 'ENABLED'),
((SELECT id FROM sys_user WHERE username = 'teacher011'), 'T2026011', '马俊驰', '男', '13800010011', 'teacher011@classroom.test', '综合教研组', '高级教师', 'ENABLED'),
((SELECT id FROM sys_user WHERE username = 'teacher012'), 'T2026012', '朱清扬', '女', '13800010012', 'teacher012@classroom.test', '语文组', '一级教师', 'ENABLED'),
((SELECT id FROM sys_user WHERE username = 'teacher013'), 'T2026013', '胡嘉豪', '男', '13800010013', 'teacher013@classroom.test', '数学组', '高级教师', 'ENABLED'),
((SELECT id FROM sys_user WHERE username = 'teacher014'), 'T2026014', '林舒雅', '女', '13800010014', 'teacher014@classroom.test', '英语组', '一级教师', 'ENABLED'),
((SELECT id FROM sys_user WHERE username = 'teacher015'), 'T2026015', '高启航', '男', '13800010015', 'teacher015@classroom.test', '理综组', '二级教师', 'ENABLED'),
((SELECT id FROM sys_user WHERE username = 'teacher016'), 'T2026016', '何诗雨', '女', '13800010016', 'teacher016@classroom.test', '综合教研组', '高级教师', 'ENABLED'),
((SELECT id FROM sys_user WHERE username = 'teacher017'), 'T2026017', '郭晨曦', '男', '13800010017', 'teacher017@classroom.test', '语文组', '一级教师', 'ENABLED'),
((SELECT id FROM sys_user WHERE username = 'teacher018'), 'T2026018', '罗可欣', '女', '13800010018', 'teacher018@classroom.test', '数学组', '二级教师', 'ENABLED'),
((SELECT id FROM sys_user WHERE username = 'teacher019'), 'T2026019', '梁宇航', '男', '13800010019', 'teacher019@classroom.test', '英语组', '一级教师', 'ENABLED'),
((SELECT id FROM sys_user WHERE username = 'teacher020'), 'T2026020', '唐若楠', '女', '13800010020', 'teacher020@classroom.test', '理综组', '一级教师', 'ENABLED');

INSERT IGNORE INTO edu_teacher_class (
  teacher_id, class_id, subject_id, relation_type,
  can_view_monitor, can_start_monitor, can_review,
  start_date, end_date, enabled
) VALUES
((SELECT id FROM edu_teacher WHERE teacher_no = 'T2026001'), (SELECT id FROM edu_class WHERE class_code = 'CLASS_1'), (SELECT id FROM edu_subject WHERE subject_code = 'GENERAL'), 'HEAD_TEACHER', 1, 1, 1, CURDATE(), NULL, 1),
((SELECT id FROM edu_teacher WHERE teacher_no = 'T2026002'), (SELECT id FROM edu_class WHERE class_code = 'CLASS_1'), (SELECT id FROM edu_subject WHERE subject_code = 'CHINESE'), 'SUBJECT_TEACHER', 1, 0, 1, CURDATE(), NULL, 1),
((SELECT id FROM edu_teacher WHERE teacher_no = 'T2026003'), (SELECT id FROM edu_class WHERE class_code = 'CLASS_1'), (SELECT id FROM edu_subject WHERE subject_code = 'MATH'), 'SUBJECT_TEACHER', 1, 0, 1, CURDATE(), NULL, 1),
((SELECT id FROM edu_teacher WHERE teacher_no = 'T2026004'), (SELECT id FROM edu_class WHERE class_code = 'CLASS_1'), (SELECT id FROM edu_subject WHERE subject_code = 'ENGLISH'), 'SUBJECT_TEACHER', 1, 0, 1, CURDATE(), NULL, 1),
((SELECT id FROM edu_teacher WHERE teacher_no = 'T2026005'), (SELECT id FROM edu_class WHERE class_code = 'CLASS_1'), (SELECT id FROM edu_subject WHERE subject_code = 'PHYSICS'), 'SUBJECT_TEACHER', 1, 0, 1, CURDATE(), NULL, 1),
((SELECT id FROM edu_teacher WHERE teacher_no = 'T2026006'), (SELECT id FROM edu_class WHERE class_code = 'CLASS_2'), (SELECT id FROM edu_subject WHERE subject_code = 'GENERAL'), 'HEAD_TEACHER', 1, 1, 1, CURDATE(), NULL, 1),
((SELECT id FROM edu_teacher WHERE teacher_no = 'T2026007'), (SELECT id FROM edu_class WHERE class_code = 'CLASS_2'), (SELECT id FROM edu_subject WHERE subject_code = 'CHINESE'), 'SUBJECT_TEACHER', 1, 0, 1, CURDATE(), NULL, 1),
((SELECT id FROM edu_teacher WHERE teacher_no = 'T2026008'), (SELECT id FROM edu_class WHERE class_code = 'CLASS_2'), (SELECT id FROM edu_subject WHERE subject_code = 'MATH'), 'SUBJECT_TEACHER', 1, 0, 1, CURDATE(), NULL, 1),
((SELECT id FROM edu_teacher WHERE teacher_no = 'T2026009'), (SELECT id FROM edu_class WHERE class_code = 'CLASS_2'), (SELECT id FROM edu_subject WHERE subject_code = 'ENGLISH'), 'SUBJECT_TEACHER', 1, 0, 1, CURDATE(), NULL, 1),
((SELECT id FROM edu_teacher WHERE teacher_no = 'T2026010'), (SELECT id FROM edu_class WHERE class_code = 'CLASS_2'), (SELECT id FROM edu_subject WHERE subject_code = 'PHYSICS'), 'SUBJECT_TEACHER', 1, 0, 1, CURDATE(), NULL, 1),
((SELECT id FROM edu_teacher WHERE teacher_no = 'T2026011'), (SELECT id FROM edu_class WHERE class_code = 'CLASS_3'), (SELECT id FROM edu_subject WHERE subject_code = 'GENERAL'), 'HEAD_TEACHER', 1, 1, 1, CURDATE(), NULL, 1),
((SELECT id FROM edu_teacher WHERE teacher_no = 'T2026012'), (SELECT id FROM edu_class WHERE class_code = 'CLASS_3'), (SELECT id FROM edu_subject WHERE subject_code = 'CHINESE'), 'SUBJECT_TEACHER', 1, 0, 1, CURDATE(), NULL, 1),
((SELECT id FROM edu_teacher WHERE teacher_no = 'T2026013'), (SELECT id FROM edu_class WHERE class_code = 'CLASS_3'), (SELECT id FROM edu_subject WHERE subject_code = 'MATH'), 'SUBJECT_TEACHER', 1, 0, 1, CURDATE(), NULL, 1),
((SELECT id FROM edu_teacher WHERE teacher_no = 'T2026014'), (SELECT id FROM edu_class WHERE class_code = 'CLASS_3'), (SELECT id FROM edu_subject WHERE subject_code = 'ENGLISH'), 'SUBJECT_TEACHER', 1, 0, 1, CURDATE(), NULL, 1),
((SELECT id FROM edu_teacher WHERE teacher_no = 'T2026015'), (SELECT id FROM edu_class WHERE class_code = 'CLASS_3'), (SELECT id FROM edu_subject WHERE subject_code = 'PHYSICS'), 'SUBJECT_TEACHER', 1, 0, 1, CURDATE(), NULL, 1),
((SELECT id FROM edu_teacher WHERE teacher_no = 'T2026016'), (SELECT id FROM edu_class WHERE class_code = 'CLASS_4'), (SELECT id FROM edu_subject WHERE subject_code = 'GENERAL'), 'HEAD_TEACHER', 1, 1, 1, CURDATE(), NULL, 1),
((SELECT id FROM edu_teacher WHERE teacher_no = 'T2026017'), (SELECT id FROM edu_class WHERE class_code = 'CLASS_4'), (SELECT id FROM edu_subject WHERE subject_code = 'CHINESE'), 'SUBJECT_TEACHER', 1, 0, 1, CURDATE(), NULL, 1),
((SELECT id FROM edu_teacher WHERE teacher_no = 'T2026018'), (SELECT id FROM edu_class WHERE class_code = 'CLASS_4'), (SELECT id FROM edu_subject WHERE subject_code = 'MATH'), 'SUBJECT_TEACHER', 1, 0, 1, CURDATE(), NULL, 1),
((SELECT id FROM edu_teacher WHERE teacher_no = 'T2026019'), (SELECT id FROM edu_class WHERE class_code = 'CLASS_4'), (SELECT id FROM edu_subject WHERE subject_code = 'ENGLISH'), 'SUBJECT_TEACHER', 1, 0, 1, CURDATE(), NULL, 1),
((SELECT id FROM edu_teacher WHERE teacher_no = 'T2026020'), (SELECT id FROM edu_class WHERE class_code = 'CLASS_4'), (SELECT id FROM edu_subject WHERE subject_code = 'PHYSICS'), 'SUBJECT_TEACHER', 1, 0, 1, CURDATE(), NULL, 1);

UPDATE edu_class c
JOIN edu_teacher t ON t.teacher_no = 'T2026001'
SET c.head_teacher_id = t.id
WHERE c.class_code = 'CLASS_1' AND c.head_teacher_id IS NULL;

UPDATE edu_class c
JOIN edu_teacher t ON t.teacher_no = 'T2026006'
SET c.head_teacher_id = t.id
WHERE c.class_code = 'CLASS_2' AND c.head_teacher_id IS NULL;

UPDATE edu_class c
JOIN edu_teacher t ON t.teacher_no = 'T2026011'
SET c.head_teacher_id = t.id
WHERE c.class_code = 'CLASS_3' AND c.head_teacher_id IS NULL;

UPDATE edu_class c
JOIN edu_teacher t ON t.teacher_no = 'T2026016'
SET c.head_teacher_id = t.id
WHERE c.class_code = 'CLASS_4' AND c.head_teacher_id IS NULL;

COMMIT;
