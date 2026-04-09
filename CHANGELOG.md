# Changelog - 更新日志

## 2026-03-23

### 功能新增: 全局中断机制

#### 功能描述

支持用户在任务执行过程中通过 Ctrl+C 中断任务，包括：
- Agent 级中断：在 Agent 执行前检查并中断
- LLM 级中断：关闭 HTTP 连接，取消正在进行的 LLM 请求
- 后台任务中断：取消所有后台智能分析任务

#### 使用方式

在任务执行过程中按下 Ctrl+C 即可中断。

#### 中断后显示

- 中断原因
- 已运行时间
- 当前执行节点
- 已完成节点列表

#### 技术实现

1. **InterruptController**: 全局中断控制器（单例模式）
   - `interrupt()`: 触发中断
   - `check()`: 检查中断状态
   - `register_callback()`: 注册清理回调

2. **LLM HTTP 连接关闭**: 使用 httpx 客户端，中断时关闭连接

3. **信号处理**: 捕获 SIGINT 信号，触发中断

#### 文件改动

- 新增 `src/evaluator/core/interrupt.py`
- 修改 `src/evaluator/agents/base_agent.py`
- 修改 `src/evaluator/llm/client.py`
- 修改 `src/evaluator/cli/app.py`
- 修改 `src/evaluator/core/background.py`

### Bug 修复: ReviewerAgent 重试字段名不一致

#### 问题描述

ReviewerAgent 设置 `cicd_retry_mode`、`cicd_retry_issues`，但 CICDOrchestrator 和 RetryHandlingAgent 读取 `retry_mode`、`retry_issues`，导致重试逻辑被跳过，报告不完整时整体重新运行。

#### 修复方案

**routes.py - prepare_cicd_retry**:
- 添加 `retry_mode`、`retry_issues`、`cicd_existing_report` 字段
- 统一字段名供下游 Agent 使用

### Bug 修复: IntentParser 自然语言解析问题

#### 问题描述

1. LLM 解析失败：`'\n  "intent"'` - JSON 正则表达式无法正确匹配包含嵌套对象的 JSON
2. `_extract_project_name` 无法匹配带空格的项目名：如 "分析 cccl 项目"（中间有空格）
3. `InputAgent` 未设置 `project_url`，导致 `LoaderAgent` 验证失败

#### 修复方案

1. **intent_parser_agent.py - _parse_llm_response**:
   - 改进 JSON 提取逻辑，支持多种格式
   - 方法1: 提取 ```json ... ``` 代码块
   - 方法2: 找第一个 { 到最后一个 }

2. **intent_parser_agent.py - INTENT_PARSER_PROMPT**:
   - 简化 Prompt，要求 LLM 返回单行 JSON
   - 移除冗余说明，聚焦格式要求

3. **intent_parser_agent.py - _extract_project_name**:
   - 改进正则表达式 `r'([^\s]+)\s*项目'` 支持空格
   - 新增逻辑：查找 "项目" 前的词汇

4. **input_agent.py - _handle_local_path**:
   - 添加 `project_url: None` 字段，修复 LoaderAgent 验证失败

### Bug 修复: 统一入口点状态管理

#### 问题描述

CLI 解析意图后调用 LangGraph，但 `_handle_list`、`_handle_show`、`_handle_delete` 等方法创建的初始状态缺少必要字段，导致 IntentParserAgent 验证失败。

错误日志：
```
IntentParserAgent: 缺失输入字段 ['known_projects', 'context']
```

#### 修复方案

采用**统一入口点方案 D**：意图解析只做一次，在 LangGraph 入口处。

1. **state.py**: 添加 `known_projects` 和 `context` 字段定义
2. **intent_parser_agent.py**: 
   - 更新 `describe()` 移除 `known_projects` 和 `context` 的硬性要求
   - 更新 `run()` 检测已解析意图并跳过重复解析
3. **app.py**: 
   - `_handle_list` 添加 `known_projects`、`context`、`user_input` 字段
   - `_handle_show` 添加 `known_projects`、`context`、`user_input` 字段
   - `_handle_delete` 添加 `known_projects`、`context`、`user_input` 字段
   - `_handle_compare` (已有完整字段)
   - `_handle_analyze` (已有完整字段)

#### 执行流程

```
CLI 解析意图
    │
    ▼
_handle_*() 创建初始状态
    │
    ▼
graph.invoke(initial_state)  ← 进入 LangGraph，不是直接调用 agent
    │
    ▼
intent_parser 节点 (检测已解析则跳过)
    │
    ▼
orchestrator 节点 (统一编排)
    │
    ▼
handler 节点 (执行具体操作)
```

### 功能增强: LangSmith 可观测性改进

#### 后台任务关联 trace

- ✅ background.py 新增 `parent_run_id` 参数
- ✅ `_run_intelligence` 方法支持 trace context 传递
- ✅ main_graph.py 在提交后台任务时获取并传递 `parent_run_id`

#### 并发 LLM 调用追踪

- ✅ llm_invocation_agent.py 新增 `_parallel_calls_with_runnable` 方法
- ✅ 使用 `RunnableParallel` 替代部分 `ThreadPoolExecutor` 调用
- ✅ 保留 `_parallel_calls_with_threadpool` 作为回退方案
- 自动关联 trace，无需手动传递 `parent_run_id`

### 功能增强: 配置统一管理

#### 配置模块重构

- ✅ 重写 `src/evaluator/config.py`，新增 13 个配置项
- ✅ 更新 `.env` 文件，添加所有配置项及注释说明
- ✅ 更新 `.env.example` 文件，作为配置模板

#### 配置项列表

| 分类 | 配置项 | 环境变量 | 默认值 |
|------|--------|----------|--------|
| 重试 | `max_retries` | EVAL_MAX_RETRIES | 3 |
| | `llm_max_retries` | EVAL_LLM_MAX_RETRIES | 5 |
| | `llm_retry_base_delay` | EVAL_LLM_RETRY_DELAY | 1.0 |
| 并发 | `max_background_workers` | EVAL_MAX_WORKERS | 1 |
| | `max_llm_workers` | EVAL_LLM_WORKERS | 4 |
| | `max_concurrent_llm_calls` | EVAL_LLM_CONCURRENT | 4 |
| 超时 | `git_clone_timeout` | EVAL_GIT_TIMEOUT | 300 |
| | `llm_request_timeout` | EVAL_LLM_REQUEST_TIMEOUT | 300 |
| | `llm_call_timeout` | EVAL_LLM_TIMEOUT | 600 |
| LLM | `llm_max_tokens` | EVAL_LLM_MAX_TOKENS | 131072 |
| 报告 | `max_section_length` | EVAL_MAX_SECTION_LENGTH | 3000 |
| | `max_workflows_single` | EVAL_MAX_WORKFLOWS_SINGLE | 10 |
| | `max_workflows_batch` | EVAL_MAX_WORKFLOWS_BATCH | 10 |

#### 配置使用更新

- ✅ llm/client.py 使用 config.llm_request_timeout 和 config.llm_max_tokens
- ✅ reviewer_agent.py 使用 config.max_section_length, config.llm_call_timeout, config.max_retries, config.llm_retry_base_delay
- ✅ llm_invocation_agent.py 使用 config.llm_max_retries, config.llm_retry_base_delay
- ✅ analysis_planning_agent.py 使用 config.max_workflows_single, config.max_workflows_batch
- ✅ orchestrator_agent.py, background.py, git_ops.py 已有配置继续使用

### 问题修复: LangGraph 边定义冲突

#### 修复内容

- ✅ main_graph.py 条件边添加 `orchestrator` 作为正常完成目标
- ✅ routes.py 路由函数修改：`route_after_input`、`route_after_loader`、`route_after_cicd`、`route_after_review` 返回 `orchestrator` 而非直接跳转到下一节点
- ✅ 移除固定边定义（input → orchestrator、loader → orchestrator、cicd → orchestrator、reviewer → orchestrator）
- 业务流变化：所有 Agent 正常完成后返回 `orchestrator` 决定下一步，而非直接跳转

### 问题修复: 硬编码配置统一

#### 配置模块

- ✅ 新建 `src/evaluator/config.py` 配置模块
- ✅ 支持环境变量覆盖默认值（EVAL_MAX_RETRIES、EVAL_MAX_WORKERS 等）

#### 配置使用

- ✅ orchestrator_agent.py 使用 `config.max_retries`
- ✅ background.py 使用 `config.max_background_workers`
- ✅ git_ops.py 使用 `config.git_clone_timeout`
- ✅ llm_invocation_agent.py 使用 `config.max_concurrent_llm_calls` 和 `config.llm_call_timeout`
- ✅ reviewer_agent.py 使用 `config.max_llm_workers`

### Phase 2: 错误处理统一

#### 主图集成

- ✅ main_graph.py 添加 `error_handler` 节点
- ✅ main_graph.py 添加 `validate` 节点（StateValidationAgent）
- ✅ 为 input、loader、cicd、reviewer 节点添加错误处理条件边
- ✅ 添加 `route_error` 路由函数（retry/recover/end）
- ✅ 添加 `route_after_validate` 路由函数

#### ErrorHandlerAgent 增强

- ✅ 支持错误分类（致命错误 vs 可恢复错误）
- ✅ 新增 `_is_fatal()` 和 `_is_recoverable()` 方法
- ✅ 新增 `error_recoverable` 输出字段
- 打印错误处理日志（错误数量、策略）

#### Agent 异常捕获

- ✅ `_create_node()` 使用 `safe_run()` 替代 `run()`
- ✅ `safe_run()` 增加异常捕获逻辑
- 异常信息追加到 `errors` 字段，避免流程崩溃

### Phase 3: 状态管理优化

#### 状态转换简化

- ✅ cicd/state.py 新增 `CICD_STATE_FIELDS` 字段分组定义
- ✅ `to_cicd_state()` 使用字段分组自动映射
- ✅ `from_cicd_state()` 只复制输出字段，避免覆盖

#### 状态验证装饰器

- ✅ base_agent.py 新增 `validate_state()` 装饰器
- 在 Agent run 方法执行前验证必需字段

### Phase 1: 可观测性增强

#### Agent 追踪

- ✅ BaseAgent 添加 `@traceable()` 装饰器（`run` 和 `safe_run` 方法）
- ✅ routes.py 添加 `@traceable()` 装饰器（12 个路由函数）
- 支持 LangSmith 追踪（需设置 `LANGCHAIN_TRACING_V2=true` 环境变量）

#### LLM 回调

- ✅ LLMClient 新增 `LLMCallbackHandler` 类（继承 `BaseCallbackHandler`）
- 记录 LLM 调用开始、结束、错误事件
- 记录调用耗时和 token 使用情况

## 2026-03-22

### Phase 16.1: 响应变量语义统一

#### 语义定义

| 变量 | 语义 | 用途 |
|------|------|------|
| `llm_responses` | 原始响应列表 | 保留（每次调用的原始结果） |
| `merged_response` | 合并后最终响应 | 保留（唯一最终响应） |
| `llm_response` | ~~单次原始响应~~ | **已移除** |

#### 代码修改

- ✅ RetryHandlingAgent：输出从 `llm_response` 改为 `merged_response`
- ✅ StageOrganizationAgent：输入/输出从 `llm_response` 改为 `merged_response`
- ✅ ReportGenerationAgent：移除兼容代码，只使用 `merged_response`
- ✅ SummaryGenerationAgent：移除兼容代码，只使用 `merged_response`
- ✅ state.py：CICDState 移除 `llm_response` 字段，新增 `batch_files`、`main_rounds`、`main_system_prompt` 字段

### Phase 16: 多轮对话模式优化

#### 功能优化

- ✅ LLMClient 新增 `chat_multi_round()` 方法（支持多轮对话）
- ✅ LLMClient 新增 `_invoke_with_timeout()` 方法（带超时的 LLM 调用）
- ✅ ci_diagram_generator.py 新增 `generate_multi_round_prompts()` 函数
- ✅ ci_diagram_generator.py 新增 10 个 `_generate_round_*()` 函数（Round 0-9）
- ✅ CIAnalyzer 新增 `use_multi_round` 参数（默认启用多轮对话）
- ✅ LLMInvocationAgent 新增 `_multi_round_call()` 方法
- ✅ LLMInvocationAgent 新增 `_execute_multi_round()` 方法
- ✅ LLMInvocationAgent 新增 `_merge_multi_round_responses()` 方法
- ✅ AnalysisPlanningAgent 适配新的 prompt 策略

#### 问题解决

- 解决 prompt_main.txt 输出要求过于复杂导致 LLM 卡住的问题
- 多轮对话模式将 main 分析拆分为 10 个 rounds，每轮只输出 1 个章节
- 降低单轮输出量，从 ~15000 字符降至 ~2000 字符/轮

## 2026-03-21

### Phase 12.1: Review修复 (ses_2ef7)

#### P0 Bug 修复

- ✅ ToolSelectionAgent 删除重复 `__init__` 方法（行91-92覆盖行35-37）
- ✅ ReportGenerationAgent 添加 `super().__init__()`（修复继承问题）

### Phase 13: 工作流执行修复

#### Bug 修复

- ✅ IntentParserAgent 跳过已解析状态（CLI 命令直接设置 intent 时不再重复解析）
- ✅ validate_agent_dependencies 修复依赖匹配逻辑（支持 intent_parser ↔ IntentParserAgent）

### Phase 15: CI/CD 报告生成修复

#### Bug 修复

- ✅ QualityCheckAgent 移除 `_organize_stages` 调用（避免卡死，后续由 StageOrganizationAgent 处理）
- ✅ StageOrganizationAgent 修复字段名（使用 `merged_response` 替代 `llm_response`）
- ✅ ReportGenerationAgent 修复字段名（使用 `merged_response` 替代 `llm_response`）
- ✅ _simple_parse 调整检测顺序（意图优先于项目匹配）
- ✅ 扩展意图关键词（帮助、分析、对比、详情、删除）
- ✅ 新增 _extract_project_name 方法（从自然语言提取项目名称）
- ✅ 新增 _extract_two_projects 方法（从自然语言提取两个项目）

### Phase 12: Review P0/P1修复

#### P0 关键修复

- ✅ ToolSelectionAgent 添加 `run()` 方法（支持 LangGraph 节点）
- ✅ main.py 修复导入路径 (`evaluator.core.graphs.create_main_graph`)
- ✅ ArchitectureValidationAgent 修复状态直接修改（使用 `{**state, ...}` 模式）

#### P1 修复

- ✅ ToolSelectionAgent 添加 `super().__init__()` + 移除孤立 docstring
- ✅ IntentParserAgent 添加 `super().__init__()`
- ✅ DataExtractionAgent 添加 `super().__init__()`
- ✅ AnalysisPlanningAgent 添加 `super().__init__()`
- ✅ RetryHandlingAgent 添加 `super().__init__()`
- ✅ StageOrganizationAgent 添加 `super().__init__()`
- ✅ ReportGenerationAgent 添加 `super().__init__()`
- ✅ SummaryGenerationAgent 添加 `super().__init__()`

### Phase 11: Bug修复

#### Bug 修复

- ✅ ReviewerAgent 添加 `super().__init__()`
- ✅ ReporterAgent 添加 `super().__init__()`
- ✅ LoaderAgent 添加 `super().__init__()`
- ✅ QualityCheckAgent 添加 `super().__init__()`
- ✅ ReflectionAgent 修复变量未定义（添加 `total = len(self.history)`）
- ✅ test_agents.py 移除不存在的 `CICDAgentFacade`
- ✅ StorageManager 添加公共方法 `get_version_dir()`
- ✅ CompareAgent 使用公共方法替代私有方法

### Phase 10: Review架构修复

#### Review 问题修复

- ✅ 修复 LLMInvocationAgent 未正确继承 BaseAgent（添加 `super().__init__()`）
- ✅ CLI 移除无用导入（InputAgent/LoaderAgent）

### Phase 9: Review深度修复

#### Review 问题修复

- ✅ 修复 CICD 子Agent 循环依赖（LLMInvocationAgent 移除对 ResultMergingAgent 的直接调用）
- ✅ 修复 CompareAgent 签名错误（改为 `run(state) -> Dict`，使用 `{**state, ...}`）
- ✅ 修复 CLI 简单命令绕过 LangGraph（_handle_list/show/delete 使用 LangGraph）
- ✅ IntelligencePipeline 使用 LangGraph 编排（支持并行）
- ✅ 更新 AGENTS.md 和 ARCHITECTURE.md

### Phase 8: Review修复

#### Review问题修复

- ✅ CICDOrchestrator 继承 BaseAgent
- ✅ 新增状态转换函数 `to_cicd_state()` / `from_cicd_state()`
- ✅ CICDAgent 使用状态转换函数
- ✅ InputAgent 无状态构造
- ✅ 移除 CLI 回退机制（langgraph 是强制依赖）
- ✅ 新增 IntelligencePipeline Agent
- ✅ BackgroundTasks 使用 IntelligencePipeline
- ✅ 动态生成条件边目标
- ✅ 简化节点包装函数，使用通用 `_create_node()`
- ✅ 新增 ErrorHandlerAgent
- ✅ 新增 StateValidationAgent
- ✅ 新增 `validate_agent_dependencies()` 依赖验证
- ✅ 更新 AGENTS.md 和 ARCHITECTURE.md

### Phase 7: Agent规范化

#### 所有Agent继承BaseAgent

- ✅ DataExtractionAgent 继承 BaseAgent
- ✅ AnalysisPlanningAgent 继承 BaseAgent
- ✅ LLMInvocationAgent 继承 BaseAgent
- ✅ ResultMergingAgent 继承 BaseAgent + **修复签名** (P0)
- ✅ QualityCheckAgent 继承 BaseAgent
- ✅ RetryHandlingAgent 继承 BaseAgent + **修复状态不可变** (P0)
- ✅ ArchitectureValidationAgent 继承 BaseAgent
- ✅ StageOrganizationAgent 继承 BaseAgent + **修复状态不可变** (P0)
- ✅ ReportGenerationAgent 继承 BaseAgent
- ✅ SummaryGenerationAgent 继承 BaseAgent
- ✅ ListHandlerAgent 继承 BaseAgent
- ✅ InfoHandlerAgent 继承 BaseAgent
- ✅ DeleteHandlerAgent 继承 BaseAgent
- ✅ HelpHandlerAgent 继承 BaseAgent
- ✅ ToolSelectionAgent 继承 BaseAgent
- ✅ RecommendationAgent **移除重复__init__**
- ✅ CICDState 添加 `llm_response` 和 `cicd_analysis` 字段
- ✅ 更新 ARCHITECTURE.md (v4.2.0)

### Phase 6: CLI统一LangGraph

#### CLI使用LangGraph统一工作流

- ✅ `_handle_analyze` 使用 LangGraph 执行分析
- ✅ `_handle_compare` 使用 LangGraph 执行对比
- ✅ 保留直接调用模式作为回退
- ✅ InputAgent 继承 BaseAgent
- ✅ LoaderAgent 继承 BaseAgent
- ✅ IntentParserAgent 继承 BaseAgent
- ✅ CICDAgent 继承 BaseAgent
- ✅ ReviewerAgent 继承 BaseAgent，使用 `{**state, ...}` 模式
- ✅ ReporterAgent 继承 BaseAgent，使用 `{**state, ...}` 模式
- ✅ CompareAgent 继承 BaseAgent
- ✅ 更新 ARCHITECTURE.md (v4.1.0)

### Phase 5: CICDAgent重构

#### CICDAgent子Agent架构完成

- ✅ 新增 RetryHandlingAgent (重试处理)
- ✅ 新增 ArchitectureValidationAgent (架构验证)
- ✅ 新增 StageOrganizationAgent (阶段组织)
- ✅ 新增 ReportGenerationAgent (报告生成)
- ✅ 新增 SummaryGenerationAgent (摘要生成)
- ✅ 更新 CICDOrchestrator 编排逻辑
- ✅ 删除原有CICDAgent实现(1200+行)
- ✅ CICDAgent继承BaseAgent
- ✅ 更新ARCHITECTURE.md和AGENTS.md

### Phase 4: 智能Agent集成

- ✅ 新增 BaseAgent 基类定义 (`base_agent.py`)
- ✅ 新增 BackgroundTasks 后台任务管理器 (`core/background.py`)
- ✅ StorageAgent 继承 BaseAgent，添加 `run()` 方法
- ✅ ReflectionAgent 继承 BaseAgent，添加 `run()` 方法
- ✅ RecommendationAgent 继承 BaseAgent，添加 `run()` 方法
- ✅ OrchestratorAgent 委托工具选择给 ToolSelectionAgent
- ✅ 新增 CLI 命令：/insights, /recommend, /similar
- ✅ ReporterAgent 完成后自动触发异步智能Agent

### Phase 1-3: 初始架构

- ✅ 拆分 CICDAgent 为 6 个子 Agent
- ✅ 新增 CICDOrchestrator 编排器
- ✅ 新增 LangGraph 工作流
- ✅ 新增 StorageAgent, ReflectionAgent, RecommendationAgent
