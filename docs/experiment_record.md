# 数据集与模型训练记录

本文件是论文中数据集整理、YOLO 训练和效果评估的唯一事实来源。只有完成实际训练并保存相应日志、混淆矩阵或预测样例后，才能填写指标结论。

## 固定约定

- 数据集配置：`dataset/classroom_behavior.yaml`
- 标签格式：YOLO 检测格式 `class x_center y_center width height`
- 类别映射：`0 NORMAL`、`1 HEAD_DOWN`、`2 DESK_LYING`、`3 TURNING_HEAD`、`4 EATING`
- 划分原则：按视频、班级或时间段分组划分训练集、验证集和测试集，避免相邻视频帧同时进入不同集合。
- 运行模型：后端默认加载 `models/gmn26n-behavior.pt`。

## 训练记录模板

每次训练追加一节，未获得的数值填写“待补充”。

```text
实验编号：
日期：
数据集版本与来源：
训练/验证/测试划分：
基础模型与权重：
训练命令或关键参数：
运行环境（Python、Ultralytics、PyTorch、GPU）：
输出目录：outputs/train/
Precision / Recall / mAP50 / mAP50-95：
混淆矩阵与预测样例：
模型文件：
结论与典型误检：
```

## 系统级验证记录

除离线模型指标外，可记录模型嵌入系统后的结果，例如 YOLO 与 SAHI 的推理耗时、滑动窗口告警稳定性、VLM 复核后的典型案例。该部分不能替代测试集指标，应注明视频来源和验证条件。
