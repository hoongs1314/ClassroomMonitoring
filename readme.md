# 环境安装与配置
## 安装miniconda
1. 配置miniconda虚拟环境
```shell
# 创建conda环境并指定python版本
conda create classroom_yolo python=3.11
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

# 整体方案设计
1. 根据视频每秒抽帧
2. 使用yolo识别帧画面，定位人并分析
3. 根据人物姿态判断可疑行为
4. 保存异常截图
5. 交给多模态模型做分析并给出输出文本
6. 输出异常纪录