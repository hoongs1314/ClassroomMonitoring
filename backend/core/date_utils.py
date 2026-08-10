from datetime import date, datetime, time, timedelta


def parse_date_range(start_value = None, end_value = None):
	"""解析历史查询日期，结束日期按次日零点构造左闭右开区间。"""
	try:
		start_date = date.fromisoformat(start_value) if start_value else None
		end_date = date.fromisoformat(end_value) if end_value else None
	except ValueError as exc:
		raise ValueError("日期格式必须为 YYYY-MM-DD") from exc

	if start_date and end_date and end_date < start_date:
		raise ValueError("结束日期不能早于开始日期")

	start_at = datetime.combine(start_date, time.min) if start_date else None
	end_at = datetime.combine(end_date + timedelta(days = 1), time.min) if end_date else None
	return start_at, end_at
