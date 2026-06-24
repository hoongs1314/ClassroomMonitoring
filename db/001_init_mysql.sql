-- ClassroomMonitoring MySQL base schema.
-- Run this file inside the target database. It does not create or drop databases.
-- Recommended MySQL version: 5.7+ for JSON columns, 8.0+ preferred.

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS sys_user (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  username VARCHAR(64) NOT NULL COMMENT 'Login username',
  password_hash VARCHAR(255) NOT NULL COMMENT 'Password hash, never store plain text',
  real_name VARCHAR(64) NOT NULL DEFAULT '' COMMENT 'Display name',
  phone VARCHAR(32) NULL COMMENT 'Phone number',
  email VARCHAR(128) NULL COMMENT 'Email address',
  avatar_url VARCHAR(255) NULL COMMENT 'Avatar URL',
  status VARCHAR(16) NOT NULL DEFAULT 'ENABLED' COMMENT 'ENABLED, DISABLED, LOCKED',
  failed_login_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Failed login count',
  locked_until DATETIME NULL COMMENT 'Lock expiration time',
  last_login_at DATETIME NULL COMMENT 'Last login time',
  last_login_ip VARCHAR(64) NULL COMMENT 'Last login IP',
  password_changed_at DATETIME NULL COMMENT 'Last password update time',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  PRIMARY KEY (id),
  UNIQUE KEY uk_sys_user_username (username),
  KEY idx_sys_user_phone (phone),
  KEY idx_sys_user_email (email),
  KEY idx_sys_user_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='System user account';

CREATE TABLE IF NOT EXISTS sys_role (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  role_code VARCHAR(32) NOT NULL COMMENT 'Role code',
  role_name VARCHAR(64) NOT NULL COMMENT 'Role name',
  description VARCHAR(255) NULL COMMENT 'Role description',
  enabled TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Whether role is enabled',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  PRIMARY KEY (id),
  UNIQUE KEY uk_sys_role_code (role_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='System role';

CREATE TABLE IF NOT EXISTS sys_user_role (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  user_id BIGINT UNSIGNED NOT NULL COMMENT 'User ID',
  role_id BIGINT UNSIGNED NOT NULL COMMENT 'Role ID',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  PRIMARY KEY (id),
  UNIQUE KEY uk_sys_user_role (user_id, role_id),
  KEY idx_sys_user_role_role_id (role_id),
  CONSTRAINT fk_sys_user_role_user FOREIGN KEY (user_id) REFERENCES sys_user (id) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_sys_user_role_role FOREIGN KEY (role_id) REFERENCES sys_role (id) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='User role relation';

CREATE TABLE IF NOT EXISTS sys_auth_token (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  user_id BIGINT UNSIGNED NOT NULL COMMENT 'User ID',
  token_jti VARCHAR(128) NOT NULL COMMENT 'Access token unique ID',
  refresh_token_hash VARCHAR(255) NULL COMMENT 'Refresh token hash',
  client_ip VARCHAR(64) NULL COMMENT 'Client IP',
  user_agent VARCHAR(512) NULL COMMENT 'Client user agent',
  expires_at DATETIME NOT NULL COMMENT 'Token expiration time',
  revoked_at DATETIME NULL COMMENT 'Token revoke time',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  PRIMARY KEY (id),
  UNIQUE KEY uk_sys_auth_token_jti (token_jti),
  KEY idx_sys_auth_token_user_id (user_id),
  KEY idx_sys_auth_token_expires_at (expires_at),
  CONSTRAINT fk_sys_auth_token_user FOREIGN KEY (user_id) REFERENCES sys_user (id) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Login token and refresh session';

CREATE TABLE IF NOT EXISTS sys_login_log (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  user_id BIGINT UNSIGNED NULL COMMENT 'User ID if login user exists',
  username VARCHAR(64) NOT NULL COMMENT 'Submitted username',
  login_result VARCHAR(16) NOT NULL COMMENT 'SUCCESS, FAILED, LOCKED',
  fail_reason VARCHAR(255) NULL COMMENT 'Failure reason',
  client_ip VARCHAR(64) NULL COMMENT 'Client IP',
  user_agent VARCHAR(512) NULL COMMENT 'Client user agent',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  PRIMARY KEY (id),
  KEY idx_sys_login_log_user_id (user_id),
  KEY idx_sys_login_log_username (username),
  KEY idx_sys_login_log_created_at (created_at),
  CONSTRAINT fk_sys_login_log_user FOREIGN KEY (user_id) REFERENCES sys_user (id) ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Login audit log';

CREATE TABLE IF NOT EXISTS edu_teacher (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  user_id BIGINT UNSIGNED NULL COMMENT 'Bound login account ID',
  teacher_no VARCHAR(64) NOT NULL COMMENT 'Teacher number',
  teacher_name VARCHAR(64) NOT NULL COMMENT 'Teacher name',
  gender VARCHAR(16) NULL COMMENT 'Gender',
  phone VARCHAR(32) NULL COMMENT 'Phone number',
  email VARCHAR(128) NULL COMMENT 'Email address',
  department VARCHAR(128) NULL COMMENT 'Department',
  title VARCHAR(64) NULL COMMENT 'Professional title',
  status VARCHAR(16) NOT NULL DEFAULT 'ENABLED' COMMENT 'ENABLED, DISABLED',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  PRIMARY KEY (id),
  UNIQUE KEY uk_edu_teacher_user_id (user_id),
  UNIQUE KEY uk_edu_teacher_no (teacher_no),
  KEY idx_edu_teacher_name (teacher_name),
  KEY idx_edu_teacher_status (status),
  CONSTRAINT fk_edu_teacher_user FOREIGN KEY (user_id) REFERENCES sys_user (id) ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Teacher profile';

CREATE TABLE IF NOT EXISTS edu_class (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  class_code VARCHAR(64) NOT NULL COMMENT 'Class code',
  class_name VARCHAR(64) NOT NULL COMMENT 'Class name',
  grade_name VARCHAR(64) NULL COMMENT 'Grade name',
  academic_year VARCHAR(32) NULL COMMENT 'Academic year',
  head_teacher_id BIGINT UNSIGNED NULL COMMENT 'Head teacher ID',
  default_video_path VARCHAR(255) NULL COMMENT 'Default monitor video path',
  enabled TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Whether class is enabled',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  PRIMARY KEY (id),
  UNIQUE KEY uk_edu_class_code (class_code),
  KEY idx_edu_class_name (class_name),
  KEY idx_edu_class_head_teacher_id (head_teacher_id),
  CONSTRAINT fk_edu_class_head_teacher FOREIGN KEY (head_teacher_id) REFERENCES edu_teacher (id) ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Teaching class';

CREATE TABLE IF NOT EXISTS edu_subject (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  subject_code VARCHAR(64) NOT NULL COMMENT 'Subject code',
  subject_name VARCHAR(64) NOT NULL COMMENT 'Subject name',
  enabled TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Whether subject is enabled',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  PRIMARY KEY (id),
  UNIQUE KEY uk_edu_subject_code (subject_code),
  KEY idx_edu_subject_name (subject_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Subject dictionary';

CREATE TABLE IF NOT EXISTS edu_teacher_class (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  teacher_id BIGINT UNSIGNED NOT NULL COMMENT 'Teacher ID',
  class_id BIGINT UNSIGNED NOT NULL COMMENT 'Class ID',
  subject_id BIGINT UNSIGNED NULL COMMENT 'Subject ID',
  relation_type VARCHAR(32) NOT NULL COMMENT 'HEAD_TEACHER, SUBJECT_TEACHER, OBSERVER',
  can_view_monitor TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Can view monitor sessions',
  can_start_monitor TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Can start monitor sessions',
  can_review TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Can write teaching review',
  start_date DATE NULL COMMENT 'Permission start date',
  end_date DATE NULL COMMENT 'Permission end date',
  enabled TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Whether relation is enabled',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  PRIMARY KEY (id),
  UNIQUE KEY uk_edu_teacher_class_scope (teacher_id, class_id, subject_id, relation_type),
  KEY idx_edu_teacher_class_class_id (class_id),
  KEY idx_edu_teacher_class_subject_id (subject_id),
  KEY idx_edu_teacher_class_enabled (enabled),
  CONSTRAINT fk_edu_teacher_class_teacher FOREIGN KEY (teacher_id) REFERENCES edu_teacher (id) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_edu_teacher_class_class FOREIGN KEY (class_id) REFERENCES edu_class (id) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_edu_teacher_class_subject FOREIGN KEY (subject_id) REFERENCES edu_subject (id) ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Teacher class permission and teaching relation';

CREATE TABLE IF NOT EXISTS monitor_session (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  session_no VARCHAR(64) NOT NULL COMMENT 'Monitor session number',
  class_id BIGINT UNSIGNED NOT NULL COMMENT 'Class ID',
  class_name VARCHAR(64) NOT NULL COMMENT 'Class name snapshot',
  teacher_id BIGINT UNSIGNED NULL COMMENT 'Teacher ID',
  teacher_name VARCHAR(64) NULL COMMENT 'Teacher name snapshot',
  subject_id BIGINT UNSIGNED NULL COMMENT 'Subject ID',
  subject_name VARCHAR(64) NULL COMMENT 'Subject name snapshot',
  lesson_title VARCHAR(128) NULL COMMENT 'Lesson title',
  operator_user_id BIGINT UNSIGNED NULL COMMENT 'User who starts monitor',
  operator_name VARCHAR(64) NULL COMMENT 'Operator name snapshot',
  video_path VARCHAR(255) NULL COMMENT 'Video path or stream source',
  img_width INT UNSIGNED NULL COMMENT 'Frame width',
  img_height INT UNSIGNED NULL COMMENT 'Frame height',
  status VARCHAR(16) NOT NULL DEFAULT 'RUNNING' COMMENT 'RUNNING, STOPPED, ERROR',
  started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Monitor start time',
  ended_at DATETIME NULL COMMENT 'Monitor end time',
  last_heartbeat_at DATETIME NULL COMMENT 'Last heartbeat time',
  total_seat_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Total detected seat count',
  warning_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Warning event count',
  notice_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Notice event count',
  event_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Total event count',
  detect_config_json JSON NULL COMMENT 'Detection configuration snapshot',
  vlm_config_json JSON NULL COMMENT 'VLM configuration snapshot',
  rule_config_json JSON NULL COMMENT 'Behavior rule configuration snapshot',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  PRIMARY KEY (id),
  UNIQUE KEY uk_monitor_session_no (session_no),
  KEY idx_monitor_session_class_time (class_id, started_at),
  KEY idx_monitor_session_teacher_time (teacher_id, started_at),
  KEY idx_monitor_session_subject_id (subject_id),
  KEY idx_monitor_session_operator_user_id (operator_user_id),
  KEY idx_monitor_session_status (status),
  CONSTRAINT fk_monitor_session_class FOREIGN KEY (class_id) REFERENCES edu_class (id) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_monitor_session_teacher FOREIGN KEY (teacher_id) REFERENCES edu_teacher (id) ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT fk_monitor_session_subject FOREIGN KEY (subject_id) REFERENCES edu_subject (id) ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT fk_monitor_session_operator FOREIGN KEY (operator_user_id) REFERENCES sys_user (id) ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Classroom monitor session';

CREATE TABLE IF NOT EXISTS monitor_session_seat (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  session_id BIGINT UNSIGNED NOT NULL COMMENT 'Monitor session ID',
  runtime_seat_id INT UNSIGNED NOT NULL COMMENT 'Runtime seat ID from detection process',
  seat_code VARCHAR(32) NOT NULL COMMENT 'Seat code, for example S01',
  box_x1 DECIMAL(10,2) NOT NULL COMMENT 'Bounding box x1',
  box_y1 DECIMAL(10,2) NOT NULL COMMENT 'Bounding box y1',
  box_x2 DECIMAL(10,2) NOT NULL COMMENT 'Bounding box x2',
  box_y2 DECIMAL(10,2) NOT NULL COMMENT 'Bounding box y2',
  status VARCHAR(32) NOT NULL DEFAULT 'NORMAL' COMMENT 'NORMAL, HEAD_DOWN, DESK_LYING, TURNING_HEAD, EATING',
  det_category INT NULL COMMENT 'Detection category ID',
  analysis_source VARCHAR(32) NULL COMMENT 'DETECT, VLM',
  locked_abnormal TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Whether abnormal status is locked',
  first_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'First seen time',
  last_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Last seen time',
  PRIMARY KEY (id),
  UNIQUE KEY uk_monitor_session_runtime_seat (session_id, runtime_seat_id),
  KEY idx_monitor_session_seat_session_status (session_id, status),
  CONSTRAINT fk_monitor_session_seat_session FOREIGN KEY (session_id) REFERENCES monitor_session (id) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Seat snapshot in a monitor session';

CREATE TABLE IF NOT EXISTS monitor_behavior_event (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  event_uid VARCHAR(64) NOT NULL COMMENT 'Event unique ID exposed to frontend',
  session_id BIGINT UNSIGNED NOT NULL COMMENT 'Monitor session ID',
  class_id BIGINT UNSIGNED NOT NULL COMMENT 'Class ID',
  seat_id BIGINT UNSIGNED NULL COMMENT 'Seat snapshot ID',
  seat_code VARCHAR(32) NOT NULL COMMENT 'Seat code snapshot',
  level VARCHAR(16) NOT NULL COMMENT '警告, 提示',
  status VARCHAR(32) NOT NULL COMMENT 'NORMAL, HEAD_DOWN, DESK_LYING, TURNING_HEAD, EATING',
  label VARCHAR(128) NOT NULL DEFAULT '' COMMENT 'Display label',
  reason TEXT NULL COMMENT 'Analysis reason',
  source VARCHAR(32) NOT NULL DEFAULT 'DETECT' COMMENT 'Event source',
  analysis_source VARCHAR(32) NOT NULL DEFAULT 'DETECT' COMMENT 'Latest analysis source',
  image_url VARCHAR(255) NULL COMMENT 'Event image URL',
  image_path VARCHAR(255) NULL COMMENT 'Event image file path',
  box_x1 DECIMAL(10,2) NULL COMMENT 'Bounding box x1',
  box_y1 DECIMAL(10,2) NULL COMMENT 'Bounding box y1',
  box_x2 DECIMAL(10,2) NULL COMMENT 'Bounding box x2',
  box_y2 DECIMAL(10,2) NULL COMMENT 'Bounding box y2',
  event_time DATETIME NOT NULL COMMENT 'Event time',
  confirmed_by_vlm TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Whether confirmed by VLM',
  handle_status VARCHAR(32) NOT NULL DEFAULT 'UNHANDLED' COMMENT 'UNHANDLED, HANDLED, IGNORED',
  handled_by BIGINT UNSIGNED NULL COMMENT 'Handler user ID',
  handled_at DATETIME NULL COMMENT 'Handle time',
  handle_remark VARCHAR(500) NULL COMMENT 'Handle remark',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  PRIMARY KEY (id),
  UNIQUE KEY uk_monitor_behavior_event_uid (event_uid),
  KEY idx_monitor_behavior_event_session_time (session_id, event_time),
  KEY idx_monitor_behavior_event_class_time (class_id, event_time),
  KEY idx_monitor_behavior_event_seat_id (seat_id),
  KEY idx_monitor_behavior_event_level_status (level, status),
  KEY idx_monitor_behavior_event_handle_status (handle_status),
  KEY idx_monitor_behavior_event_handled_by (handled_by),
  CONSTRAINT fk_monitor_behavior_event_session FOREIGN KEY (session_id) REFERENCES monitor_session (id) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_monitor_behavior_event_class FOREIGN KEY (class_id) REFERENCES edu_class (id) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_monitor_behavior_event_seat FOREIGN KEY (seat_id) REFERENCES monitor_session_seat (id) ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT fk_monitor_behavior_event_handler FOREIGN KEY (handled_by) REFERENCES sys_user (id) ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Abnormal behavior event';

CREATE TABLE IF NOT EXISTS monitor_event_frame (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  event_id BIGINT UNSIGNED NOT NULL COMMENT 'Behavior event ID',
  frame_index INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Frame index in event detail',
  frame_time DATETIME NULL COMMENT 'Frame time',
  focus_image_url VARCHAR(255) NULL COMMENT 'Focus image URL',
  focus_image_path VARCHAR(255) NULL COMMENT 'Focus image file path',
  seat_code VARCHAR(32) NULL COMMENT 'Seat code snapshot',
  status VARCHAR(32) NULL COMMENT 'Seat status',
  status_text VARCHAR(64) NULL COMMENT 'Seat status display text',
  ratio DECIMAL(10,4) NULL COMMENT 'Analysis ratio',
  box_conf DECIMAL(10,4) NULL COMMENT 'Detection confidence',
  box_x1 DECIMAL(10,2) NULL COMMENT 'Bounding box x1',
  box_y1 DECIMAL(10,2) NULL COMMENT 'Bounding box y1',
  box_x2 DECIMAL(10,2) NULL COMMENT 'Bounding box x2',
  box_y2 DECIMAL(10,2) NULL COMMENT 'Bounding box y2',
  raw_payload_json JSON NULL COMMENT 'Raw frame payload for frontend detail',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  PRIMARY KEY (id),
  KEY idx_monitor_event_frame_event_index (event_id, frame_index),
  CONSTRAINT fk_monitor_event_frame_event FOREIGN KEY (event_id) REFERENCES monitor_behavior_event (id) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Event detail frame';

CREATE TABLE IF NOT EXISTS monitor_vlm_review (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  event_id BIGINT UNSIGNED NULL COMMENT 'Behavior event ID',
  session_id BIGINT UNSIGNED NOT NULL COMMENT 'Monitor session ID',
  seat_id BIGINT UNSIGNED NULL COMMENT 'Seat snapshot ID',
  model_name VARCHAR(64) NOT NULL DEFAULT 'qwen-vl-max' COMMENT 'VLM model name',
  request_image_url VARCHAR(255) NULL COMMENT 'Request image URL',
  request_image_path VARCHAR(255) NULL COMMENT 'Request image file path',
  raw_response LONGTEXT NULL COMMENT 'Raw VLM response',
  parsed_status VARCHAR(32) NULL COMMENT 'Parsed status',
  parsed_label VARCHAR(128) NULL COMMENT 'Parsed label',
  parsed_reason TEXT NULL COMMENT 'Parsed reason',
  success TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Whether review succeeded',
  error_message TEXT NULL COMMENT 'Error message if failed',
  latency_ms INT UNSIGNED NULL COMMENT 'Review latency in milliseconds',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  PRIMARY KEY (id),
  KEY idx_monitor_vlm_review_event_id (event_id),
  KEY idx_monitor_vlm_review_session_id (session_id),
  KEY idx_monitor_vlm_review_seat_id (seat_id),
  KEY idx_monitor_vlm_review_created_at (created_at),
  CONSTRAINT fk_monitor_vlm_review_event FOREIGN KEY (event_id) REFERENCES monitor_behavior_event (id) ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT fk_monitor_vlm_review_session FOREIGN KEY (session_id) REFERENCES monitor_session (id) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_monitor_vlm_review_seat FOREIGN KEY (seat_id) REFERENCES monitor_session_seat (id) ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='VLM review record';

CREATE TABLE IF NOT EXISTS monitor_teaching_review (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  session_id BIGINT UNSIGNED NOT NULL COMMENT 'Monitor session ID',
  teacher_id BIGINT UNSIGNED NOT NULL COMMENT 'Reviewer teacher ID',
  review_status VARCHAR(16) NOT NULL DEFAULT 'PENDING' COMMENT 'PENDING, REVIEWED',
  teaching_effect_score DECIMAL(5,2) NULL COMMENT 'Teaching effect score',
  focus_summary TEXT NULL COMMENT 'Focus summary',
  problem_summary TEXT NULL COMMENT 'Problem summary',
  improvement_plan TEXT NULL COMMENT 'Improvement plan',
  reviewed_at DATETIME NULL COMMENT 'Review time',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  PRIMARY KEY (id),
  UNIQUE KEY uk_monitor_teaching_review_teacher (session_id, teacher_id),
  KEY idx_monitor_teaching_review_teacher_id (teacher_id),
  KEY idx_monitor_teaching_review_status (review_status),
  CONSTRAINT fk_monitor_teaching_review_session FOREIGN KEY (session_id) REFERENCES monitor_session (id) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_monitor_teaching_review_teacher FOREIGN KEY (teacher_id) REFERENCES edu_teacher (id) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Teacher after-class teaching review';

INSERT IGNORE INTO sys_role (role_code, role_name, description, enabled) VALUES
('ADMIN', '系统管理员', '拥有系统配置、用户管理和全部监控记录查看权限', 1),
('TEACHER', '教师', '查看授权班级监控记录并提交教学复盘', 1),
('OPERATOR', '监控操作员', '启动和停止课堂监控任务', 1),
('VIEWER', '只读用户', '只读查看授权范围内的监控记录', 1);

INSERT IGNORE INTO sys_user (username, password_hash, real_name, status) VALUES
('admin', 'CHANGE_ME_WITH_BCRYPT_HASH', '系统管理员', 'DISABLED');

INSERT IGNORE INTO sys_user_role (user_id, role_id)
SELECT u.id, r.id
FROM sys_user u
JOIN sys_role r ON r.role_code = 'ADMIN'
WHERE u.username = 'admin';

INSERT IGNORE INTO edu_subject (subject_code, subject_name, enabled) VALUES
('GENERAL', '通用课程', 1),
('CHINESE', '语文', 1),
('MATH', '数学', 1),
('ENGLISH', '英语', 1),
('PHYSICS', '物理', 1);

INSERT IGNORE INTO edu_class (class_code, class_name, grade_name, academic_year, default_video_path, enabled) VALUES
('CLASS_1', '1班', NULL, NULL, 'inputs/test.mp4', 1),
('CLASS_2', '2班', NULL, NULL, 'inputs/v1.mp4', 1),
('CLASS_3', '3班', NULL, NULL, 'inputs/v2.mp4', 1),
('CLASS_4', '4班', NULL, NULL, 'inputs/v3.mp4', 1);
