# CICDAgent

## 概述

CI/CD 架构分析 Agent，负责分析项目的 GitHub Actions 工作流架构，生成详细的 Markdown 分析报告。

## 职责

1. 提取 CI/CD 数据（工作流、Job、触发条件等）
2. 调用 LLM 生成架构分析报告
3. 生成架构图 JSON 数据
4. 支持大项目分割并发分析
5. 自动验证和补充遗漏的工作流
6. 验证报告准确性

## 输入

| 参数 | 类型 | 必需 | 描述 |
|------|------|------|------|
| `project_path` | `str` | 是 | 项目根目录路径 |
| `project_name` | `str` | 否 | 项目名称（默认从路径提取） |
| `storage_dir` | `str` | 否 | 存储目录路径 |
| `llm_config` | `dict` | 否 | LLM 配置 |
| `cicd_retry_mode` | `str` | 否 | 重试模式（retry/supplement） |
| `cicd_retry_issues` | `list` | 否 | 需要重试的问题列表 |
| `cicd_existing_report` | `str` | 否 | 已有的报告内容 |

## 输出

```python
{
    "current_step": "cicd",
    "cicd_analysis": {
        "status": "success|failed",
        "workflows_count": int,
        "actions_count": int,
        "ci_data_path": str,
        "report_path": str,
        "architecture_json_path": str,
        "analysis_summary_path": str,
        "error": Optional[str],
    },
    "errors": list[str],
}
```

## 依赖

| 依赖 | 类型 | 说明 |
|------|------|------|
| `ReviewerAgent` | Agent | 验证 LLM 响应和报告质量 |
| `CIAnalyzer` | Skill | CI/CD 数据提取和报告生成 |
| `LLMClient` | 工具 | LLM 调用 |

## 配置

| 配置项 | 默认值 | 描述 |
|--------|--------|------|
| `MAX_WORKFLOWS_SINGLE_PROMPT` | 10 | 单次调用的最大工作流数 |
| `MAX_WORKFLOWS_PER_BATCH` | 10 | 每批次最大工作流数 |
| `MAX_CONCURRENT_LLM_CALLS` | 2 | 最大并发 LLM 调用数 |

## 处理策略

| 工作流数量 | 策略 | 说明 |
|-----------|------|------|
| ≤10 | 单次调用 | 一次 LLM 调用完成分析 |
| 11-30 | 分割并发 | 分割 Prompt + 并发调用 + 合并结果 |
| >30 | 大分割并发 | 更小的批次 + 并发处理 |

## 生成的输出文件

| 文件 | 描述 |
|------|------|
| `ci_data.json` | 提取的 CI/CD 原始数据 |
| `CI_ARCHITECTURE.md` | LLM 生成的 Markdown 报告 |
| `architecture.json` | 架构图 JSON 数据 |
| `analysis_summary.json` | 分析摘要 JSON |

## 报告结构

```
## 项目概述
## CI/CD 整体架构图
## 阶段一：触发入口
## 阶段二：XXX
...
## 关键发现和建议
## 附录
<!-- ARCHITECTURE_JSON ... -->
```

## 使用示例

```python
from evaluator.agents import CICDAgent
from evaluator.llm import LLMClient

llm = LLMClient(api_key="...")
agent = CICDAgent(llm=llm)

state = {
    "project_path": "/path/to/project",
    "project_name": "my-project",
    "storage_dir": "./data/projects/my-project/v1_xxx",
}

result = agent.run(state)
```

## LangSmith 追踪

```python
@traceable(name="CICDAgent", run_type="agent")
def run(self, state):
    # 内部追踪
    # ├── extract_ci_data (Tool)
    # ├── generate_prompt (Tool)
    # ├── chat (LLM)
    # ├── validate_response (ReviewerAgent)
    # └── generate_report (Tool)
```
