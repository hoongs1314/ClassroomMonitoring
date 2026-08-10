-- 课后教学分析改造增量脚本。
-- 执行前请先完成 db/001_init_mysql.sql；本脚本不删除既有监控与复盘数据。

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS edu_academic_year (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  year_name VARCHAR(32) NOT NULL COMMENT 'Academic year name, e.g. 2026-2027',
  start_date DATE NOT NULL COMMENT 'Start date',
  end_date DATE NOT NULL COMMENT 'End date',
  status VARCHAR(16) NOT NULL DEFAULT 'ENABLED' COMMENT 'ENABLED, DISABLED',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  PRIMARY KEY (id),
  UNIQUE KEY uk_edu_academic_year_name (year_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Academic year';

CREATE TABLE IF NOT EXISTS edu_academic_term (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  academic_year_id BIGINT UNSIGNED NOT NULL COMMENT 'Academic year ID',
  term_name VARCHAR(64) NOT NULL COMMENT 'Term name',
  start_date DATE NOT NULL COMMENT 'Start date',
  end_date DATE NOT NULL COMMENT 'End date',
  status VARCHAR(16) NOT NULL DEFAULT 'ENABLED' COMMENT 'ENABLED, DISABLED',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  PRIMARY KEY (id),
  UNIQUE KEY uk_edu_academic_term_name (academic_year_id, term_name),
  KEY idx_edu_academic_term_dates (start_date, end_date),
  CONSTRAINT fk_edu_academic_term_year FOREIGN KEY (academic_year_id) REFERENCES edu_academic_year (id) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Academic term';

CREATE TABLE IF NOT EXISTS teaching_course (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  course_no VARCHAR(64) NOT NULL COMMENT 'Teaching course number',
  term_id BIGINT UNSIGNED NOT NULL COMMENT 'Term ID',
  class_id BIGINT UNSIGNED NOT NULL COMMENT 'Class ID',
  subject_id BIGINT UNSIGNED NOT NULL COMMENT 'Subject ID',
  teacher_id BIGINT UNSIGNED NULL COMMENT 'Teacher ID, assigned after schedule setup when needed',
  course_name VARCHAR(128) NOT NULL COMMENT 'Course display name',
  planned_lesson_count INT UNSIGNED NULL COMMENT 'Planned lesson count',
  start_date DATE NULL COMMENT 'Start date',
  end_date DATE NULL COMMENT 'End date',
  status VARCHAR(16) NOT NULL DEFAULT 'DRAFT' COMMENT 'DRAFT, ACTIVE, FINISHED, ARCHIVED',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  PRIMARY KEY (id),
  UNIQUE KEY uk_teaching_course_no (course_no),
  KEY idx_teaching_course_teacher_term (teacher_id, term_id),
  KEY idx_teaching_course_class_term (class_id, term_id),
  CONSTRAINT fk_teaching_course_term FOREIGN KEY (term_id) REFERENCES edu_academic_term (id) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_teaching_course_class FOREIGN KEY (class_id) REFERENCES edu_class (id) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_teaching_course_subject FOREIGN KEY (subject_id) REFERENCES edu_subject (id) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_teaching_course_teacher FOREIGN KEY (teacher_id) REFERENCES edu_teacher (id) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Class subject course, teacher assignment optional';

CREATE TABLE IF NOT EXISTS edu_lesson_schedule (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  teaching_course_id BIGINT UNSIGNED NOT NULL COMMENT 'Teaching course ID',
  weekday TINYINT UNSIGNED NOT NULL COMMENT '1 Monday through 7 Sunday',
  start_time VARCHAR(8) NOT NULL COMMENT 'HH:MM',
  end_time VARCHAR(8) NOT NULL COMMENT 'HH:MM',
  lesson_title VARCHAR(128) NULL COMMENT 'Default lesson title',
  enabled TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Whether enabled',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  PRIMARY KEY (id),
  UNIQUE KEY uk_edu_lesson_schedule_time (teaching_course_id, weekday, start_time),
  KEY idx_edu_lesson_schedule_weekday_time (weekday, start_time, end_time),
  CONSTRAINT fk_edu_lesson_schedule_course FOREIGN KEY (teaching_course_id) REFERENCES teaching_course (id) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Weekly lesson schedule';

CREATE TABLE IF NOT EXISTS camera_device (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  device_code VARCHAR(64) NOT NULL COMMENT 'Device code',
  device_name VARCHAR(128) NOT NULL COMMENT 'Device name',
  location VARCHAR(255) NULL COMMENT 'Fixed installation location',
  source_path VARCHAR(255) NULL COMMENT 'Internal source configuration',
  enabled TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Whether enabled',
  remark VARCHAR(500) NULL COMMENT 'Remark',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  PRIMARY KEY (id),
  UNIQUE KEY uk_camera_device_code (device_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Fixed camera device';

CREATE TABLE IF NOT EXISTS camera_class_binding (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  camera_id BIGINT UNSIGNED NOT NULL COMMENT 'Camera ID',
  class_id BIGINT UNSIGNED NOT NULL COMMENT 'Class ID',
  effective_start_date DATE NOT NULL COMMENT 'Effective start date',
  effective_end_date DATE NULL COMMENT 'Effective end date, exclusive',
  enabled TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'Whether enabled',
  remark VARCHAR(500) NULL COMMENT 'Change remark',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  PRIMARY KEY (id),
  UNIQUE KEY uk_camera_class_binding_start (camera_id, class_id, effective_start_date),
  KEY idx_camera_class_binding_class_dates (class_id, effective_start_date, effective_end_date),
  CONSTRAINT fk_camera_class_binding_camera FOREIGN KEY (camera_id) REFERENCES camera_device (id) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_camera_class_binding_class FOREIGN KEY (class_id) REFERENCES edu_class (id) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Camera class effective binding';

-- MySQL 8.4 不支持 ALTER TABLE ... ADD COLUMN IF NOT EXISTS，以下通过元数据检查保持脚本可重复执行。
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE monitor_session ADD COLUMN term_id BIGINT UNSIGNED NULL COMMENT ''Term snapshot ID''', 'SELECT 1') FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'monitor_session' AND column_name = 'term_id');
PREPARE migration_statement FROM @sql; EXECUTE migration_statement; DEALLOCATE PREPARE migration_statement;
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE monitor_session ADD COLUMN teaching_course_id BIGINT UNSIGNED NULL COMMENT ''Teaching course snapshot ID''', 'SELECT 1') FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'monitor_session' AND column_name = 'teaching_course_id');
PREPARE migration_statement FROM @sql; EXECUTE migration_statement; DEALLOCATE PREPARE migration_statement;
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE monitor_session ADD COLUMN schedule_id BIGINT UNSIGNED NULL COMMENT ''Schedule snapshot ID''', 'SELECT 1') FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'monitor_session' AND column_name = 'schedule_id');
PREPARE migration_statement FROM @sql; EXECUTE migration_statement; DEALLOCATE PREPARE migration_statement;
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE monitor_session ADD COLUMN camera_id BIGINT UNSIGNED NULL COMMENT ''Camera snapshot ID''', 'SELECT 1') FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'monitor_session' AND column_name = 'camera_id');
PREPARE migration_statement FROM @sql; EXECUTE migration_statement; DEALLOCATE PREPARE migration_statement;
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE monitor_session ADD COLUMN camera_binding_id BIGINT UNSIGNED NULL COMMENT ''Camera binding snapshot ID''', 'SELECT 1') FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'monitor_session' AND column_name = 'camera_binding_id');
PREPARE migration_statement FROM @sql; EXECUTE migration_statement; DEALLOCATE PREPARE migration_statement;
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE monitor_session ADD COLUMN analysis_status VARCHAR(16) NOT NULL DEFAULT ''PENDING'' COMMENT ''PENDING, RUNNING, COMPLETED, FAILED''', 'SELECT 1') FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'monitor_session' AND column_name = 'analysis_status');
PREPARE migration_statement FROM @sql; EXECUTE migration_statement; DEALLOCATE PREPARE migration_statement;
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE monitor_session ADD COLUMN planned_started_at DATETIME NULL COMMENT ''Schedule start time''', 'SELECT 1') FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'monitor_session' AND column_name = 'planned_started_at');
PREPARE migration_statement FROM @sql; EXECUTE migration_statement; DEALLOCATE PREPARE migration_statement;
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE monitor_session ADD COLUMN planned_ended_at DATETIME NULL COMMENT ''Schedule end time''', 'SELECT 1') FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'monitor_session' AND column_name = 'planned_ended_at');
PREPARE migration_statement FROM @sql; EXECUTE migration_statement; DEALLOCATE PREPARE migration_statement;
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE monitor_session ADD COLUMN analysis_completed_at DATETIME NULL COMMENT ''Analysis completion time''', 'SELECT 1') FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'monitor_session' AND column_name = 'analysis_completed_at');
PREPARE migration_statement FROM @sql; EXECUTE migration_statement; DEALLOCATE PREPARE migration_statement;

SET @sql = (SELECT IF(COUNT(*) = 0, 'CREATE INDEX idx_monitor_session_teaching_course_time ON monitor_session (teaching_course_id, started_at)', 'SELECT 1') FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = 'monitor_session' AND index_name = 'idx_monitor_session_teaching_course_time');
PREPARE migration_statement FROM @sql; EXECUTE migration_statement; DEALLOCATE PREPARE migration_statement;
SET @sql = (SELECT IF(COUNT(*) = 0, 'CREATE INDEX idx_monitor_session_schedule_time ON monitor_session (schedule_id, planned_started_at)', 'SELECT 1') FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = 'monitor_session' AND index_name = 'idx_monitor_session_schedule_time');
PREPARE migration_statement FROM @sql; EXECUTE migration_statement; DEALLOCATE PREPARE migration_statement;
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE monitor_session ADD CONSTRAINT fk_monitor_session_term FOREIGN KEY (term_id) REFERENCES edu_academic_term (id) ON UPDATE CASCADE ON DELETE SET NULL', 'SELECT 1') FROM information_schema.table_constraints WHERE table_schema = DATABASE() AND table_name = 'monitor_session' AND constraint_name = 'fk_monitor_session_term');
PREPARE migration_statement FROM @sql; EXECUTE migration_statement; DEALLOCATE PREPARE migration_statement;
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE monitor_session ADD CONSTRAINT fk_monitor_session_course FOREIGN KEY (teaching_course_id) REFERENCES teaching_course (id) ON UPDATE CASCADE ON DELETE SET NULL', 'SELECT 1') FROM information_schema.table_constraints WHERE table_schema = DATABASE() AND table_name = 'monitor_session' AND constraint_name = 'fk_monitor_session_course');
PREPARE migration_statement FROM @sql; EXECUTE migration_statement; DEALLOCATE PREPARE migration_statement;
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE monitor_session ADD CONSTRAINT fk_monitor_session_schedule FOREIGN KEY (schedule_id) REFERENCES edu_lesson_schedule (id) ON UPDATE CASCADE ON DELETE SET NULL', 'SELECT 1') FROM information_schema.table_constraints WHERE table_schema = DATABASE() AND table_name = 'monitor_session' AND constraint_name = 'fk_monitor_session_schedule');
PREPARE migration_statement FROM @sql; EXECUTE migration_statement; DEALLOCATE PREPARE migration_statement;
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE monitor_session ADD CONSTRAINT fk_monitor_session_camera FOREIGN KEY (camera_id) REFERENCES camera_device (id) ON UPDATE CASCADE ON DELETE SET NULL', 'SELECT 1') FROM information_schema.table_constraints WHERE table_schema = DATABASE() AND table_name = 'monitor_session' AND constraint_name = 'fk_monitor_session_camera');
PREPARE migration_statement FROM @sql; EXECUTE migration_statement; DEALLOCATE PREPARE migration_statement;
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE monitor_session ADD CONSTRAINT fk_monitor_session_camera_binding FOREIGN KEY (camera_binding_id) REFERENCES camera_class_binding (id) ON UPDATE CASCADE ON DELETE SET NULL', 'SELECT 1') FROM information_schema.table_constraints WHERE table_schema = DATABASE() AND table_name = 'monitor_session' AND constraint_name = 'fk_monitor_session_camera_binding');
PREPARE migration_statement FROM @sql; EXECUTE migration_statement; DEALLOCATE PREPARE migration_statement;

CREATE TABLE IF NOT EXISTS lesson_analysis_run (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  session_id BIGINT UNSIGNED NOT NULL COMMENT 'Session ID',
  run_no INT UNSIGNED NOT NULL COMMENT 'Run number per session',
  run_status VARCHAR(16) NOT NULL DEFAULT 'PENDING' COMMENT 'PENDING, RUNNING, COMPLETED, FAILED',
  is_current TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Whether current run',
  model_name VARCHAR(128) NULL COMMENT 'Model name',
  model_version VARCHAR(128) NULL COMMENT 'Model version',
  rule_version VARCHAR(64) NULL COMMENT 'Rule version',
  config_json JSON NULL COMMENT 'Analysis configuration snapshot',
  started_at DATETIME NULL COMMENT 'Run start time',
  finished_at DATETIME NULL COMMENT 'Run finish time',
  error_message TEXT NULL COMMENT 'Failure message',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  PRIMARY KEY (id),
  UNIQUE KEY uk_lesson_analysis_run_no (session_id, run_no),
  KEY idx_lesson_analysis_run_session_status (session_id, run_status),
  CONSTRAINT fk_lesson_analysis_run_session FOREIGN KEY (session_id) REFERENCES monitor_session (id) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Repeatable lesson analysis run';

SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE monitor_behavior_event ADD COLUMN analysis_run_id BIGINT UNSIGNED NULL COMMENT ''Analysis run ID''', 'SELECT 1') FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'monitor_behavior_event' AND column_name = 'analysis_run_id');
PREPARE migration_statement FROM @sql; EXECUTE migration_statement; DEALLOCATE PREPARE migration_statement;
SET @sql = (SELECT IF(COUNT(*) = 0, 'CREATE INDEX idx_monitor_behavior_event_run_time ON monitor_behavior_event (analysis_run_id, event_time)', 'SELECT 1') FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = 'monitor_behavior_event' AND index_name = 'idx_monitor_behavior_event_run_time');
PREPARE migration_statement FROM @sql; EXECUTE migration_statement; DEALLOCATE PREPARE migration_statement;
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE monitor_behavior_event ADD CONSTRAINT fk_monitor_behavior_event_analysis_run FOREIGN KEY (analysis_run_id) REFERENCES lesson_analysis_run (id) ON UPDATE CASCADE ON DELETE SET NULL', 'SELECT 1') FROM information_schema.table_constraints WHERE table_schema = DATABASE() AND table_name = 'monitor_behavior_event' AND constraint_name = 'fk_monitor_behavior_event_analysis_run');
PREPARE migration_statement FROM @sql; EXECUTE migration_statement; DEALLOCATE PREPARE migration_statement;

CREATE TABLE IF NOT EXISTS lesson_analysis_summary (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  analysis_run_id BIGINT UNSIGNED NOT NULL COMMENT 'Analysis run ID',
  planned_duration_seconds INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Scheduled duration',
  valid_analysis_seconds INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Effective analysis duration',
  sampled_frame_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Sampled frame count',
  valid_frame_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Valid frame count',
  avg_detected_seat_count DECIMAL(10,2) NULL COMMENT 'Average detected seats',
  event_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Event count',
  confirmed_event_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'VLM confirmed count',
  data_quality_level VARCHAR(16) NOT NULL DEFAULT 'LIMITED' COMMENT 'GOOD, LIMITED, UNAVAILABLE',
  quality_remark TEXT NULL COMMENT 'Quality remark',
  generated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Generation time',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  PRIMARY KEY (id),
  UNIQUE KEY uk_lesson_analysis_summary_run (analysis_run_id),
  CONSTRAINT fk_lesson_analysis_summary_run FOREIGN KEY (analysis_run_id) REFERENCES lesson_analysis_run (id) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Lesson analysis summary';

CREATE TABLE IF NOT EXISTS lesson_behavior_stat (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  summary_id BIGINT UNSIGNED NOT NULL COMMENT 'Lesson summary ID',
  behavior_code VARCHAR(32) NOT NULL COMMENT 'Behavior status code',
  segment_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Merged segment count',
  event_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Event count',
  total_duration_seconds INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Total duration',
  duration_ratio DECIMAL(10,4) NOT NULL DEFAULT 0 COMMENT 'Duration ratio',
  vlm_confirmed_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'VLM confirmed count',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  PRIMARY KEY (id),
  UNIQUE KEY uk_lesson_behavior_stat (summary_id, behavior_code),
  CONSTRAINT fk_lesson_behavior_stat_summary FOREIGN KEY (summary_id) REFERENCES lesson_analysis_summary (id) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Lesson behavior statistics';

CREATE TABLE IF NOT EXISTS course_analysis_aggregate (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  aggregate_no VARCHAR(64) NOT NULL COMMENT 'Aggregate number',
  teaching_course_id BIGINT UNSIGNED NOT NULL COMMENT 'Teaching course ID',
  scope_type VARCHAR(16) NOT NULL COMMENT 'WEEK, MONTH, TERM, CUSTOM',
  period_start_date DATE NOT NULL COMMENT 'Inclusive start date',
  period_end_date DATE NOT NULL COMMENT 'Exclusive end date',
  source_session_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Source sessions',
  completed_session_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Completed sessions',
  valid_analysis_seconds INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Effective analysis duration',
  data_quality_level VARCHAR(16) NOT NULL DEFAULT 'LIMITED' COMMENT 'GOOD, LIMITED, UNAVAILABLE',
  calculation_version INT UNSIGNED NOT NULL DEFAULT 1 COMMENT 'Calculation version',
  aggregate_status VARCHAR(16) NOT NULL DEFAULT 'DRAFT' COMMENT 'DRAFT, READY, OUTDATED',
  calculated_at DATETIME NULL COMMENT 'Calculation time',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  PRIMARY KEY (id),
  UNIQUE KEY uk_course_analysis_aggregate (teaching_course_id, scope_type, period_start_date, period_end_date, calculation_version),
  UNIQUE KEY uk_course_analysis_aggregate_no (aggregate_no),
  CONSTRAINT fk_course_analysis_aggregate_course FOREIGN KEY (teaching_course_id) REFERENCES teaching_course (id) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Course period aggregate';

CREATE TABLE IF NOT EXISTS course_behavior_stat (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  aggregate_id BIGINT UNSIGNED NOT NULL COMMENT 'Aggregate ID',
  behavior_code VARCHAR(32) NOT NULL COMMENT 'Behavior status code',
  segment_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Merged segment count',
  event_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Event count',
  total_duration_seconds INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Total duration',
  average_per_session DECIMAL(10,4) NOT NULL DEFAULT 0 COMMENT 'Average event count',
  average_duration_ratio DECIMAL(10,4) NOT NULL DEFAULT 0 COMMENT 'Average duration ratio',
  session_coverage_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Sessions containing behavior',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  PRIMARY KEY (id),
  UNIQUE KEY uk_course_behavior_stat (aggregate_id, behavior_code),
  CONSTRAINT fk_course_behavior_stat_aggregate FOREIGN KEY (aggregate_id) REFERENCES course_analysis_aggregate (id) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Course behavior statistics';

CREATE TABLE IF NOT EXISTS course_aggregate_source (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  aggregate_id BIGINT UNSIGNED NOT NULL COMMENT 'Aggregate ID',
  session_id BIGINT UNSIGNED NOT NULL COMMENT 'Session ID',
  analysis_run_id BIGINT UNSIGNED NOT NULL COMMENT 'Analysis run ID',
  summary_id BIGINT UNSIGNED NOT NULL COMMENT 'Summary ID',
  included_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Included time',
  PRIMARY KEY (id),
  UNIQUE KEY uk_course_aggregate_source (aggregate_id, summary_id),
  CONSTRAINT fk_course_aggregate_source_aggregate FOREIGN KEY (aggregate_id) REFERENCES course_analysis_aggregate (id) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_course_aggregate_source_session FOREIGN KEY (session_id) REFERENCES monitor_session (id) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_course_aggregate_source_run FOREIGN KEY (analysis_run_id) REFERENCES lesson_analysis_run (id) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_course_aggregate_source_summary FOREIGN KEY (summary_id) REFERENCES lesson_analysis_summary (id) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Aggregate input snapshot';

CREATE TABLE IF NOT EXISTS teaching_analysis_report (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  report_no VARCHAR(64) NOT NULL COMMENT 'Report number',
  report_title VARCHAR(255) NOT NULL COMMENT 'Report title',
  report_scope VARCHAR(16) NOT NULL COMMENT 'LESSON, WEEK, MONTH, TERM, COURSE',
  session_id BIGINT UNSIGNED NULL COMMENT 'Lesson source',
  aggregate_id BIGINT UNSIGNED NULL COMMENT 'Aggregate source',
  teaching_course_id BIGINT UNSIGNED NULL COMMENT 'Course source',
  report_version INT UNSIGNED NOT NULL DEFAULT 1 COMMENT 'Report version',
  report_status VARCHAR(16) NOT NULL DEFAULT 'DRAFT' COMMENT 'DRAFT, PUBLISHED, ARCHIVED',
  generated_mode VARCHAR(32) NOT NULL DEFAULT 'SYSTEM' COMMENT 'SYSTEM, TEACHER_EDITED',
  overview_text TEXT NULL COMMENT 'Fact overview',
  finding_text TEXT NULL COMMENT 'Findings',
  suggestion_text TEXT NULL COMMENT 'Suggestions',
  teacher_conclusion TEXT NULL COMMENT 'Teacher conclusion',
  data_snapshot_json JSON NULL COMMENT 'Immutable data snapshot',
  export_file_path VARCHAR(255) NULL COMMENT 'Export path',
  generated_by BIGINT UNSIGNED NULL COMMENT 'Generated user ID',
  published_by BIGINT UNSIGNED NULL COMMENT 'Published user ID',
  published_at DATETIME NULL COMMENT 'Published time',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  PRIMARY KEY (id),
  UNIQUE KEY uk_teaching_analysis_report_no (report_no),
  KEY idx_teaching_analysis_report_course_status (teaching_course_id, report_status),
  CONSTRAINT fk_teaching_analysis_report_session FOREIGN KEY (session_id) REFERENCES monitor_session (id) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_teaching_analysis_report_aggregate FOREIGN KEY (aggregate_id) REFERENCES course_analysis_aggregate (id) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_teaching_analysis_report_course FOREIGN KEY (teaching_course_id) REFERENCES teaching_course (id) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_teaching_analysis_report_generated_by FOREIGN KEY (generated_by) REFERENCES sys_user (id) ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT fk_teaching_analysis_report_published_by FOREIGN KEY (published_by) REFERENCES sys_user (id) ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Teaching analysis report';

CREATE TABLE IF NOT EXISTS course_analysis_entry (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  teaching_course_id BIGINT UNSIGNED NOT NULL COMMENT 'Teaching course ID',
  session_id BIGINT UNSIGNED NOT NULL COMMENT 'Session ID',
  analysis_run_id BIGINT UNSIGNED NOT NULL COMMENT 'Analysis run ID',
  summary_id BIGINT UNSIGNED NOT NULL COMMENT 'Summary ID',
  report_id BIGINT UNSIGNED NULL COMMENT 'Lesson report ID',
  lesson_index INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Lesson order',
  lesson_date DATE NOT NULL COMMENT 'Lesson date',
  lesson_title VARCHAR(128) NULL COMMENT 'Lesson title',
  comparison_base_entry_id BIGINT UNSIGNED NULL COMMENT 'Comparison baseline entry',
  system_change_summary TEXT NULL COMMENT 'System factual change summary',
  teacher_change_note TEXT NULL COMMENT 'Teacher interpretation',
  is_baseline TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Whether baseline',
  is_milestone TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Whether milestone',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  PRIMARY KEY (id),
  UNIQUE KEY uk_course_analysis_entry_session (teaching_course_id, session_id),
  KEY idx_course_analysis_entry_course_date (teaching_course_id, lesson_date, lesson_index),
  CONSTRAINT fk_course_analysis_entry_course FOREIGN KEY (teaching_course_id) REFERENCES teaching_course (id) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_course_analysis_entry_session FOREIGN KEY (session_id) REFERENCES monitor_session (id) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_course_analysis_entry_run FOREIGN KEY (analysis_run_id) REFERENCES lesson_analysis_run (id) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_course_analysis_entry_summary FOREIGN KEY (summary_id) REFERENCES lesson_analysis_summary (id) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_course_analysis_entry_report FOREIGN KEY (report_id) REFERENCES teaching_analysis_report (id) ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT fk_course_analysis_entry_baseline FOREIGN KEY (comparison_base_entry_id) REFERENCES course_analysis_entry (id) ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Course lesson analysis timeline entry';

CREATE TABLE IF NOT EXISTS teaching_improvement_action (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  teaching_course_id BIGINT UNSIGNED NOT NULL COMMENT 'Teaching course ID',
  source_entry_id BIGINT UNSIGNED NOT NULL COMMENT 'Problem source entry',
  issue_type VARCHAR(64) NULL COMMENT 'Issue category',
  issue_description TEXT NOT NULL COMMENT 'Issue description',
  improvement_plan TEXT NOT NULL COMMENT 'Improvement plan',
  planned_for_entry_id BIGINT UNSIGNED NULL COMMENT 'Planned execution entry',
  action_status VARCHAR(16) NOT NULL DEFAULT 'PLANNED' COMMENT 'PLANNED, IMPLEMENTED, VERIFIED, CLOSED',
  implemented_at DATETIME NULL COMMENT 'Implementation time',
  verified_by_entry_id BIGINT UNSIGNED NULL COMMENT 'Verification entry',
  verification_note TEXT NULL COMMENT 'Teacher verification note',
  created_by BIGINT UNSIGNED NOT NULL COMMENT 'Teacher ID',
  verified_at DATETIME NULL COMMENT 'Verification time',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  PRIMARY KEY (id),
  KEY idx_teaching_improvement_course_status (teaching_course_id, action_status),
  CONSTRAINT fk_teaching_improvement_course FOREIGN KEY (teaching_course_id) REFERENCES teaching_course (id) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_teaching_improvement_source FOREIGN KEY (source_entry_id) REFERENCES course_analysis_entry (id) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_teaching_improvement_planned FOREIGN KEY (planned_for_entry_id) REFERENCES course_analysis_entry (id) ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT fk_teaching_improvement_verified FOREIGN KEY (verified_by_entry_id) REFERENCES course_analysis_entry (id) ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT fk_teaching_improvement_teacher FOREIGN KEY (created_by) REFERENCES edu_teacher (id) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Teaching improvement action loop';

CREATE TABLE IF NOT EXISTS teaching_report_evidence (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
  report_id BIGINT UNSIGNED NOT NULL COMMENT 'Report ID',
  session_id BIGINT UNSIGNED NOT NULL COMMENT 'Session ID',
  event_id BIGINT UNSIGNED NULL COMMENT 'Event ID',
  evidence_type VARCHAR(32) NOT NULL COMMENT 'HIGHLIGHT, ISSUE, SUGGESTION_SOURCE',
  sort_no INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Display order',
  remark TEXT NULL COMMENT 'Report remark',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Create time',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Update time',
  PRIMARY KEY (id),
  UNIQUE KEY uk_teaching_report_evidence (report_id, event_id, evidence_type),
  CONSTRAINT fk_teaching_report_evidence_report FOREIGN KEY (report_id) REFERENCES teaching_analysis_report (id) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_teaching_report_evidence_session FOREIGN KEY (session_id) REFERENCES monitor_session (id) ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_teaching_report_evidence_event FOREIGN KEY (event_id) REFERENCES monitor_behavior_event (id) ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Report evidence reference';
