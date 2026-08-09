# 项目文档索引

本目录用于存放论文、答辩和可复用的系统设计材料。

## 图表工具选型

本项目可使用 Mermaid 维护 Markdown 草图；论文和答辩的正式图件统一保留图源与导出文件。

- Mermaid 适合把流程图、结构图和 ER 图直接放入 Markdown 文档维护。
- `diagrams/source/` 保存 SVG 等图源，`diagrams/export/` 保存可插入论文和答辩的 PNG 图件。

备选工具：

- PlantUML：适合 UML 建模，但在 GitHub Markdown 中通常需要额外渲染服务。
- draw.io / diagrams.net：适合手工绘图，但图源不如 Mermaid 文本便于 diff。

## 文档清单

- `system_architecture.md`：课后教学分析架构、课表到课程报告的数据链路、权限边界与验证限制。
- `database_er.md`：教学课程、固定课表、摄像头绑定、课次分析和课程复盘的 ER 图与约束说明。
- `thesis_classroom_monitoring.md`：毕业设计论文源稿。
- `experiment_record.md`：数据集、训练与评估的真实记录。
- `system_review_2026-08-09.md`：当前实现的整体复核结论、自动化测试证据与后续修复项。
- `defense/`：答辩 PPTX、PDF 与使用说明。
