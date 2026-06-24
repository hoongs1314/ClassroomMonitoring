# 课堂异常行为智能检测系统

## 核心功能
- SAHI分片
- detect座位检测
- pose姿态检测，头肩位置判断
- VLM分析，语义化内容输出

## 核心文件
- main.py
  - FastAPI 服务入口 (端口8000)
- monitor_service.py
  - 检测链路核心：SAHI分片
  - detect座位检测
  - Pose姿态检测
  - VLM分析
- pose_engine.py
  - 核心姿态分析

## 本地启动

后端：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:ALIYUN_API_KEY="你的阿里云Key"
python main.py
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
