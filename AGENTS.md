# Eval-Agent Agents

CI/CD 架构评估工具的 Agent 系统文档。

## Agent 列表

### 核心 Agent

| Agent | 文件 | 状态 | 职责 |
|-------|------|------|------|
| InputAgent | `input_agent.py` | ✅ 完成 | 解析用户输入 (URL/路径) |
| LoaderAgent | `loader_agent.py` | ✅ 完成 | 加载/克隆项目 |
| IntentParserAgent | `intent_parser_agent.py` | ✅ 完成 | 意图解析 (自然语言) |
| CICDAgent | `cicd_agent.py` | ✅ 完成 | CI/CD 架构分析（子Agent架构） |
| ReviewerAgent | `reviewer_agent.py` | ✅ 完成 | 报告验证与准确性检查 |
| ReporterAgent | `reporter_agent.py` | ✅ 完成 | HTML 报告生成 |
| CompareAgent | `compare_agent.py` | ✅ 完成 | 项目对比分析 |

### 基础设施

| 组件 | 文件 | 状态 | 职责 |
|------|------|------|------|
| InterruptController | `core/interrupt.py` | ✅ 完成 | 全局中断控制 |
| BackgroundTasks | `core/background.py` | ✅ 完成 | 后台任务管理 |

### 编排 Agent

| Agent | 文件 | 状态 | 职责 |
|-------|------|------|------|
| OrchestratorAgent | `orchestrator_agent.py` | ✅ 完成 | 动态规划执行流程 + 智能重试 |
| IntelligencePipeline | `intelligence_pipeline.py` | ✅ 完成 | 智能分析流水线编排 |
| CICDOrchestrator | `cicd/orchestrator.py` | ✅ 完成 | CI/CD 分析编排器 |

### 智能 Agent

| Agent | 文件 | 状态 | 职责 |
|-------|------|------|------|
| ToolSelectionAgent | `tool_selection_agent.py` | ✅ 完成 | 智能选择工具组合 |
| StorageAgent | `storage_agent.py` | ✅ 已集成 | 智能存储 + 相似项目检索 |
| ReflectionAgent | `reflection_agent.py` | ✅ 已集成 | 执行历史反思 + 性能分析 |
| RecommendationAgent | `recommendation_agent.py` | ✅ 已集成 | 最佳实践推荐 + 改进建议 |

### CI/CD 子 Agent

| Agent | 文件 | 状态 | 职责 |
|-------|------|------|------|
| DataExtractionAgent | `cicd/data_extraction_agent.py` | ✅ 完成 | 提取 CI/CD 配置数据 |
| AnalysisPlanningAgent | `cicd/analysis_planning_agent.py` | ✅ 完成 | 决定分析策略 (单次/并发) |
| LLMInvocationAgent | `cicd/llm_invocation_agent.py` | ✅ 完成 | 执行 LLM 调用 |
| ResultMergingAgent | `cicd/result_merging_agent.py` | ✅ 完成 | 合并多个 LLM 响应 |
| QualityCheckAgent | `cicd/quality_check_agent.py` | ✅ 完成 | 验证报告质量 |
| RetryHandlingAgent | `cicd/retry_handling_agent.py` | ✅ 完成 | 重试/补充模式处理 |
| ArchitectureValidationAgent | `cicd/architecture_validation_agent.py` | ✅ 完成 | 架构验证与补充 |
| StageOrganizationAgent | `cicd/stage_organization_agent.py` | ✅ 完成 | 阶段组织 |
| ReportGenerationAgent | `cicd/report_generation_agent.py` | ✅ 完成 | 报告生成 |
| SummaryGenerationAgent | `cicd/summary_generation_agent.py` | ✅ 完成 | 摘要生成 |

### 处理 Agent

| Agent | 文件 | 状态 | 职责 |
|-------|------|------|------|
| ListHandlerAgent | `handlers/list_handler.py` | ✅ 完成 | 处理 list 命令 |
| InfoHandlerAgent | `handlers/info_handler.py` | ✅ 完成 | 处理 info 命令 |
| DeleteHandlerAgent | `handlers/delete_handler.py` | ✅ 完成 | 处理 delete 命令 |
| HelpHandlerAgent | `handlers/help_handler.py` | ✅ 完成 | 处理 help 命令 |

### 验证 Agent

| Agent | 文件 | 状态 | 职责 |
|-------|------|------|------|
| ErrorHandlerAgent | `error_handler_agent.py` | ✅ 完成 | 统一错误处理 |
| StateValidationAgent | `state_validation_agent.py` | ✅ 完成 | 状态完整性验证 |

## BaseAgent 基类

所有Agent必须继承BaseAgent：

```python
from evaluator.agents.base_agent import BaseAgent, AgentMeta

class MyAgent(BaseAgent):
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="MyAgent",
            description="我的Agent描述",
            category="analysis",
            inputs=["input_field"],
            outputs=["output_field"],
            dependencies=["OtherAgent"],
        )
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        value = state["input_field"]
        result = self._process(value)
        return {**state, "output_field": result}
```

## 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                         OrchestratorAgent                          │
│                   (动态规划 + 智能重试决策)                         │
│         plan() │ should_retry() │ evaluate_quality()            │
│                   (委托给ToolSelectionAgent)                       │
└─────────────────────────────┬───────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────┐
│                      ToolSelectionAgent                            │
│                   (智能选择工具组合)                               │
│              select_tools() │ execute_with_tools()               │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│  StorageAgent  │     │ReflectionAgent│     │RecommendationAgent│
│ find_similar() │     │   reflect()   │     │ recommend()    │
│suggest_compare │     │record()       │     │ get_quick_wins │
└───────────────┘     └───────────────┘     └───────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │          异步执行      │        后台保存       │
        ▼                     ▼                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                        LangGraph                                  │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                    IntentParserAgent                         │  │
│  └─────────────────────────┬───────────────────────────────────┘  │
│                            │                                       │
│  ┌─────────────────────────▼───────────────────────────────────┐  │
│  │                      InputAgent                              │  │
│  └─────────────────────────┬───────────────────────────────────┘  │
│                            │                                       │
│  ┌─────────────────────────▼───────────────────────────────────┐  │
│  │                     LoaderAgent                               │  │
│  └─────────────────────────┬───────────────────────────────────┘  │
│                            │                                       │
│  ┌─────────────────────────▼───────────────────────────────────┐  │
│  │                     CICDAgent                                  │  │
│  │              (内部由CICDOrchestrator编排)                     │  │
│  └─────────────────────────┬───────────────────────────────────┘  │
│                            │                                       │
│  ┌─────────────────────────▼───────────────────────────────────┐  │
│  │                    ReviewerAgent                             │  │
│  └─────────────────────────┬───────────────────────────────────┘  │
│                            │                                       │
│  ┌─────────────────────────▼───────────────────────────────────┐  │
│  │                    ReporterAgent                             │  │
│  │              (完成后触发异步智能Agent)                        │  │
│  └─────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### CICDOrchestrator 子Agent流程

```
extract → plan → invoke → merge → check → retry? → validate → organize → report → summary
    │        │      │      │      │         │         │        │        │
    ▼        ▼      ▼      ▼      ▼         ▼         ▼        ▼        ▼
DataEx-  Analysis LLM    Result Quality Retry    Arch     Stage    Report Sum-
traction Plan-    Invo-  Merge  Check  Handle    Valid    Organ    Gen    mary
          ning   cation                           ation            ertion Gen
```

## 执行流程

### 分析流程

```
用户输入
    │
    ├── 传统命令: /analyze path
    └── 自然语言: "帮我分析这个项目"
            │
            ▼
    IntentParserAgent (解析意图)
            │
            ▼
    OrchestratorAgent (规划执行步骤)
            │
            ▼
    InputAgent (解析输入)
            │
            ▼
    LoaderAgent (加载项目)
            │
            ▼
    CICDAgent (CI/CD 分析)
            │
            ├── DataExtractionAgent (提取数据)
            ├── AnalysisPlanningAgent (规划策略)
            ├── LLMInvocationAgent (LLM 调用)
            ├── ResultMergingAgent (合并结果)
            ├── QualityCheckAgent (质量检查)
            ├── RetryHandlingAgent (重试处理)
            ├── ArchitectureValidationAgent (架构验证)
            ├── StageOrganizationAgent (阶段组织)
            ├── ReportGenerationAgent (报告生成)
            └── SummaryGenerationAgent (摘要生成)
            │
            ▼
    ReviewerAgent (验证报告)
            │
            ▼
    ReporterAgent (生成 HTML)
            │
            ▼
    [异步执行]
    StorageAgent → RecommendationAgent → ReflectionAgent
            │
            ▼
    insights.json (保存结果)
            │
            ▼
    用户可通过 /insights 查看智能分析结果
```

## 路由函数 (core/routes.py)

| 函数 | 说明 |
|------|------|
| `route_intent()` | 基于意图的路由 |
| `route_after_input()` | 输入后路由：loader/error_handler/skip |
| `route_after_loader()` | 加载后路由：cicd/error_handler/skip |
| `route_after_cicd()` | CI/CD 后路由：reviewer/error_handler/skip |
| `route_after_review()` | 验证后路由：reporter/cicd/error_handler |
| `should_skip_review()` | 判断是否跳过 review |
| `evaluate_quality()` | 评估结果质量 |

## CLI 命令

| 命令 | 说明 |
|------|------|
| `/analyze [type] <path>` | 分析项目的 CI/CD 架构 |
| `/compare <a> <b>` | 对比两个项目的 CI 架构 |
| `/list` | 列出已保存的项目 |
| `/show <name>` | 显示项目详情 |
| `/delete <name>` | 删除项目 |
| `/insights [name]` | 显示智能分析结果 |
| `/recommend [name]` | 显示改进建议 |
| `/similar [name]` | 显示相似项目 |
| `/help [topic]` | 显示帮助 |

## 添加新 Agent

1. 在 `src/evaluator/agents/` 创建 Agent 文件
2. 继承 `BaseAgent`
3. 实现 `describe()` 和 `run()` 方法
4. 在 `agents/__init__.py` 导出
5. 在 `core/graphs/main_graph.py` 添加节点
6. 更新本索引文档
