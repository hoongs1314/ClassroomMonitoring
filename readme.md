# 基于 YOLO 的学生课堂行为识别与课后教学分析系统

## 项目定位

系统面向教师的课后教学复盘，而非上课过程中的实时告警查看。固定摄像设备与班级按有效日期绑定；管理员维护学年、学期、教学课程和固定课表，系统据此生成待分析课次。单节课的行为事件、课后报告、课程分析串联、教学改进措施和课程阶段报告均可追溯保存。

当前短视频循环播放仅保留为管理员验证识别链路的开发演示来源，不作为真实课堂视频采集方案，也不向教师端展示为业务功能。

## 核心功能
- YOLO与SAHI分片行为检测
- 匈牙利算法座位匹配与滑动窗口告警
- VLM异常截图复核与语义说明
- 学年、学期、教学课程、固定课表、摄像设备及摄像头—班级有效期绑定管理
- 课表驱动的待分析课次、单节课后报告、课程分析串联与教学改进闭环
- 周期课程汇总、课程阶段报告及报告数据快照

## 核心文件
- backend/main.py
  - FastAPI 服务入口 (端口8997)
- backend/services/monitor_service.py
  - 管理员演示识别链路：YOLO与SAHI分片、座位匹配、连续状态判定、事件持久化和VLM复核
  - 演示结束后生成单节课后分析汇总；若命中已配置课表，则自动归入对应教学课程
- backend/services/schedule_service.py
  - 按固定课表创建 `SCHEDULED/PENDING` 课次，保留摄像头—班级绑定快照
- backend/services/teaching_analysis_service.py
  - 生成单节课汇总、课程分析条目、课程周期汇总与报告草稿
- backend/core
  - 配置、数据库、鉴权依赖和启动引导
- backend/domain
  - SQLAlchemy 数据模型
- backend/routers
  - 认证、教师端历史记录和复盘接口
- backend/prompts
  - VLM 分析提示词

## 科研资料与运行资产

- `docs/thesis_classroom_monitoring.md`：论文源稿；`docs/diagrams/` 保存论文图源和导出图；`docs/defense/` 用于存放答辩材料。
- `docs/experiment_record.md`：记录实际使用的数据集、训练配置、权重和评估结果，未验证指标不得填写为结论。
- `dataset/`：YOLO 训练数据，包含 `images/`、`labels/` 和 `classroom_behavior.yaml`；实际样本不纳入 Git。
- `models/`：本地模型权重；运行时默认加载 `models/gmn26n-behavior.pt`。
- `inputs/`：本地试运行视频；`outputs/`：事件截图和训练/评估输出。两者均不纳入 Git。

## 本地启动

后端：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
$env:ALIYUN_API_KEY="你的阿里云Key"
python backend/main.py
```

前端：

```powershell
cd web
npm install
npm run dev
```

数据库：

```powershell
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS classroom_monitoring DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;"
mysql -u root -p classroom_monitoring < db/001_init_mysql.sql
mysql -u root -p classroom_monitoring < db/002_teaching_analysis.sql
mysql -u root -p classroom_monitoring < db/006_runtime_integrity.sql
```

已有数据库升级时，执行第二、三条增量脚本。脚本只新增表、索引和约束，不删除既有课堂记录；执行前仍应完成数据库备份。`006_runtime_integrity.sql` 若发现历史重复课表课次会停止执行并保留原表，需先人工核对。Docker 在新建数据卷时会按顺序自动执行 `001_init_mysql.sql`、`002_teaching_analysis.sql` 与 `006_runtime_integrity.sql`；已有数据卷仍需在容器内或通过本机 MySQL 客户端手动执行增量脚本。

如需导入图片对应的“高三示范班”周课表，可额外执行：

```powershell
mysql -u root -p classroom_monitoring < db/003_seed_grade3_demo_timetable.sql
```

该种子数据包含 2026–2027 学年第一学期、七门学科、示例教师、七个教学课程和 44 个正式学科课时；不会创建摄像设备或真实教师账号，可在管理页按实际信息替换。

如需重置为教师端“我的班级”功能的最小测试数据，可执行：

```powershell
mysql -u root -p classroom_monitoring < db/004_seed_teacher_class_test_data.sql
```

该脚本保留既有监控历史，将旧示例课程归档，并创建 `teacher1`（高三1班、高三2班数学）和 `tearch2`（高三2班英语）；两位教师的测试密码均为 `Teacher123!`。`admin` 账号及其密码保持当前部署配置。

如需清空教学配置与课程分析数据，并生成暂不分配教师的完整高三课表，可执行：

```powershell
mysql -u root -p classroom_monitoring < db/005_reset_unassigned_grade3_timetable.sql
```

该脚本保留账号、教师档案和监控历史（课次、事件、截图、复核），清理旧课程、课表、学年学期、教师班级授权、摄像头班级绑定及课程分析记录；随后生成高三1班、高三2班各周一至周五七节课的完整课表。课程教师为空，后续可在“教学课程与课表”中再分配。

课表调度器会将已结束但尚未接入视频分析的课次保留为待分析状态，不生成虚构报告。接入真实摄像机录像或离线视频处理器后，应在处理完成时写入行为事件，再调用课后汇总服务生成报告。

## 自动化测试

后端使用 Python 标准库 `unittest`，前端使用 Node 内置测试器；在项目根目录执行：

```powershell
.\scripts\run-tests.ps1
```

如只检查后端，可执行：

```powershell
.\scripts\run-tests.ps1 -SkipFrontend
```

教师端“我的班级”按班级聚合展示，不按科目拆分；每次加载会按当前本地时间和固定周课表匹配“当前课程”。进入班级后仍以当前/默认教学课程作为课次档案权限边界，支持按日期范围筛选和服务端分页，只返回该课程生成的课次、警告、提示和事件汇总；复盘页面可进一步查看异常事件关联截图帧。管理员保留跨班级的全局课次档案入口。

## Docker 启动

准备模型和开发演示视频（真实部署应改为受控的摄像机录像接入）：

- `models/gmn26n-behavior.pt`
- `inputs/test.mp4`
- `inputs/v1.mp4`
- `inputs/v2.mp4`
- `inputs/v3.mp4`

启动：

```powershell
docker compose up -d --build
```

## 生产 Docker 部署

面向内网服务器的最小暴露端口部署，请按 [deploy/README.md](deploy/README.md) 准备密钥和运行资产后，使用 `docker-compose.production.yml` 启动。

首次需要登录时，建议先在 `.env` 或当前终端设置：

```powershell
$env:ADMIN_USERNAME="admin"
$env:ADMIN_PASSWORD="请替换成强密码"
$env:JWT_SECRET_KEY="请替换成随机长密钥"
$env:ALIYUN_API_KEY="你的阿里云Key"
$env:VLM_WORKER_COUNT="2"
```

访问：

- 前端：http://localhost:8080
- 后端：http://localhost:8997
- MySQL：localhost:3306

浏览器媒体请求通过 HttpOnly Cookie 鉴权，不再将访问令牌附在视频流、截图或 WebSocket URL 中。HTTPS 部署请设置 `MEDIA_COOKIE_SECURE=true`；开发跨端口访问默认只允许 `localhost` 与 `127.0.0.1` 的 8998、8080 来源，如需额外前端域名请通过 `CORS_ORIGINS` 显式配置。

首次启动会自动执行 `db/001_init_mysql.sql` 与 `db/002_teaching_analysis.sql` 初始化表结构。设置 `ADMIN_PASSWORD` 后，后端仅在管理员账号不存在时创建该账号，既有账号的密码和启用状态不会在重启时被覆盖。
