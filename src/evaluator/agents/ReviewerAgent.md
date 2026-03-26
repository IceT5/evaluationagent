# ReviewerAgent

## 概述

报告验证 Agent，负责检视 CI/CD 报告的准确性和完整性，确保分析结果可靠。

## 职责

1. 验证 LLM 响应格式
2. 验证工作流完整性
3. 验证 Job 准确性
4. 验证触发条件正确性
5. 验证架构完整性
6. 验证统计数据一致性
7. 验证项目概述准确性

## 输入

| 参数 | 类型 | 必需 | 描述 |
|------|------|------|------|
| `llm_response` | `str` | 是 | LLM 生成的响应 |
| `ci_data` | `dict` | 是 | CI/CD 原始数据 |
| `architecture` | `dict` | 否 | 架构图 JSON |
| `overview` | `str` | 否 | 项目概述 |
| `md_report_path` | `str` | 否 | Markdown 报告路径 |
| `html_report_path` | `str` | 否 | HTML 报告路径 |

## 输出

### validate_llm_response()

```python
{
    "valid": bool,
    "issues": list[str],
    "needs_review": bool,
}
```

### validate_architecture_completeness()

```python
{
    "is_complete": bool,
    "missing_workflows": list[str],
    "trigger_types_in_ci": set[str],
    "trigger_types_in_arch": set[str],
    "missing_trigger_types": set[str],
    "layer_workflow_count": int,
    "ci_workflow_count": int,
}
```

### validate_statistics_consistency()

```python
{
    "workflow_count_match": bool,
    "trigger_distribution_match": bool,
    "layer_distribution_complete": bool,
    "issues": list[str],
}
```

### validate_overview_accuracy()

```python
{
    "is_accurate": bool,
    "workflow_count_in_overview": int,
    "actual_workflow_count": int,
    "corrected_overview": str,
}
```

### validate_final_reports()

```python
{
    "valid": bool,
    "md_issues": list[str],
    "html_issues": list[str],
}
```

## 验证类型

| 验证类型 | 方法 | 描述 |
|---------|------|------|
| LLM 响应格式 | `validate_llm_response()` | 检查必要章节存在 |
| 工作流完整性 | `validate_workflow_completeness()` | 验证所有工作流被分析 |
| Job 准确性 | `validate_job_accuracy()` | 验证 Job 数量和名称 |
| 触发条件 | `validate_trigger_correctness()` | 验证触发类型匹配 |
| 架构完整性 | `validate_architecture_completeness()` | 验证架构图包含所有工作流 |
| 统计一致性 | `validate_statistics_consistency()` | 验证统计数据准确性 |
| 概述准确性 | `validate_overview_accuracy()` | 验证概述数量准确性 |
| 最终报告 | `validate_final_reports()` | 验证 MD 和 HTML 报告 |

## 依赖

| 依赖 | 类型 | 说明 |
|------|------|------|
| `LLMClient` | 工具 | LLM 调用（用于验证） |

## 使用示例

```python
from evaluator.agents import ReviewerAgent

agent = ReviewerAgent(llm=llm_client)

# 验证 LLM 响应
result = agent.validate_llm_response(llm_response, ci_data)

# 验证架构完整性
arch_result = agent.validate_architecture_completeness(ci_data, architecture)

# 验证概述准确性
overview_result = agent.validate_overview_accuracy(overview, ci_data)

# 验证最终报告
report_result = agent.validate_final_reports(md_path, html_path, ci_data)
```

## LangSmith 追踪

```python
@traceable(name="ReviewerAgent", run_type="agent")
def run(self, state):
    # 内部追踪
    # ├── validate_workflow_completeness (Tool)
    # ├── validate_job_accuracy (Tool)
    # ├── validate_architecture_completeness (Tool)
    # ├── validate_overview_accuracy (Tool)
    # └── validate_final_reports (Tool)
```
