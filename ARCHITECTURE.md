# Eval-Agent 架构设计文档

> 版本: 2.3.1  
> 最后更新: 2026-04-06  
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
| ❌ 使用ThreadPoolExecutor | 无法关联LangSmith trace，必须使用统一并发工具 |

### 1.3 统一并发工具

**所有并发执行必须使用统一工具类**：

```python
from evaluator.utils import parallel_execute

# 创建任务列表
tasks = [lambda: task1(), lambda: task2(), lambda: task3()]

# 并发执行（自动关联LangSmith trace）
results = parallel_execute(tasks, max_concurrent=4)
```

**工具位置**：`src/evaluator/utils/concurrency.py`

**核心优势**：
- ✅ 自动使用RunnableParallel关联trace
- ✅ 自动分批执行限制并发数
- ✅ 统一维护，避免重复实现
- ✅ 简化代码，提高可读性

**禁止事项**：
- ❌ 直接使用ThreadPoolExecutor
- ❌ 直接使用RunnableParallel（应通过工具类）
- ❌ 重复实现并发逻辑

### 1.4 Agent分类

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

**当前功能缺陷与改进方向**：

### 一、锚点定位问题

**1. 删除锚点无效**（方案2+3）
- **缺陷**：`trigger_fabricated` 使用 `trigger_yaml` 锚点，返回 `start == end`，导致删除操作无效
- **影响**：删除触发条件时，报告内容未改变，可能陷入无限循环
- **优化方案**：
  - 创建专门的 `trigger_line` 锚点类型，定位具体触发条件行
  - 返回 `start < end` 的位置，使删除操作生效
  - 实施位置：`strategy.py` 添加 `_resolve_trigger_line` 方法
  - 修改 `coordinator.py` 锚点映射：`trigger_fabricated` → `trigger_line`
- **优先级**：中（作为方案1的双重保险）
- **状态**：待观察方案1效果后决定

**2. Job节点操作空实现**
- **缺陷**：`_add_job_node` 和 `_remove_job_node` 是空实现
- **原因**：Job 信息在 architecture.json 中是嵌入在 workflow 节点的 `jobs` 字段，不是独立节点
- **影响**：Job 相关问题无法自动修复
- **优化方案**：
  - 选项A：保持现状（Job 只是数量统计）
  - 选项B：Job 作为独立节点（需修改 architecture.json 结构）
  - 选项C：Job 作为 workflow 节点的子节点（嵌套结构）
- **建议**：选项A（保持现状），当前 HTML 报告不需要 Job 级别的架构图
- **优先级**：低
- **状态**：暂缓实施

### 二、数据一致性问题

**3. 新增节点缺少 connections**
- **缺陷**：添加节点（`trigger_missing`, `workflow_missing`）时，只添加节点，不添加 connections
- **影响**：新增节点孤立，没有连接关系，HTML 架构图显示不完整
- **优化方案**：
  - 方案A：在添加节点时，从 ci_data 提取连接信息并添加 connections（复杂）
  - 方案B：检测到新增节点时，自动触发重新生成 architecture.json（用户体验差）
  - 方案C：验证时发现连接缺失，提示用户重试（推荐）
- **优先级**：中
- **状态**：暂未实施，建议采用方案C

**4. 删除节点遗留无效 connections**（已解决）
- **缺陷**：删除节点后，connections 中仍指向已删除节点
- **影响**：HTML 渲染错误（找不到目标节点）
- **优化方案**：在保存 architecture.json 前，清理无效连接
- **实施位置**：`report_fix_agent.py` 的 `_clean_invalid_connections` 方法
- **优先级**：高
- **状态**：✅ 已实施（方案A-简化版3）

**5. 多文件同步不完整**
- **缺陷**：当前只同步 architecture.json 和 summary.json，未同步 CI_ARCHITECTURE.md 的其他部分
- **影响**：修复后，报告中的架构图、调用关系树等可能与实际不一致
- **优化方案**：
  - 同步更新架构图（ASCII art）
  - 同步更新调用关系树
  - 同步更新连接关系说明
- **优先级**：低
- **状态**：暂未实施

### 三、修复可靠性问题

**6. 缺少修复效果验证**
- **缺陷**：修复后没有验证是否真正解决了问题
- **影响**：修复可能失败但未发现，继续生成错误报告
- **优化方案**：
  - 修复后，对修复的内容进行二次验证
  - 检查问题是否仍然存在
  - 如果仍存在，标记为修复失败，记录原因
- **优先级**：中
- **状态**：暂未实施

**7. Markdown 格式完整性**
- **缺陷**：删除内容后，可能导致 Markdown 格式错误
- **影响**：
  - 删除表格行后，表格格式可能破坏
  - 删除 YAML 块中的行后，缩进可能错误
  - 删除章节内容后，标题层级可能不连续
- **优化方案**：
  - 删除后，验证 Markdown 格式
  - 自动修复格式错误（如表格分隔符、空行等）
  - 如果无法自动修复，标记为需要手动处理
- **优先级**：中
- **状态**：暂未实施

**8. 修复操作缺少事务性**
- **缺陷**：如果修复过程中出错，可能导致数据不一致
- **影响**：部分文件已修改，部分未修改，状态不一致
- **优化方案**：
  - 实现事务机制：修改前备份，出错时回滚
  - 或者：先在内存中完成所有修改，最后一次性保存
- **优先级**：低
- **状态**：暂未实施

**9. LLM 修复缺少重试机制**
- **缺陷**：LLM 生成内容可能失败，没有重试逻辑
- **影响**：LLM 修复失败后，问题未解决
- **优化方案**：
  - 添加重试机制（最多3次）
  - 失败后降级到其他修复方式或标记为无法修复
- **优先级**：低
- **状态**：暂未实施

### 四、可观测性问题

**10. 修复日志不完整**
- **缺陷**：当前只记录修复类型和操作，缺少详细日志
- **影响**：不利于问题追踪和调试
- **优化方案**：
  - 记录修复前后的内容对比（diff）
  - 记录修复耗时
  - 记录修复失败原因
  - 保存修复日志到单独文件
- **优先级**：低
- **状态**：暂未实施

**11. 缺少修复统计**
- **缺陷**：没有统计修复成功率、失败原因分布等
- **影响**：无法评估修复效果，难以优化
- **优化方案**：
  - 统计各类问题的修复成功率
  - 统计修复失败原因分布
  - 生成修复效果报告
- **优先级**：低
- **状态**：暂未实施

### 五、实施优先级总结

**高优先级（已实施）**：
- ✅ 修复触发条件提取逻辑（方案1）
- ✅ 清理无效 connections（方案A-简化版3）

**中优先级（建议实施）**：
- 删除锚点优化（方案2+3）
- 新增节点 connections 处理
- 修复效果验证
- Markdown 格式完整性

**低优先级（可选实施）**：
- Job 节点操作实现
- 多文件同步完整性
- 修复操作事务性
- LLM 修复重试机制
- 修复日志完善
- 修复统计

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

### 6.3 后续优化方向

**当前限制**：
- BackgroundTasks使用ThreadPoolExecutor，无法完美关联LangSmith trace
- IntelligencePipeline内部是同步执行，无法利用异步优势
- 虽然通过parent_run_id手动关联trace，但不够优雅

**优化路径**：

#### 阶段1：异步Agent支持
为所有Agent添加异步方法：

```python
class BaseAgent(ABC):
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """同步执行"""
        pass
    
    async def arun(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """异步执行"""
        # 默认实现：在事件循环中运行同步方法
        return await asyncio.get_event_loop().run_in_executor(
            None, 
            lambda: self.run(state)
        )
```

#### 阶段2：IntelligencePipeline并发优化
使用混合模式并发执行：

```python
from evaluator.utils import parallel_execute_dict

# Storage独立执行
storage_result = StorageAgent().run(state)

# Recommendation + Reflection并发执行
tasks = {
    "recommendation": lambda: RecommendationAgent().run(state),
    "reflection": lambda: ReflectionAgent().run(state),
}
results = parallel_execute_dict(tasks, max_concurrent=2)
```

#### 阶段3：BackgroundTasks异步改造
使用asyncio事件循环替代ThreadPoolExecutor：

```python
import asyncio

class BackgroundTasks:
    def __init__(self):
        self._loop = asyncio.new_event_loop()
    
    def submit_intelligence(self, state: Dict[str, Any]):
        async def run_pipeline():
            pipeline = IntelligencePipeline()
            return await pipeline.arun(state)
        
        task = asyncio.create_task(run_pipeline())
        return task
```

**预期收益**：
- ✅ 完美关联LangSmith trace
- ✅ 提升性能（并发执行）
- ✅ 统一异步架构
- ✅ 更优雅的实现

**实施时机**：
- 短期：保持现状，通过parent_run_id关联trace
- 中期：实现阶段1和阶段2
- 长期：实现阶段3，完全移除ThreadPoolExecutor

### 6.4 LangchainCallbackHandler 移除说明

**移除时间**：2026-04-06

**移除原因**：
- langchain-core 1.x 已移除 LangchainCallbackHandler 类
- 该类在项目中从未实际使用
- 保留会导致导入失败，影响核心 traceable 功能

**历史背景**：
- 最初引入是为了解决 BackgroundTasks 的 trace 关联问题
- 但一直通过 parent_run_id 手动关联，未实际调用
- get_callback_handler() 函数从未被使用

**影响范围**：
- ✅ 无影响（从未使用）
- ✅ 核心功能 traceable 正常工作
- ✅ BackgroundTasks 通过 parent_run_id 关联 trace

**未来优化方向**：
- 短期：保持 parent_run_id 方案（当前状态）
- 中期：实现异步 Agent（arun 方法）
- 长期：使用 asyncio 替代 ThreadPoolExecutor
- 参考：6.3 节的三阶段优化路径

**如需重新引入**：
- 如果 langchain-core 未来版本重新提供类似功能
- 或使用 langchain-community 包中的替代方案
- 需在 BackgroundTasks 优化时评估

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

### 7.2 动态工具选择（未来功能）

**当前状态**：未启用（保留实现）

**相关Agent**：ToolSelectionAgent

**设计意图**：
- 动态选择和组合工具
- LLM驱动的工具选择
- 灵活的工作流编排

**当前未启用原因**：

| 原因 | 说明 |
|-----|------|
| **稳定性** | 核心功能编排需要可预测的行为 |
| **确定性** | 避免动态选择带来的不确定性 |
| **性能** | 减少LLM调用开销 |
| **简洁性** | 静态模板已满足当前需求 |

**当前实现**：
- OrchestratorAgent使用静态WORKFLOW_TEMPLATES
- 工作流根据intent硬编码
- 无动态工具选择逻辑

**未来启用场景**：

1. **自定义分析流程**
   - 用户定义分析步骤
   - 灵活组合分析工具
   - 个性化工作流

2. **插件系统**
   - 第三方插件集成
   - 动态加载工具
   - 扩展分析能力

3. **用户定义工作流**
   - 配置文件定义工作流
   - 可视化工作流编辑器
   - 工作流模板市场

**启用路径**：

```python
# 配置开关
config.use_dynamic_tool_selection = False  # 默认关闭

# OrchestratorAgent决策逻辑
if config.use_dynamic_tool_selection:
    tools = self.select_tools(task, context)  # 动态选择
else:
    workflow = self.WORKFLOW_TEMPLATES.get(intent)  # 静态模板
```

**实施时机**：
- 短期：保持静态模式
- 中期：实现配置开关
- 长期：在附加功能中启用

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
| 2.3.1 | 2026-04-06 | 修复触发条件提取逻辑，添加无效连接清理，记录未来改进方向 |
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
