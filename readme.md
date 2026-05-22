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