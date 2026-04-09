# ReporterAgent

## 概述

报告生成 Agent，负责将 Markdown 报告转换为交互式 HTML 报告。

## 职责

1. 解析 Markdown 报告内容
2. 生成交互式 HTML 页面
3. 生成统计图表（触发类型分布、阶段分布）
4. 生成可搜索的工作流详情
5. 保存报告到存储目录

## 输入

| 参数 | 类型 | 必需 | 描述 |
|------|------|------|------|
| `cicd_analysis` | `dict` | 是 | CICDAgent 分析结果 |
| `project_name` | `str` | 是 | 项目名称 |
| `project_path` | `str` | 是 | 项目路径 |
| `storage_dir` | `str` | 否 | 存储目录 |
| `storage_version_id` | `str` | 否 | 版本 ID |
| `review_result` | `dict` | 否 | 验证结果 |
| `review_issues` | `list` | 否 | 验证问题列表 |
| `corrected_report` | `str` | 否 | 修正后的报告内容 |

## 输出

```python
{
    "current_step": "reporter",
    "html_report": str,                 # HTML 报告内容
    "report_path": str,                 # HTML 报告路径
    "errors": list[str],               # 错误列表
}
```

## 生成的输出文件

| 文件 | 描述 |
|------|------|
| `report.html` | 交互式 HTML 报告 |
| `workflow_details.json` | 工作流详情 JSON |

## HTML 报告功能

| 功能 | 描述 |
|------|------|
| 侧边导航 | 可折叠的层级导航 |
| 架构图 | SVG 矢量图，支持缩放和拖拽 |
| 统计图表 | 触发类型饼图、阶段分布柱状图 |
| 工作流搜索 | 全文搜索工作流和脚本 |
| 工作流详情 | 点击节点查看工作流详细信息 |
| 代码高亮 | YAML、Python 代码高亮 |
| 响应式布局 | 适配不同屏幕尺寸 |

## 报告结构

```html
<!-- 项目概述 -->
<!-- 统计概览 -->
<!-- CI/CD 整体架构图 -->
<!-- 阶段一：触发入口 -->
<!-- 阶段二：XXX -->
...
<!-- 脚本目录索引 -->
<!-- 关键发现和建议 -->
<!-- 附录 -->
```

## 使用示例

```python
from evaluator.agents import ReporterAgent

agent = ReporterAgent()

state = {
    "cicd_analysis": cicd_result["cicd_analysis"],
    "project_name": "my-project",
    "project_path": "/path/to/project",
    "storage_dir": "./data/projects/my-project/v1_xxx",
    "storage_version_id": "v1_xxx",
}

result = agent.run(state)
print(f"HTML 报告: {result['report_path']}")
```

## 依赖

| 依赖 | 类型 | 说明 |
|------|------|------|
| `StorageManager` | 存储 | 存储管理 |

## LangSmith 追踪

```python
@traceable(name="ReporterAgent", run_type="agent")
def run(self, state):
    # 内部追踪
    # ├── parse_markdown (Tool)
    # ├── generate_statistics (Tool)
    # ├── generate_html (Tool)
    # └── save_report (Tool)
```
