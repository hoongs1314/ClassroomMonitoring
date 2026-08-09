"""课后分析汇总、课程串联和周期统计服务。"""

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from uuid import uuid4

from sqlalchemy import func

from domain.models import (
	CourseAggregateSource,
	CourseAnalysisAggregate,
	CourseAnalysisEntry,
	CourseBehaviorStat,
	EduAcademicTerm,
	LessonAnalysisRun,
	LessonAnalysisSummary,
	LessonBehaviorStat,
	MonitorBehaviorEvent,
	MonitorSession,
	TeachingAnalysisReport,
	TeachingCourse,
)


def _new_no(prefix):
	return f"{prefix}{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid4().hex[:6]}"


def _duration_seconds(started_at, ended_at):
	if not started_at or not ended_at or ended_at <= started_at:
		return 0
	return max(int((ended_at - started_at).total_seconds()), 0)


def _next_month_start(value):
	return date(value.year + 1, 1, 1) if value.month == 12 else date(value.year, value.month + 1, 1)


def _resolve_aggregate_period(db, course, scope_type, start_date, end_date):
	"""统一使用左闭右开的统计区间，防止周/月汇总被错误标记为整个学期。"""
	term = db.query(EduAcademicTerm).filter(EduAcademicTerm.id == course.term_id).first()
	course_start = course.start_date or (term.start_date if term else datetime.utcnow().date())
	course_end = (course.end_date or (term.end_date if term else datetime.utcnow().date())) + timedelta(days = 1)
	if scope_type == "TERM":
		if start_date or end_date:
			raise ValueError("学期汇总不接受自定义日期范围")
		return course_start, course_end
	if not start_date or not end_date:
		raise ValueError(f"{scope_type} 汇总必须同时提供 start_date 和 end_date")
	if end_date <= start_date:
		raise ValueError("汇总结束日期必须晚于开始日期")
	if start_date < course_start or end_date > course_end:
		raise ValueError("汇总日期必须位于教学课程有效期内")
	if scope_type == "WEEK" and (start_date.weekday() != 0 or end_date != start_date + timedelta(days = 7)):
		raise ValueError("周汇总必须从周一开始，且结束日期为下周一")
	if scope_type == "MONTH" and (start_date.day != 1 or end_date != _next_month_start(start_date)):
		raise ValueError("月汇总必须从当月 1 日开始，结束日期为下月 1 日")
	return start_date, end_date


def _serialize_behavior_counts(events):
	counts = defaultdict(lambda: { "event_count": 0, "confirmed_count": 0 })
	for event in events:
		row = counts[event.status]
		row["event_count"] += 1
		row["confirmed_count"] += 1 if event.confirmed_by_vlm else 0
	return counts


def _build_lesson_overview(session, summary):
	return (
		f"本课次共记录 {summary.event_count} 个待复核行为事件，"
		f"有效分析时长 {summary.valid_analysis_seconds} 秒。"
		"结果用于课后教学复盘，不作为学生纪律或教师教学质量的自动结论。"
	)


def _build_lesson_finding(behavior_counts):
	if not behavior_counts:
		return "本次分析未形成可汇总的行为事件，建议结合录像质量和课堂实际情况进行判断。"
	parts = [f"{code} {item['event_count']} 次" for code, item in sorted(behavior_counts.items())]
	return "检测到的状态分布：" + "、".join(parts) + "。"


def _build_lesson_suggestion(behavior_counts):
	if not behavior_counts:
		return "建议先确认摄像画面、遮挡情况与课次素材完整性，再决定是否调整教学安排。"
	return "建议教师结合课程内容、课堂互动和代表性证据片段，形成下一节课可验证的教学调整措施。"


def finalize_lesson_analysis(db, session_id):
	"""以当前课次的已持久化事件生成课后汇总和报告草稿。

	该方法只汇总已写入数据库的证据；后续离线 Worker 重跑模型时可再次调用并生成新的运行版本。
	"""
	session = db.query(MonitorSession).filter(MonitorSession.id == session_id).first()
	if not session:
		raise ValueError("课堂课次不存在")

	max_run_no = db.query(func.max(LessonAnalysisRun.run_no)).filter(LessonAnalysisRun.session_id == session.id).scalar() or 0
	db.query(LessonAnalysisRun).filter(LessonAnalysisRun.session_id == session.id, LessonAnalysisRun.is_current == 1).update({ "is_current": 0 })
	run = LessonAnalysisRun(
		session_id = session.id,
		run_no = int(max_run_no) + 1,
		run_status = "RUNNING",
		is_current = 1,
		model_name = "yolo-sahi-vlm",
		rule_version = "post-class-v1",
		config_json = {
			"detect": session.detect_config_json or {},
			"vlm": session.vlm_config_json or {},
			"rule": session.rule_config_json or {},
		},
		started_at = datetime.utcnow(),
	)
	db.add(run)
	db.flush()

	events = db.query(MonitorBehaviorEvent).filter(MonitorBehaviorEvent.session_id == session.id).order_by(MonitorBehaviorEvent.event_time.asc()).all()
	for event in events:
		event.analysis_run_id = run.id

	planned_duration = _duration_seconds(session.planned_started_at, session.planned_ended_at)
	actual_duration = _duration_seconds(session.started_at, session.ended_at)
	valid_duration = actual_duration or planned_duration
	behavior_counts = _serialize_behavior_counts(events)
	summary = LessonAnalysisSummary(
		analysis_run_id = run.id,
		planned_duration_seconds = planned_duration,
		valid_analysis_seconds = valid_duration,
		# 当前实时链路只保存最后一帧人数，不能伪装成全课平均人数。
		avg_detected_seat_count = None,
		event_count = len(events),
		confirmed_event_count = sum(1 for event in events if event.confirmed_by_vlm),
		# 现有实时链路未保存全帧覆盖率，必须如实标注为受限数据。
		data_quality_level = "LIMITED",
		quality_remark = "当前汇总由已持久化事件生成，尚未记录完整的视频帧覆盖率。",
	)
	db.add(summary)
	db.flush()
	for behavior_code, item in behavior_counts.items():
		db.add(
			LessonBehaviorStat(
				summary_id = summary.id,
				behavior_code = behavior_code,
				segment_count = item["event_count"],
				event_count = item["event_count"],
				vlm_confirmed_count = item["confirmed_count"],
			)
		)

	max_report_version = db.query(func.max(TeachingAnalysisReport.report_version)).filter(
		TeachingAnalysisReport.session_id == session.id,
		TeachingAnalysisReport.report_scope == "LESSON",
	).scalar() or 0
	report = TeachingAnalysisReport(
		report_no = _new_no("LR"),
		report_title = f"{session.class_name} {session.lesson_title or '课堂'}课后分析报告",
		report_scope = "LESSON",
		session_id = session.id,
		teaching_course_id = session.teaching_course_id,
		report_version = int(max_report_version) + 1,
		overview_text = _build_lesson_overview(session, summary),
		finding_text = _build_lesson_finding(behavior_counts),
		suggestion_text = _build_lesson_suggestion(behavior_counts),
		data_snapshot_json = {
			"summary_id": summary.id,
			"event_count": summary.event_count,
			"confirmed_event_count": summary.confirmed_event_count,
			"valid_analysis_seconds": summary.valid_analysis_seconds,
			"data_quality_level": summary.data_quality_level,
		},
	)
	db.add(report)
	db.flush()

	if session.teaching_course_id:
		entry = (
			db.query(CourseAnalysisEntry)
			.filter(CourseAnalysisEntry.teaching_course_id == session.teaching_course_id, CourseAnalysisEntry.session_id == session.id)
			.first()
		)
		if not entry:
			lesson_index = db.query(func.count(CourseAnalysisEntry.id)).filter(CourseAnalysisEntry.teaching_course_id == session.teaching_course_id).scalar() or 0
			previous_entry = (
				db.query(CourseAnalysisEntry)
				.filter(CourseAnalysisEntry.teaching_course_id == session.teaching_course_id)
				.order_by(CourseAnalysisEntry.lesson_date.desc(), CourseAnalysisEntry.lesson_index.desc())
				.first()
			)
			entry = CourseAnalysisEntry(
				teaching_course_id = session.teaching_course_id,
				session_id = session.id,
				analysis_run_id = run.id,
				summary_id = summary.id,
				report_id = report.id,
				lesson_index = int(lesson_index) + 1,
				lesson_date = (session.started_at or datetime.utcnow()).date(),
				lesson_title = session.lesson_title,
				comparison_base_entry_id = previous_entry.id if previous_entry else None,
				is_baseline = 1 if previous_entry is None else 0,
			)
			db.add(entry)
		else:
			entry.analysis_run_id = run.id
			entry.summary_id = summary.id
			entry.report_id = report.id

		if entry.comparison_base_entry_id:
			base = db.query(CourseAnalysisEntry).filter(CourseAnalysisEntry.id == entry.comparison_base_entry_id).first()
			if base:
				base_summary = db.query(LessonAnalysisSummary).filter(LessonAnalysisSummary.id == base.summary_id).first()
				if base_summary:
					delta = summary.event_count - base_summary.event_count
					entry.system_change_summary = f"相较基准课，待复核事件数变化 {delta:+d}。该变化仅反映分析数据，不构成教学效果因果结论。"

	run.run_status = "COMPLETED"
	run.finished_at = datetime.utcnow()
	session.analysis_status = "COMPLETED"
	session.analysis_completed_at = run.finished_at
	if session.teaching_course_id:
		refresh_course_aggregate(db, session.teaching_course_id, "TERM")
	return run, summary, report


def refresh_course_aggregate(db, teaching_course_id, scope_type = "TERM", start_date = None, end_date = None):
	"""按当前完成的分析版本重建一份课程周期汇总。"""
	course = db.query(TeachingCourse).filter(TeachingCourse.id == teaching_course_id).first()
	if not course:
		raise ValueError("教学课程不存在")
	if scope_type not in { "WEEK", "MONTH", "TERM", "CUSTOM" }:
		raise ValueError("汇总范围无效")
	start_date, end_date = _resolve_aggregate_period(db, course, scope_type, start_date, end_date)

	rows = (
		db.query(MonitorSession, LessonAnalysisRun, LessonAnalysisSummary)
		.join(LessonAnalysisRun, LessonAnalysisRun.session_id == MonitorSession.id)
		.join(LessonAnalysisSummary, LessonAnalysisSummary.analysis_run_id == LessonAnalysisRun.id)
		.filter(
			MonitorSession.teaching_course_id == teaching_course_id,
			LessonAnalysisRun.is_current == 1,
			LessonAnalysisRun.run_status == "COMPLETED",
			MonitorSession.started_at >= datetime.combine(start_date, time.min),
			MonitorSession.started_at < datetime.combine(end_date, time.min),
		)
		.all()
	)
	aggregate = (
		db.query(CourseAnalysisAggregate)
		.filter(
			CourseAnalysisAggregate.teaching_course_id == teaching_course_id,
			CourseAnalysisAggregate.scope_type == scope_type,
			CourseAnalysisAggregate.period_start_date == start_date,
			CourseAnalysisAggregate.period_end_date == end_date,
			CourseAnalysisAggregate.calculation_version == 1,
		)
		.first()
	)
	if not aggregate:
		aggregate = CourseAnalysisAggregate(
			aggregate_no = _new_no("CA"),
			teaching_course_id = teaching_course_id,
			scope_type = scope_type,
			period_start_date = start_date,
			period_end_date = end_date,
		)
		db.add(aggregate)
		db.flush()

	db.query(CourseAggregateSource).filter(CourseAggregateSource.aggregate_id == aggregate.id).delete(synchronize_session = False)
	db.query(CourseBehaviorStat).filter(CourseBehaviorStat.aggregate_id == aggregate.id).delete(synchronize_session = False)
	all_sessions = db.query(func.count(MonitorSession.id)).filter(
		MonitorSession.teaching_course_id == teaching_course_id,
		MonitorSession.started_at >= datetime.combine(start_date, time.min),
		MonitorSession.started_at < datetime.combine(end_date, time.min),
	).scalar() or 0
	aggregate.source_session_count = int(all_sessions)
	aggregate.completed_session_count = len(rows)
	aggregate.valid_analysis_seconds = sum(summary.valid_analysis_seconds for _, _, summary in rows)
	aggregate.data_quality_level = "GOOD" if rows and all(summary.data_quality_level == "GOOD" for _, _, summary in rows) else "LIMITED"
	aggregate.aggregate_status = "READY" if rows else "DRAFT"
	aggregate.calculated_at = datetime.utcnow()

	behavior_totals = defaultdict(lambda: { "segment_count": 0, "event_count": 0, "duration": 0, "coverage": 0 })
	for session, run, summary in rows:
		db.add(CourseAggregateSource(aggregate_id = aggregate.id, session_id = session.id, analysis_run_id = run.id, summary_id = summary.id))
		stats = db.query(LessonBehaviorStat).filter(LessonBehaviorStat.summary_id == summary.id).all()
		for stat in stats:
			item = behavior_totals[stat.behavior_code]
			item["segment_count"] += stat.segment_count
			item["event_count"] += stat.event_count
			item["duration"] += stat.total_duration_seconds
			item["coverage"] += 1
	for behavior_code, item in behavior_totals.items():
		db.add(
			CourseBehaviorStat(
				aggregate_id = aggregate.id,
				behavior_code = behavior_code,
				segment_count = item["segment_count"],
				event_count = item["event_count"],
				total_duration_seconds = item["duration"],
				average_per_session = item["event_count"] / len(rows) if rows else 0,
				session_coverage_count = item["coverage"],
			)
		)
	return aggregate
