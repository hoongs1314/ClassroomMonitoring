# 环境安装与配置
## 安装miniconda
1. 配置miniconda虚拟环境
```shell
# 创建conda环境并指定python版本
conda create -n classroom_yolo python=3.11
# 激活指定环境（yolo26）
conda activate classroom_yolo
# 取消激活
conda deactivate
# 通过名称删除
conda remove -n classroom_yolo --all
``` 
## 安装基础依赖
```shell
pip install ultralytics opencv-python streamlit pillow
```
## 安装pytorch 
```shell
# https://pytorch.org/get-started/locally/
pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cu126
```
```shell
# 导出openvino
yolo export model=yolo26x-pose.pt format=openvino imgsz=3200 conf=0.15 half=True dynamic=False

# gpu测试
yolo pose predict model=yolo26x-pose_openvino_model source=inputs/t6.png imgsz=3200 conf=0.15 device=intel:gpu project=outputs name=test_openvino_gpu

# npu测试
yolo pose predict model=yolo26x-pose_openvino_model source=inputs/t6.png imgsz=3200 conf=0.15 device=intel:npu project=outputs name=test_openvino_npu

```
# 整体方案设计
1. 根据视频每秒抽帧
2. 使用yolo识别帧画面，定位人并分析
3. 根据人物姿态判断可疑行为
4. 保存异常截图
5. 交给多模态模型做分析并给出输出文本
6. 输出异常纪录

# 遇到问题
## 前期人物识别问题
### 同一个人识别出两个框，单纯调整iou无效
- 解决方法：预测后再使用方法计算一次后去重
### 远处人物识别不出（小目标）
- 解决方法：单独分块放大后再次识别
### 部分遮挡人物识别不出
- 解决方法：分步检测，先粗检测人框，再根据面部特征检测姿态
### 模型调用时机问题
- 解决方法：将检测异常分阶段：candidate、active、closed，只在active调用
- 事件变化再触发模型调用


# 数据集

```shell
# 数据堂—208,914框监控人体属性数据
pip install modelscope
modelscope download --dataset DatatangBeijing/208914BoundingBoxes_HumanBodyAttributesDataInSurveillanceScenes
# 数据堂—1,507人102,476张人脸多姿态&多表情数据
modelscope download --dataset DatatangBeijing/1507People102476ImagesMulti_PoseAndMultiExpressionFaceData
# 数据堂—2,937人面部遮挡多姿态人脸识别数据
modelscope download --dataset DatatangBeijing/2937PeopleWithOcclusionAndMultiposeFaceRecognitionData
# 数据堂—15人3D人体22关键点标注数据
modelscope download --dataset DatatangBeijing/15People-22LandmarksAnnotationDataof3DHumanBody
```

# 服务启动
```shell
# 后端启动
python -m uvicorn video_monitor_service:app --host 127.0.0.1 --port 8001

# 前端启动
python -m http.server 8080
```