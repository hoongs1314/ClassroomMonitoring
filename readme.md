# 课堂异常行为智能检测系统

## 核心功能
- SAHI分片
- detect座位检测
- pose姿态检测，头肩位置判断
- VLM分析，语义化内容输出

## 核心文件
- backend/main.py
  - FastAPI 服务入口 (端口8997)
- backend/services/monitor_service.py
  - 检测链路核心：SAHI分片
  - detect座位检测
  - Pose姿态检测
  - VLM分析
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
```

## 自动化测试

后端使用 Python 标准库 `unittest`，前端使用 Node 内置测试器；在项目根目录执行：

```powershell
.\scripts\run-tests.ps1
```

如只检查后端，可执行：

```powershell
.\scripts\run-tests.ps1 -SkipFrontend
```

## Docker 启动

准备模型和视频文件：

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
```

访问：

- 前端：http://localhost:8080
- 后端：http://localhost:8997
- MySQL：localhost:3306

首次启动会自动执行 `db/001_init_mysql.sql` 初始化表结构。设置 `ADMIN_PASSWORD` 后，后端启动会创建或启用管理员账号。
