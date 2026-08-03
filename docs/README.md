# 项目文档索引

本目录用于存放论文和答辩可复用的系统设计材料。

## 图表工具选型

本项目图表采用 Mermaid 编写，原因如下：

- Mermaid 是 GitHub 高 star 的 diagrams-as-code 工具，适合把流程图、结构图和 ER 图直接放入 Markdown 文档维护。
- GitHub Markdown 支持 Mermaid 渲染，文档在仓库中即可预览，便于答辩材料后续导出图片。
- 相比 draw.io 二进制/压缩图源，Mermaid 文本更利于版本控制和代码审阅。

备选工具：

- PlantUML：适合 UML 建模，但在 GitHub Markdown 中通常需要额外渲染服务。
- draw.io / diagrams.net：适合手工绘图，但图源不如 Mermaid 文本便于 diff。

## 文档清单

- `system_architecture.md`：系统架构图和实时监控处理链路。
- `database_er.md`：数据库 ER 图和表关系说明。

