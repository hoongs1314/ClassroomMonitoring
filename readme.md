# 课堂异常行为监测系统

通过视频流实时检测学生人体框与姿态关键点，结合 VLM 多模态模型判断低头/趴桌等异常行为，前端暗色大屏实时展示。

---

## 一、项目结构

```
ClassroomMonitoring/
├── monitor_service.py          # FastAPI 服务入口 (端口8000)
├── monitor_impl.py             # 检测链路核心：SAHI+Pose+VLM
├── pose_engine.py              # YOLO Pose 姿态分类器
├── video_stream_util.py        # 视频帧读取器 (线程安全)
├── vlm_system_prompt.md        # VLM 系统提示词 (qwen-vl-max)
├── vlm_user_prompt.md          # VLM 用户提示词模板
├── readme.md                   # 本文档
│
├── inputs/video/               # 测试视频
│   ├── test.mp4                # → 1班 (1280×720, 30fps)
│   ├── v1.mp4                  # → 2班
│   ├── v2.mp4                  # → 3班
│   └── v3.mp4                  # → 4班
│
├── models/                     # YOLO 模型文件 (.gitignore)
│   ├── detect.pt               # SAHI 人体检测
│   └── yolo26s-pose.pt         # Pose 关键点检测
│
├── outputs/                    # 运行时输出 (.gitignore)
│   ├── logs/monitor.log        # 全链路日志
│   └── final/
│       ├── event_crops/        # 异常事件截图
│       ├── analysis_logs/      # VLM 响应审计
│       └── review_inputs/      # VLM 输入拼图
│
├── web/                        # Vue3 前端
│   └── src/
│       ├── App.vue             # 根 (ConfigProvider暗色主题)
│       ├── main.js             # 入口
│       ├── router/index.js     # 路由
│       ├── assets/styles/      # CSS变量 + 全局样式
│       ├── composables/
│       │   ├── useApi.js       # REST 请求封装
│       │   └── useWebSocket.js # WS 单例 + 事件缓冲
│       ├── layouts/MainLayout.vue
│       ├── components/
│       │   ├── common/AppSidebar.vue
│       │   └── monitor/
│       │       ├── VideoPlayer.vue
│       │       ├── StatsCard.vue
│       │       ├── EventList.vue
│       │       ├── EventDetailModal.vue
│       │       └── SeatMapModal.vue
│       └── views/MonitorView.vue
│
├── dev_prompt.md               # 开发命令
├── arch_prompt.md              # 架构说明
└── frontend_prompt.md          # 前端指南
```

---

## 二、启动命令

```bash
# 1. 环境
conda activate classroom_yolo
export ALIYUN_API_KEY="sk-xxx"    # VLM 调用必需

# 2. 后端 (端口 8000)
python -m uvicorn monitor_service:app --host 127.0.0.1 --port 8000

# 3. 前端
cd web && npm run dev
```

---

## 三、核心架构

### 3.1 检测链路

```
video_stream_util.MockMonitorStream (inputs/video/*.mp4 循环读帧)
       │  frame_loader_worker (0.04s间隔)
       ▼
detection_analysis_loop (0.1s/周期)
  ├── SAHI 切片检测 (detect.pt, slice=640×640)
  │     → 人体框 + IoU/距离双重匹配追踪
  ├── 每3周期: PoseEngine (yolo26s-pose.pt)
  │     → NORMAL / SUSPECTED / UNCERTAIN
  │     → 高置信直判: ratio<0.03 & kp_conf>0.55 → HEAD_DOWN (跳过VLM)
  │     → 模糊疑似: 累积2次 → 入队 VLM 复核
  └── 更新 state["seats"] / state["counts"]
       │
       ▼
VLM Worker Pool (×3 并行线程)
  ├── 裁剪拼图 (每批≤6座位, 320×240/cell)
  ├── qwen-vl-max 多模态复核
  └── 解析 JSON → HEAD_DOWN / DESK_LYING / NORMAL / UNCERTAIN / EMPTY
       │  → 更新 seat 状态 + locked_abnormal
       └  → 生成事件截图 → state["events"]
```

### 3.2 WebSocket 广播 (1s/次)

```json
{
  "is_running": true,
  "time": "14:32:06",
  "img_w": 1280, "img_h": 720,
  "current_class": "1班",
  "class_list": ["1班","2班","3班","4班"],
  "seats": [{"seat_id":102, "seat_code":"S02", "box":[x1,y1,x2,y2], "status":"NORMAL"}],
  "events": [{"id":..., "seat":"S02", "label":"疑似低头", "risk":"高", "url":"/event_crops/..."}],
  "counts": {"total":12, "focus":2, "normal":10}
}
```

### 3.3 REST API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/classes` | GET | 班级列表 + 当前班级 |
| `/api/switch_class` | POST | 切换班级 `{"class":"2班"}` |
| `/api/start` | POST | 启动监控 |
| `/api/stop` | POST | 停止监控 |
| `/api/latest_frame` | GET | 最新帧 JPEG |
| `/video_feed` | GET | MJPEG 视频流 |
| `/ws` | WebSocket | 实时状态广播 |
| `/event_crops/` | Static | 异常事件截图 |

---

## 四、异常检测判定逻辑

### 4.1 Pose 初筛 (pose_engine.py)

| 条件 | 判定 |
|------|------|
| `0.05 < ratio < 0.25` | NORMAL |
| `ratio < 0.03` 且 `kp_conf > 0.55` | 高置信 → **直接 HEAD_DOWN** |
| 其他 SUSPECTED/UNCERTAIN | 送 VLM 复核 |
| 关键点不足 (<2头 或 <2肩) | SUSPECTED |

`ratio = (肩部y均值 - 头部y均值) / 人体框高度`

### 4.2 VLM 复核 (qwen-vl-max)

| VLM 状态 | 含义 |
|----------|------|
| NORMAL | 正常坐姿 |
| HEAD_DOWN | 疑似低头 |
| DESK_LYING | 疑似趴桌 |
| UNCERTAIN | 无法判断（模糊/遮挡） |
| EMPTY | 空位 |

### 4.3 关键常量

| 常量 | 值 | 说明 |
|------|-----|------|
| SUSPECT_CONFIRM_COUNT | 2 | Pose 命中次数阈值 |
| REVIEW_COOLDOWN_SECONDS | 10 | 同座两次 VLM 最小间隔 |
| MIN_LOCK_SECONDS | 30 | 异常锁定最短保持时间 |
| RECOVER_CONFIRM_COUNT | 2 | 恢复所需连续 Normal 次数 |
| VLM_BATCH_MAX | 6 | 单批最大座位数 |
| COLD_START_CYCLES | 8 | 冷启动跳过 VLM 周期数 |
| VLM_WORKERS | 3 | 并行 VLM 线程数 |

---

## 五、前端设计

### 5.1 设计系统

| 维度 | 值 |
|------|-----|
| 主题 | Ant Design darkAlgorithm + wireframe |
| 主背景 | `#0B0F17` |
| 卡片 | `#141C2B` |
| 主色/危险/警告/成功 | `#3B82F6` / `#EF4444` / `#F59E0B` / `#22C55E` |
| 字体 | Fira Code(数字) + Fira Sans(正文) |

### 5.2 组件树

```
App.vue (ConfigProvider暗色主题)
 └─ MainLayout.vue
     ├─ AppSidebar.vue     ← 班级列表菜单 + 连接状态
     └─ MonitorView.vue    ← 主监控大屏
         ├─ 顶栏 (LOGO + 状态 + 启停按钮)
         ├─ 视频区: VideoPlayer.vue (MJPEG + 异常框叠加)
         ├─ 统计区: StatsCard.vue ×3 (学生人数/重点/普通)
         ├─ 事件区: EventList.vue (筛选+事件卡片)
         ├─ EventDetailModal.vue (详情弹窗)
         └─ SeatMapModal.vue (座位图: 实时帧+框+图例)
```

### 5.3 数据流

```
useWebSocket (模块级 shallowRef 单例)
  ├─ status → MonitorView 响应式更新
  ├─ isConnected → AppSidebar 连接指示灯
  ├─ eventLog[] → 累积缓冲区
  └─ 引用计数: 最后一个组件卸载时断开

班级切换:
  AppSidebar @select-class
    → MainLayout POST /api/switch_class
    → WebSocket 广播新班级 + 检测重启
    → MonitorView 自动更新画面
```

---

## 六、日志系统

日志文件: `outputs/logs/monitor.log`

| Logger | 模块 | 内容 |
|--------|------|------|
| `monitor` | monitor_impl | 检测周期、VLM调用、匹配统计 |
| `monitor.service` | monitor_service | API请求、WS连接、广播 |
| `monitor.pose` | pose_engine | 模型加载 |
| `monitor.video` | video_stream_util | 视频切换、帧读取 |

---

## 七、依赖

| 用途 | 库 |
|------|-----|
| 人体/姿态检测 | `ultralytics` (YOLO) |
| 小目标增强 | `sahi` (切片推理) |
| VLM 调用 | `langchain-openai` + DashScope `qwen-vl-max` |
| 后端 | `fastapi` + `uvicorn` |
| 前端 | Vue 3.5 + Ant Design Vue 4.x + Vite 8.x |
| 图像 | `opencv-python`, `numpy` |
