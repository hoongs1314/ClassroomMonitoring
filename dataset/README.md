# YOLO 训练数据目录

实际图像和标注文件不纳入 Git。本目录建议按以下结构准备：

```text
dataset/
├─ images/{train,val,test}/
├─ labels/{train,val,test}/
├─ classroom_behavior.yaml
└─ README.md
```

原始课堂视频保留在项目根目录的 `inputs/`，从中抽帧、去重和筛选后再生成本目录中的训练样本。标注类别、切分原则和实际训练结果以 `../docs/experiment_record.md` 为准。
