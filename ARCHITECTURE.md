# Eval-Agent 架构设计文档

> 版本: 2.3.0  
> 最后更新: 2026-04-05  
> 状态: 设计确认

---

## 一、设计原则

### 1.1 核心原则

| 原则 | 说明 |
|------|------|
| **单一入口** | 所有执行必须通过 LangGraph，无例外 |
| **统一编排** | LangGraph 是唯一的编排引擎，禁止直接调用 Agent |
| **意图先行** | IntentParserAgent 是所有工作流的第一个节点（CLI命令除外） |
| **智能路由** | OrchestratorAgent 负责工作流规划和动态决策 |
| **状态驱动** | 所有数据通过 EvaluatorState 传递，禁止全局变量 |
| **Agent基类** | 所有Agent必须继承 BaseAgent |
| **异步增强** | 智能Agent异步执行，不阻塞主流程 |
| **CLI即入口** | CLI通过LangGraph调用所有功能，无直接Agent调用 |

### 1.2 禁止事项

| 禁止 | 原因 |
|------|------|
| ❌ 直接调用 Agent | 破坏统一编排，导致状态不一致 |
| ❌ 绕过 LangGraph | 破坏单一入口原则 |
| ❌ 在 CLI 层处理业务逻辑 | CLI 只负责输入/输出，不处理业务 |
| ❌ 使用全局状态 | 导致状态难以追踪和调试 |
| ❌ 创建新的图定义文件 | 只允许 `core/graphs/` 下的图定义 |
| ❌ Agent不继承BaseAgent | 破坏架构一致性 |

### 1.3 Agent分类

| 类别 | 说明 | 示例 |
|------|------|------|
| **入口Agent** | 解析用户意图 | IntentParserAgent |
| **编排Agent** | 规划工作流、动态决策 | OrchestratorAgent, IntelligencePipeline |
| **功能Agent** | 实现具体业务逻辑 | InputAgent, LoaderAgent, CICDAgent |
| **智能Agent** | 异步执行，增强功能 | StorageAgent, RecommendationAgent, ReflectionAgent |
| **处理Agent** | 处理简单命令 | ListHandlerAgent, InfoHandlerAgent |
| **验证Agent** | 错误处理、状态验证 | ErrorHandlerAgent, StateValidationAgent |
| **CICD子Agent** | CI/CD分析子任务 | DataExtractionAgent, LLMInvocationAgent等 |

---

## 二、架构层次

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Layer 0: 用户层                                                              │
│                                                                             │
│   CLI / Python API / Web API (未来)                                         │
│                                                                             │
│   职责: 接收用户输入，调用 Layer 1，展示结果                                  │
│   禁止: 业务逻辑处理、直接调用 Agent                                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Layer 1: 编排层                                                              │
│                                                                             │
│   LangGraph (唯一编排引擎)                                                   │
│   └── core/graphs/ (唯一图定义目录)                                         │
│       ├── main_graph.py      # 主入口图                                     │
│       ├── analyze_graph.py   # 分析子图                                      │
│       └── compare_graph.py   # 对比子图                                     │
│                                                                             │
│   职责: 编排 Agent 执行顺序，管理状态流转                                     │
│   禁止: 业务逻辑实现                                                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Layer 2: Agent 层                                                            │
│                                                                             │
│   IntentParserAgent → OrchestratorAgent → 功能 Agents                       │
│                                                                             │
│   职责: 实现具体业务逻辑                                                      │
│   禁止: 跨 Agent 调用、修改全局状态                                          │
│   约束: 必须继承 BaseAgent                                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Layer 3: 基础设施层                                                          │
│                                                                             │
│   StorageManager / LLMClient / Skills / BackgroundTasks                     │
│                                                                             │
│   职责: 提供基础能力                                                          │
│   禁止: 业务逻辑                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 三、工作流设计

### 3.1 主工作流

```
用户输入
    │
    ▼
┌─────────────────┐
│ IntentParser    │  Layer 2: 解析意图
│ Agent           │  输入: user_input
│                 │  输出: intent, params
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Orchestrator    │  Layer 2: 规划工作流
│ Agent           │  输入: intent
│                 │  输出: next_step, workflow
└────────┬────────┘
         │
         ├──────────────────────────────────────┐
         │                                      │
         ▼                                      ▼
┌─────────────────┐                    ┌─────────────────┐
│ 复杂工作流       │                    │ 简单工作流       │
│ (analyze/compare)│                    │ (list/info/delete)│
│                 │                    │                 │
│ multi-step      │                    │ single-step     │
└────────┬────────┘                    └────────┬────────┘
         │                                      │
         └──────────────────┬───────────────────┘
                            │
                            ▼
                         ┌─────┐
                         │ END │
                         └─────┘
```

### 3.2 分析工作流（含智能Agent）

```
主流程（同步）:
input → loader → cicd → reviewer → reporter → END
                        ↓                    ↑
                   用户可立即查看报告       完成后触发后台任务

后台任务（异步）:
reporter完成 → storage → recommendation → reflection
                   ↓
              结果写入 insights.json

查看命令:
/insights <project>  → 显示智能分析结果
/recommend <project> → 显示改进建议
/similar <project>   → 显示相似项目
```

### 3.3 CI/CD分析子Agent流程

```
CICDOrchestrator 编排:
extract → plan → invoke → merge → check → retry? → validate → organize → report → summary

子Agent职责:
- DataExtractionAgent: 提取CI/CD配置数据
- AnalysisPlanningAgent: 决定分析策略
- LLMInvocationAgent: 执行LLM调用
- ResultMergingAgent: 合并结果
- QualityCheckAgent: 质量检查
- RetryHandlingAgent: 重试处理
- StageOrganizationAgent: 阶段组织
- ReportGenerationAgent: 报告生成
- SummaryGenerationAgent: 摘要生成
- ReportFixAgent: 修复报告问题
```

---

## 四、Agent 设计规范

### 4.1 BaseAgent 基类

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
        )
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        # 读取输入
        value = state["input_field"]
        # 处理
        result = self._process(value)
        # 返回更新 (必须包含所有原字段)
        return {**state, "output_field": result}
```

### 4.2 Agent 分类

| 类别 | Agent | 职责 |
|------|-------|------|
| **入口Agent** | IntentParserAgent | 解析用户意图 |
| **编排Agent** | OrchestratorAgent | 规划工作流、动态决策 |
| **编排Agent** | IntelligencePipeline | 智能分析流水线编排 |
| **编排Agent** | CICDOrchestrator | CI/CD分析编排 |
| **功能Agent** | InputAgent | 解析项目路径/URL |
| **功能Agent** | LoaderAgent | 加载/克隆项目 |
| **功能Agent** | CICDAgent | 分析 CI/CD 架构 |
| **功能Agent** | ReviewerAgent | 验证报告准确性 |
| **功能Agent** | ReporterAgent | 生成报告 |
| **功能Agent** | CompareAgent | 对比项目 |
| **智能Agent** | StorageAgent | 相似项目检索 |
| **智能Agent** | RecommendationAgent | 改进建议推荐 |
| **智能Agent** | ReflectionAgent | 执行历史反思 |
| **处理Agent** | ListHandlerAgent | 处理 list 命令 |
| **处理Agent** | InfoHandlerAgent | 处理 info 命令 |
| **处理Agent** | DeleteHandlerAgent | 处理 delete 命令 |
| **验证Agent** | ErrorHandlerAgent | 统一错误处理 |
| **验证Agent** | StateValidationAgent | 状态完整性验证 |
| **CICD子Agent** | DataExtractionAgent | 提取 CI/CD 数据 |
| **CICD子Agent** | AnalysisPlanningAgent | 决定分析策略 |
| **CICD子Agent** | LLMInvocationAgent | 执行 LLM 调用 |
| **CICD子Agent** | ResultMergingAgent | 合并结果 |
| **CICD子Agent** | QualityCheckAgent | 质量检查 |
| **CICD子Agent** | RetryHandlingAgent | 重试处理 |
| **CICD子Agent** | StageOrganizationAgent | 阶段组织 |
| **CICD子Agent** | ReportGenerationAgent | 报告生成 |
| **CICD子Agent** | SummaryGenerationAgent | 摘要生成 |
| **修复Agent** | ReportFixAgent | 修复报告问题 |

### 4.3 Agent详细说明

#### 入口Agent

**IntentParserAgent**
- 职责：解析用户意图，判断是命令还是自然语言
- 输入：user_input
- 输出：intent, params
- 调用关系：main_graph入口 → IntentParserAgent

**InputAgent**
- 职责：解析项目路径或URL，判断输入类型
- 输入：user_input, params
- 输出：project_name, project_path, project_url, should_download
- 调用关系：OrchestratorAgent决策后 → InputAgent

**LoaderAgent**
- 职责：下载/克隆远程项目，初始化存储目录
- 输入：project_name, project_url, project_path, should_download
- 输出：project_path, clone_status, storage_version_id, storage_dir
- 调用关系：InputAgent之后 → LoaderAgent → GitOperations/StorageManager

#### 功能Agent

**CICDAgent**
- 职责：CI/CD架构分析的主入口，内部由CICDOrchestrator编排
- 输入：project_path, storage_dir
- 输出：cicd_analysis, report_md, architecture_json, analysis_summary
- 调用关系：LoaderAgent之后 → CICDAgent → CICDOrchestrator

**ReviewerAgent**
- 职责：验证报告准确性，检查遗漏和错误
- 输入：report_md, ci_data, architecture_json
- 输出：review_result, review_issues
- 调用关系：CICDAgent之后 → ReviewerAgent

**ReporterAgent**
- 职责：生成交互式HTML报告
- 输入：report_md, architecture_json, analysis_summary
- 输出：report_html
- 调用关系：ReviewerAgent之后 → ReporterAgent

**CompareAgent**
- 职责：对比两个项目的CI/CD架构
- 输入：project_a, project_b, version_a, version_b
- 输出：comparison_result, comparison_dir
- 调用关系：Orchestrator决策后 → CompareAgent

#### 编排Agent

**OrchestratorAgent**
- 职责：规划工作流，动态决策下一步
- 输入：intent, 当前state
- 输出：orchestrator_decision (next_step, workflow)
- 调用关系：IntentParserAgent之后 → OrchestratorAgent

**CICDOrchestrator**
- 职责：编排CI/CD分析的子Agent序列
- 编排流程：extract → plan → invoke → merge → check → retry? → organize → report → summary
- 输入：project_path, storage_dir
- 输出：所有CICD子Agent的输出
- 调用关系：CICDAgent内部 → CICDOrchestrator → 各CICD子Agent

**IntelligencePipeline**
- 职责：编排智能Agent链（异步执行）
- 编排流程：StorageAgent → RecommendationAgent → ReflectionAgent
- 输入：storage_dir, project_name, ci_data
- 输出：insights.json
- 调用关系：ReporterAgent完成后（异步） → IntelligencePipeline

#### CICD子Agent

**DataExtractionAgent**
- 职责：从项目目录提取CI/CD配置数据
- 输入：project_path, storage_dir
- 输出：ci_data, ci_data_path, workflow_count
- 调用关系：CICDOrchestrator → DataExtractionAgent → CIAnalyzer

**AnalysisPlanningAgent**
- 职责：决定分析策略（单次/并发/跳过）
- 输入：ci_data, workflow_count
- 输出：strategy, prompts
- 调用关系：CICDOrchestrator → AnalysisPlanningAgent

**LLMInvocationAgent**
- 职责：执行LLM调用（单次/并发）
- 输入：prompts, strategy
- 输出：llm_responses
- 调用关系：CICDOrchestrator → LLMInvocationAgent → LLMClient

**ResultMergingAgent**
- 职责：合并多个LLM响应
- 输入：llm_responses
- 输出：merged_response
- 调用关系：CICDOrchestrator → ResultMergingAgent

**QualityCheckAgent**
- 职责：验证报告质量
- 输入：merged_response
- 输出：validation_result, retry_issues
- 调用关系：CICDOrchestrator → QualityCheckAgent

**RetryHandlingAgent**
- 职责：处理重试/补充模式
- 输入：retry_issues, retry_count
- 输出：retry_mode, 补充内容
- 调用关系：CICDOrchestrator（如需重试） → RetryHandlingAgent → LLMClient

**StageOrganizationAgent**
- 职责：组织工作流到阶段
- 输入：merged_response, ci_data
- 输出：组织后的报告内容
- 调用关系：CICDOrchestrator → StageOrganizationAgent

**ReportGenerationAgent**
- 职责：生成最终Markdown报告
- 输入：merged_response, architecture_json
- 输出：report_md, architecture_json
- 调用关系：CICDOrchestrator → ReportGenerationAgent

**SummaryGenerationAgent**
- 职责：生成分析摘要
- 输入：report_md, ci_data
- 输出：analysis_summary
- 调用关系：CICDOrchestrator → SummaryGenerationAgent

**ReportFixAgent**
- 职责：修复报告中的问题
- 输入：review_issues, report_md, ci_data
- 输出：corrected_report
- 调用关系：ReviewerAgent之后（如有问题） → ReportFixAgent → LLMClient

#### 智能Agent

**StorageAgent**
- 职责：存储分析结果，检索相似项目
- 输入：storage_dir, project_name, ci_data
- 输出：similar_projects
- 调用关系：IntelligencePipeline → StorageAgent

**RecommendationAgent**
- 职责：生成改进建议和最佳实践
- 输入：ci_data, analysis_summary
- 输出：recommendations, quick_wins
- 调用关系：IntelligencePipeline → RecommendationAgent

**ReflectionAgent**
- 职责：执行历史反思和性能分析
- 输入：project_name, analysis_summary
- 输出：reflection_result
- 调用关系：IntelligencePipeline → ReflectionAgent

#### 处理Agent

**ListHandlerAgent / InfoHandlerAgent / DeleteHandlerAgent / HelpHandlerAgent**
- 职责：处理对应的简单命令（list/info/delete/help）
- 输入：params
- 输出：对应的结果
- 调用关系：Orchestrator决策后 → 对应HandlerAgent

---

## 五、Agent调用关系

### 5.1 主工作流调用图

```
用户输入
    │
    ▼
IntentParserAgent ─────────────────┐
    │                               │
    │ intent, params                │
    ▼                               │
OrchestratorAgent                   │
    │                               │
    ├─ analyze意图                   │
    │   │                           │
    │   ▼                           │
    │  InputAgent                   │
    │   │                           │
    │   │ project_name/path/url     │
    │   ▼                           │
    │  LoaderAgent                  │
    │   │                           │
    │   │ storage_dir               │
    │   ▼                           │
    │  CICDAgent                    │
    │   │                           │
    │   │ (内部CICDOrchestrator)    │
    │   │   │                       │
    │   │   ├─ DataExtractionAgent  │
    │   │   ├─ AnalysisPlanningAgent│
    │   │   ├─ LLMInvocationAgent   │
    │   │   ├─ ResultMergingAgent   │
    │   │   ├─ QualityCheckAgent    │
    │   │   ├─ RetryHandlingAgent?  │
    │   │   ├─ StageOrganizationAgent│
    │   │   ├─ ReportGenerationAgent│
    │   │   └─ SummaryGenerationAgent│
    │   │                           │
    │   │ report_md, architecture   │
    │   ▼                           │
    │  ReviewerAgent                │
    │   │                           │
    │   │ review_result, issues     │
    │   ▼                           │
    │  ReportFixAgent? (如有问题)   │
    │   │                           │
    │   │ corrected_report          │
    │   ▼                           │
    │  ReporterAgent                │
    │   │                           │
    │   │ report_html               │
    │   ▼                           │
    │  [异步] IntelligencePipeline  │
    │   │                           │
    │   │ ├─ StorageAgent           │
    │   │ ├─ RecommendationAgent    │
    │   │ └─ ReflectionAgent        │
    │   │                           │
    │   └───────────────────────────┘
    │
    ├─ compare意图
    │   └─ CompareAgent
    │
    ├─ list/info/delete意图
    │   └─ 对应HandlerAgent
    │
    └─ help意图
        └─ HelpHandlerAgent
```

### 5.2 数据流转图

```
user_input
    │
    ▼
intent, params ───────────────────┐
    │                             │
    ▼                             │
project_name, project_path/url    │
    │                             │
    ▼                             │
storage_dir, storage_version_id   │
    │                             │
    ▼                             │
ci_data, workflow_count           │
    │                             │
    ▼                             │
prompts, strategy                 │
    │                             │
    ▼                             │
llm_responses                     │
    │                             │
    ▼                             │
merged_response                   │
    │                             │
    ▼                             │
validation_result, retry_issues   │
    │                             │
    ├─ 如需重试 ──┐               │
    │             │               │
    │             ▼               │
    │         retry_mode          │
    │             │               │
    │             └───────┐       │
    │                     │       │
    ▼                     ▼       │
report_md, architecture_json      │
    │                             │
    ▼                             │
review_result, review_issues      │
    │                             │
    ├─ 如有问题 ──┐               │
    │             │               │
    │             ▼               │
    │     corrected_report        │
    │             │               │
    │             └───────┐       │
    │                     │       │
    ▼                     ▼       │
report_html                       │
    │                             │
    ▼                             │
[异步] insights.json ─────────────┘
```

### 5.3 路由函数说明

| 路由函数 | 触发条件 | 下一步 |
|---------|---------|--------|
| route_after_input | 有errors | error_handler |
| route_after_input | should_download=True | orchestrator |
| route_after_input | 其他 | skip |
| route_after_loader | 有errors | error_handler |
| route_after_loader | 无project_path | skip |
| route_after_loader | 其他 | orchestrator |
| route_after_cicd | status=no_cicd | skip |
| route_after_cicd | status=failed且重试次数<最大值 | cicd |
| route_after_cicd | 其他 | orchestrator |
| route_after_review | review_result=issues_found | report_fix |
| route_after_review | 其他 | orchestrator |
| route_after_report_fix | fix_result=supplement | reviewer |
| route_after_report_fix | fix_result=retry | cicd |
| route_after_report_fix | 其他 | orchestrator |

---

## 六、状态设计

### 5.1 EvaluatorState定义

```python
class EvaluatorState(TypedDict, total=False):
    # ========== UI管理 ==========
    ui_manager: Optional[Any]
    
    # ========== 用户输入 ==========
    user_input: Optional[str]
    intent: Optional[str]
    params: Dict[str, Any]
    
    # ========== 项目信息 ==========
    project_name: Optional[str]
    project_path: Optional[str]
    project_url: Optional[str]
    display_name: Optional[str]
    
    # ========== 存储信息 ==========
    storage_version_id: Optional[str]
    storage_dir: Optional[str]
    
    # ========== CI/CD数据 ==========
    ci_data: Optional[Dict]
    ci_data_path: Optional[str]
    workflow_count: int
    actions_count: int
    
    # ========== 分析策略 ==========
    strategy: Optional[str]  # single/parallel/skip
    prompts: List[str]
    llm_responses: List[str]
    merged_response: Optional[str]
    
    # ========== 分析结果 ==========
    cicd_analysis: Optional[Dict]
    validation_result: Optional[Dict]
    report_md: Optional[str]
    report_html: Optional[str]
    architecture_json: Optional[Dict]
    analysis_summary: Optional[Dict]
    
    # ========== Review结果 ==========
    review_result: Optional[Dict]
    review_issues: List[Dict]
    corrected_report: Optional[str]
    fix_result: Optional[Dict]
    
    # ========== 智能Agent输出 ==========
    similar_projects: List[Dict]
    recommendations: List[Dict]
    reflection_result: Optional[Dict]
    
    # ========== 控制流（使用Reducer）==========
    errors: Annotated[List[str], merge_errors]
    warnings: Annotated[List[str], merge_warnings]
    completed_steps: Annotated[List[str], merge_steps]
```

### 5.2 字段分组说明

| 分组 | 主要字段 | 说明 |
|-----|---------|------|
| 用户输入 | user_input, intent, params | 用户输入和解析结果 |
| 项目信息 | project_name/path/url, display_name | 项目基本信息 |
| 存储信息 | storage_version_id, storage_dir | 存储位置信息 |
| CI/CD数据 | ci_data, workflow_count, actions_count | 提取的CI/CD配置数据 |
| 分析策略 | strategy, prompts | 分析策略和生成的prompts |
| 分析结果 | cicd_analysis, report_md/html, architecture_json | 分析输出结果 |
| Review结果 | review_result, review_issues, corrected_report | Review验证和修复结果 |
| 智能输出 | similar_projects, recommendations, reflection_result | 智能Agent输出 |
| 控制流 | errors, warnings, completed_steps | 流程控制和状态追踪 |

---

## 七、后台任务机制

### 6.1 BackgroundTasks

智能Agent通过BackgroundTasks异步执行：

```python
class BackgroundTasks:
    def submit_intelligence(self, state: Dict[str, Any]) -> Future:
        """提交智能分析任务"""
        return self.executor.submit(self._run_intelligence, state)
```

### 6.2 结果存储

智能分析结果保存到 `storage_dir/insights.json`：

```json
{
  "similar_projects": [...],
  "recommendations": [...],
  "reflection_result": {...},
  "generated_at": "2026-03-21T10:00:00Z"
}
```

---

## 八、计划功能（未来）

### 7.1 Checkpointer（LangGraph状态持久化）

LangGraph 的状态持久化机制，用于：

| 功能 | 说明 |
|------|------|
| 状态快照 | 保存每个节点执行后的状态 |
| 断点恢复 | 从任意节点恢复执行（用于人工审批） |
| 时间旅行 | 回溯到之前的状态进行调试 |
| 执行追踪 | 记录状态转换历史 |

**使用方式**：

```python
from langgraph.checkpoint.memory import MemorySaver

checkpointer = MemorySaver()
workflow.compile(checkpointer=checkpointer)
```

**配置说明**：
- 需安装 `langgraph-checkpoint` 依赖
- 本地开发使用 `MemorySaver`，生产环境可使用数据库存储
- 与 LangSmith Tracing 互补：checkpointer 负责状态持久化，LangSmith 负责可观测性

---

## 九、CLI命令

| 命令 | 说明 |
|------|------|
| `/analyze [type] <path>` | 分析项目的 CI/CD 架构 |
| `/compare <a> <b>` | 对比两个项目的 CI 架构 |
| `/list [--all]` | 列出已保存的项目 |
| `/show <name>` | 显示项目详情 |
| `/delete <name>` | 删除项目 |
| `/insights [name]` | 显示智能分析结果 |
| `/recommend [name]` | 显示改进建议 |
| `/similar [name]` | 显示相似项目 |
| `/help [topic]` | 显示帮助 |

---

## 十、文件结构规范

```
src/evaluator/
├── core/
│   ├── graphs/
│   │   ├── main_graph.py      # 主入口图
│   │   ├── analyze_graph.py   # 分析子图
│   │   └── compare_graph.py   # 对比子图
│   ├── background.py          # 后台任务管理器（基础设施类）
│   ├── routes.py              # 路由函数
│   └── __init__.py           # 导出create_main_graph
│
├── agents/
│   ├── base_agent.py          # Agent基类
│   ├── cicd_agent.py          # CI/CD分析Agent
│   ├── cicd/                  # CI/CD子Agent
│   │   ├── orchestrator.py     # 编排器（继承BaseAgent）
│   │   ├── state.py            # 状态定义 + 转换函数
│   │   ├── data_extraction_agent.py
│   │   ├── analysis_planning_agent.py
│   │   ├── llm_invocation_agent.py
│   │   ├── result_merging_agent.py
│   │   ├── quality_check_agent.py
│   │   ├── retry_handling_agent.py
│   │   ├── stage_organization_agent.py
│   │   ├── report_generation_agent.py
│   │   └── summary_generation_agent.py
│   ├── intelligence_pipeline.py  # 智能分析流水线（编排Agent）
│   ├── error_handler_agent.py   # 错误处理Agent
│   ├── state_validation_agent.py # 状态验证Agent
│   ├── storage_agent.py        # 智能Agent
│   ├── reflection_agent.py     # 智能Agent
│   └── recommendation_agent.py # 智能Agent
│
└── cli/
    └── app.py                 # CLI入口
```

---

## 十一、中断机制

### 8.1 概述

系统支持用户在任务执行过程中通过 Ctrl+C 中断任务。

### 8.2 架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                    InterruptController                           │
│                      (全局单例)                                  │
│                                                                  │
│  _interrupted: bool                                              │
│  _reason: str                                                    │
│  _callbacks: List[Callable]   ← 清理回调列表                     │
│  _current_node: str          ← 当前执行节点（用于显示）           │
│  _start_time: float          ← 任务开始时间                      │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│    CLI 层     │     │   Agent 层    │     │    LLM 层     │
│               │     │               │     │               │
│ signal 处理器 │     │ safe_run()    │     │ HTTP 客户端   │
│ Ctrl+C 捕获   │     │ 开头检查中断  │     │ 连接关闭      │
└───────────────┘     └───────────────┘     └───────────────┘
```

### 8.2 组件

| 组件 | 文件 | 职责 |
|------|------|------|
| InterruptController | `core/interrupt.py` | 全局中断控制 |
| 信号处理器 | `cli/app.py` | 捕获 Ctrl+C |
| Agent 中断检查 | `agents/base_agent.py` | safe_run 开头检查 |
| LLM 连接关闭 | `llm/client.py` | 关闭 HTTP 连接 |

### 8.3 中断时机

| 层级 | 触发位置 | 效果 |
|------|---------|------|
| **Agent 级** | `safe_run()` 开头 | 下一个 Agent 执行前中断 |
| **LLM 级** | `httpx_client.close()` | 关闭连接，停止等待响应 |
| **后台任务** | `cancel_all()` | 取消所有后台任务 |

### 8.4 中断后显示

```
⚠️  任务已中断
  原因: 用户按下 Ctrl+C
  已运行时间: 12.5s
  当前节点: cicd
  已完成节点: intent_parser, orchestrator, input, loader
```

### 8.5 使用方式

```python
from evaluator.core.interrupt import interrupt_controller, InterruptException

# 触发中断
interrupt_controller.interrupt("原因")

# 检查中断（在 Agent 中）
interrupt_controller.check()

# 注册清理回调
interrupt_controller.register_callback(my_cleanup_fn)
```

### 8.6 实现细节

1. **InterruptController**: 单例模式，通过 `register_callback()` 注册清理函数
2. **HTTP 连接关闭**: 使用 httpx 客户端，支持 `StreamClosed`、`CloseError`、`ProtocolError` 捕获
3. **信号处理**: 捕获 `SIGINT` 信号（Windows 支持）
4. **后台任务**: `ThreadPoolExecutor.future.cancel()` 取消任务

---

## 十二、变更记录

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| 2.3.0 | 2026-04-05 | 更新Agent列表，添加详细说明和调用关系图 |
| 2.1.0 | 2026-03-21 | CLI 使用 LangGraph 统一工作流 |
| 2.0.0 | 2026-03-21 | 架构重构：统一 LangGraph 编排 |

---

## 十三、附录

### A. 术语表

| 术语 | 定义 |
|------|------|
| Agent | 实现具体业务逻辑的组件，必须继承BaseAgent |
| BaseAgent | Agent基类，定义统一接口 |
| LangGraph | 工作流编排引擎 |
| CICDOrchestrator | CI/CD分析的编排器（继承BaseAgent） |
| IntelligencePipeline | 智能分析流水线编排Agent |
| BackgroundTasks | 后台任务管理器（基础设施类，不继承Agent） |
| Reducer | 状态合并函数，用于LangGraph状态更新 |

### B. 相关文档

- [AGENTS.md](./AGENTS.md) - Agent 索引文档
- [CHANGELOG.md](./CHANGELOG.md) - 更新日志
- [README.md](./README.md) - 使用说明
