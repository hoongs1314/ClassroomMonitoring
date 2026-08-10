-- 运行时完整性增量：阻止多实例调度为同一课表时段重复创建课次。
-- 该脚本不会删除历史数据；若已有重复记录，ALTER 会失败并保留原表，请先人工核对后再执行。
SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE monitor_session ADD CONSTRAINT uk_monitor_session_schedule_start UNIQUE (schedule_id, planned_started_at)',
    'SELECT 1'
  )
  FROM information_schema.table_constraints
  WHERE table_schema = DATABASE()
    AND table_name = 'monitor_session'
    AND constraint_name = 'uk_monitor_session_schedule_start'
);
PREPARE migration_statement FROM @sql;
EXECUTE migration_statement;
DEALLOCATE PREPARE migration_statement;
