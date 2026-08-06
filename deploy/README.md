# Docker 生产部署

本目录提供面向单机或内网服务器的部署配置。生产 Compose 仅暴露前端端口；Nginx 将 `/api`、`/ws`、`/video_feed` 与 `/event_crops` 转发给后端，MySQL 和后端不对宿主机直接开放端口。

## 部署前准备

1. 安装 Docker Desktop 或 Docker Engine，并确认 `docker compose version` 可运行。
2. 准备运行资产：
   - `models/gmn26n-behavior.pt`
   - `inputs/test.mp4`、`inputs/v1.mp4`、`inputs/v2.mp4`、`inputs/v3.mp4`
3. 复制环境变量模板：

   ```powershell
   Copy-Item deploy/.env.production.example deploy/.env.production
   ```

4. 编辑 `deploy/.env.production`，为 `MYSQL_ROOT_PASSWORD`、`MYSQL_PASSWORD`、`JWT_SECRET_KEY` 和 `ADMIN_PASSWORD` 设置非空强随机值。可用以下命令生成 JWT 密钥：

   ```powershell
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

`deploy/.env.production` 含密钥，不应提交到 Git。

## 启动与验证

在项目根目录执行：

```powershell
docker compose --env-file deploy/.env.production -f docker-compose.production.yml config --quiet
docker compose --env-file deploy/.env.production -f docker-compose.production.yml up -d --build
docker compose --env-file deploy/.env.production -f docker-compose.production.yml ps
```

浏览器访问 `http://服务器地址:FRONTEND_PORT`。默认端口为 `8080`。

查看日志：

```powershell
docker compose --env-file deploy/.env.production -f docker-compose.production.yml logs -f backend
```

停止服务但保留数据库卷：

```powershell
docker compose --env-file deploy/.env.production -f docker-compose.production.yml down
```

## 运行边界

- `.dockerignore` 不会把模型和视频打进镜像；它们通过上述绑定挂载提供给后端。
- 初始化 SQL 只会在 MySQL 数据卷首次创建时执行。已有数据卷不会自动重放初始化脚本。
- 后端会把异常截图写入 `OUTPUTS_DIR`；该目录需要具备写入权限并按学校隐私要求设置保留周期。
- 前端在生产环境默认使用同源 Nginx 反向代理，无需将浏览器 API 地址固定为 `localhost:8997`。
