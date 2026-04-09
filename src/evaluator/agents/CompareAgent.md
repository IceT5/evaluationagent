# CompareAgent

## 概述

项目对比 Agent，负责对比两个项目的 CI/CD 架构，生成详细的对比分析报告。

## 职责

1. 加载两个项目的分析数据
2. 计算定量维度得分
3. 调用 LLM 分析架构模式差异
4. 生成对比总结和建议
5. 生成 Markdown 和 HTML 对比报告

## 输入

```python
CompareInput = {
    "project_a": str,           # 项目 A 名称
    "project_b": str,           # 项目 B 名称
    "version_a": Optional[str], # 项目 A 版本（默认最新）
    "version_b": Optional[str], # 项目 B 版本（默认最新）
    "dimensions": Optional[list[str]],  # 对比维度列表
}
```

## 支持的对比维度

| 维度 | 指标 |
|------|------|
| `complexity` | 工作流数量、Job 总数、平均 Job/工作流、依赖深度、矩阵构建使用率、条件步骤使用 |
| `best_practices` | 缓存使用率、安全扫描覆盖、Artifact 复用率、密钥管理、超时配置、失败快速停止 |
| `maintainability` | Action 复用率、自定义 Action 比例、脚本复用率、工作流调用使用、文档覆盖率、命名一致性 |

## 输出

```python
{
    "comparison_id": str,
    "project_a": str,
    "project_b": str,
    "version_a": Optional[str],
    "version_b": Optional[str],
    "semantic_diff": Optional[str],     # LLM 生成的架构差异分析
    "summary": str,                      # 对比总结
    "dimensions": list[dict],            # 维度得分
    "recommendations": list[str],         # 改进建议
    "compare_html": str,                 # HTML 报告内容
}
```

## 对比维度结果格式

```python
{
    "name": str,           # 维度名称
    "score_a": float,      # 项目 A 得分
    "score_b": float,      # 项目 B 得分
    "winner": "A|B|tie",   # 胜出方
    "metrics": [
        {
            "name": str,
            "value_a": float,
            "value_b": float,
            "unit": str,
            "higher_is_better": bool,
            "winner": "A|B|tie|N/A",
        }
    ]
}
```

## 依赖

| 依赖 | 类型 | 说明 |
|------|------|------|
| `DimensionCalculator` | 工具 | 维度计算 |
| `LLMClient` | 工具 | LLM 调用（可选） |
| `StorageManager` | 存储 | 存储管理 |

## 使用示例

```python
from evaluator.agents import CompareAgent
from evaluator.llm import LLMClient

# 方式 1：使用 LLM
llm = LLMClient(api_key="...")
agent = CompareAgent(llm=llm)

result = agent.run({
    "project_a": "cccl",
    "project_b": "TensorRT-LLM",
})

# 方式 2：纯规则分析
agent = CompareAgent()

result = agent.run({
    "project_a": "cccl",
    "project_b": "TensorRT-LLM",
    "dimensions": ["complexity", "best_practices"],
})
```

## 生成的输出文件

| 文件 | 描述 |
|------|------|
| `metadata.json` | 对比元数据 |
| `compare.md` | Markdown 对比报告 |
| `compare.html` | HTML 对比报告 |

## 报告结构

```
# CI/CD 架构对比报告

## 项目信息
## 对比总结
## 详细对比
### 架构复杂度
### 最佳实践
### 可维护性
## 改进建议
```

## LangSmith 追踪

```python
@traceable(name="CompareAgent", run_type="agent")
def run(self, input_data):
    # 内部追踪
    # ├── load_projects (Tool)
    # ├── calculate_dimensions (Tool)
    # ├── analyze_semantic_diff (LLM) - 如果配置了 LLM
    # ├── generate_summary (Tool/LLM)
    # ├── generate_recommendations (Tool/LLM)
    # └── generate_reports (Tool)
```
