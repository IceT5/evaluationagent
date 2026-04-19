# Eval-Agent 开发指南

> AI编程工具请先阅读本文档，遵从所有开发要求。Claude Code 用户请同时参考 [CLAUDE.md](./CLAUDE.md)（自动加载）。

## 核心原则（必须遵从）

### 1. 代码复用优先

**修改前必须检查**：
- 是否已有可复用的代码？
- 是否可以扩展现有功能而非新增？
- 是否有相似的实现可以参考？

**禁止**：
- ❌ 直接新增代码而不分析复用可能性
- ❌ 重复实现已有功能
- ❌ 创建相似但不一致的实现

### 2. LangSmith Trace支持（关键要求）

**必须支持trace**：
- 使用 `@traceable()` 装饰器标记Agent
- **使用统一并发工具** `evaluator.utils.parallel_execute` 实现并发
- 自动关联LangSmith trace，无需手动处理

**禁止**：
- ❌ 使用 ThreadPoolExecutor（无法关联trace）
- ❌ 直接使用 RunnableParallel（应使用统一工具）
- ❌ 无法追踪的并发方式

**统一并发工具**：
```python
from evaluator.utils import parallel_execute

# 创建任务列表
tasks = [lambda: task1(), lambda: task2(), lambda: task3()]

# 并发执行（自动关联trace）
results = parallel_execute(tasks, max_concurrent=4)
```

**工具优势**：
- ✅ 自动使用RunnableParallel关联trace
- ✅ 自动分批执行限制并发数
- ✅ 统一维护，避免重复实现
- ✅ 简化代码，提高可读性

### 3. 统一编排原则

**单一入口**：
- 所有执行必须通过 LangGraph
- CLI不直接调用Agent
- Agent不跨层调用

**禁止**：
- ❌ 绕过 LangGraph
- ❌ 在 CLI 层处理业务逻辑
- ❌ 使用全局状态

### 4. Agent开发规范

**必须继承BaseAgent**：
```python
from evaluator.agents.base_agent import BaseAgent, AgentMeta

class MyAgent(BaseAgent):
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="MyAgent",
            description="职责描述",
            category="analysis",
            inputs=["input_field"],
            outputs=["output_field"],
        )
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        # 读取输入
        value = state["input_field"]
        # 处理
        result = self._process(value)
        # 返回更新（必须包含所有原字段）
        return {**state, "output_field": result}
```

**约束**：
- ✅ 单一职责：每个Agent只做一件事
- ✅ 状态驱动：输入输出都通过state
- ✅ 返回state超集：`{**state, "new": value}`
- ❌ 不能删除state字段
- ❌ 不能修改其他Agent输出（除非明确需要）

### 5. 状态管理

**字段定义**：
- 所有字段在 `state.py` 中定义
- 新增字段必须同步更新 EvaluatorState
- 使用TypedDict提供类型提示

**命名规范**：
- `{agent}_result`：Agent执行结果（如`cicd_result`）
- `{agent}_output`：Agent输出数据（如`report_html`）
- `{data}_data`：原始数据（如`ci_data`）
- `{data}_json`：JSON数据（如`architecture_json`）

**CI/CD 链路新增约束**：
- `cicd_assembled_data` 是 CI/CD 最终结构化真相源
- `batch_input_context` 是多轮到分批之间的显式输入契约
- `batch_inputs` / batch metadata 是 workflow_detail / script_detail 的显式分批契约
- `cicd_retry_result` 是 CI/CD 唯一重试决策对象
- `report_contract` 是当前报告章节契约的显式定义
- `report_artifacts` 是 Markdown / HTML / JSON 的共同章节真相源
- `section_assignment_result` 是 section/workflow 归属的显式真相源
- `merged_response` 仅允许作为展示、调试、导出文本，不得再作为主决策输入
- 分批执行禁止依赖隐式 LLM 会话上下文，必须依赖显式 state / artifacts
- empty-script 必须建模为合法空态，而不是缺章节或隐式异常
- `validation_result` 应表示最终结构化产物校验结果，不应与阶段契约检查混用

**禁止**：
- ❌ 从 `merged_response` 反向提取结构化事实作为主链路
- ❌ 仅依赖 prompt 文件名作为 workflow/script 批次的主判断依据
- ❌ 让 reporter / reviewer 各自从 Markdown 独立重算 section/workflow 归属作为主逻辑
- ❌ 直接从 batch 本地阶段分组推导最终报告阶段归属
- ❌ 在未冻结 report_contract 的情况下随意改动报告章节顺序或标题
- ❌ 让 Markdown / HTML 各自独立推断事实，绕过 `report_artifacts`
- ❌ 使用 `cicd_analysis.status=failed` 代替统一 retry 语义
- ❌ 让 batch 继承未声明的 previous messages / conversation history
- ❌ 在 LangGraph 之外实现 CI/CD 正式业务编排

**补充说明**：
- `architecture_diagram` 是 Markdown 架构图章节的展示真相源
- `architecture_json` 是 HTML / 结构化消费真相源
- 当前 `safe_run` / Studio 子图展开的父级边界问题仍属待收口的专项架构问题，不应再继续扩大 direct graph.invoke 的使用范围

### 6. 错误处理

**层次**：
1. Agent内部：捕获并记录，返回带errors的state
2. Core层：路由到error_handler
3. CLI层：显示友好错误信息

**格式**：
```python
errors = state.get("errors", [])
errors.append(f"{agent_name}: {error_type}: {message}")
return {**state, "errors": errors}
```

**中断支持**：
```python
from evaluator.core.interrupt import interrupt_controller, InterruptException

try:
    interrupt_controller.check()
except InterruptException:
    raise  # 向上传播
```

### 7. 配置管理

**优先级**：系统环境变量 > .env文件 > 默认值

**命名**：
- `EVAL_*`：业务配置（如`EVAL_MAX_RETRIES`）
- `OPENAI_*`：LLM配置
- `LANGCHAIN_*`：LangChain配置

**使用**：
```python
from evaluator.config import config
value = config.some_field
```

## 架构概览

```
CLI → Core (LangGraph) → Agents → Skills/Storage
```

**分层职责**：
- **Core**：协调、路由（无业务逻辑）
- **Agents**：功能实现（单一职责）
- **Skills**：可复用工具（纯函数）
- **Storage**：数据持久化（简单CRUD）

详细架构见 [ARCHITECTURE.md](./ARCHITECTURE.md)

## Agent列表（30个）

### 核心（7个）
- InputAgent, LoaderAgent, IntentParserAgent
- CICDAgent, ReviewerAgent, ReporterAgent, CompareAgent

### 编排（3个）
- OrchestratorAgent, IntelligencePipeline, CICDOrchestrator

### 智能（4个）
- ToolSelectionAgent（未启用，保留用于未来扩展）
- StorageAgent, ReflectionAgent, RecommendationAgent

**ToolSelectionAgent说明**：
- 状态：未启用
- 原因：核心功能编排使用静态模板，避免动态选择的不确定性
- 未来：用于附加功能（自定义流程、插件系统）

### CICD子Agent（9个）
- DataExtractionAgent, AnalysisPlanningAgent, LLMInvocationAgent
- ResultMergingAgent, QualityCheckAgent, RetryHandlingAgent
- StageOrganizationAgent, ReportGenerationAgent, SummaryGenerationAgent

### 修复（1个）
- ReportFixAgent

### 处理（11个）
- ListHandlerAgent, InfoHandlerAgent, DeleteHandlerAgent, HelpHandlerAgent
- InsightsHandlerAgent, RecommendHandlerAgent, SimilarHandlerAgent
- AnalyzersHandlerAgent, VersionHandlerAgent, ClearHandlerAgent, QuitHandlerAgent

### 验证（2个）
- ErrorHandlerAgent, StateValidationAgent

## LangSmith Trace统一要求

**所有Agent必须支持trace**，确保执行过程可追踪、可调试。

### 基本原则

- ✅ 所有Agent通过`safe_run()`统一trace入口
- ✅ `run()`方法不添加`@traceable()`装饰器（避免双重trace）
- ✅ 使用扩展版metadata（19个字段）提供完整上下文
- ❌ 禁止在`run()`方法添加`@traceable()`
- ❌ 禁止直接调用`run()`而不通过`safe_run()`
- ❌ 禁止使用ThreadPoolExecutor（无法关联trace）

### Metadata标准

**扩展版Metadata（所有Agent自动包含）：**
- 基础信息：agent_name, agent_category, project信息
- 执行上下文：intent, current_step, completed_steps_count
- CI/CD信息：workflow_count, actions_count, strategy
- 重试信息：retry_mode, retry_count, retry_issues_count
- 错误和警告：has_errors, error_count, has_warnings, warning_count
- 存储信息：storage_dir, has_storage_version

**详细版Metadata（调试模式）：**
设置`EVAL_TRACE_DEBUG=true`时，额外包含：inputs, outputs, dependencies, state_keys

### 并发执行

**必须使用统一并发工具：**
```python
from evaluator.utils import parallel_execute
tasks = [lambda: task1(), lambda: task2()]
results = parallel_execute(tasks, max_concurrent=4)
```

### 验证清单

开发新Agent时，确认：
- [ ] Agent继承BaseAgent
- [ ] run()方法没有@traceable()装饰器
- [ ] 通过safe_run()调用
- [ ] 在LangSmith中能看到完整trace链路

### 常见错误和教训

**错误1：直接调用run()而不是safe_run()**

❌ **错误示例：**
```python
# main_graph.py中的节点
def _create_node(agent):
    def node(state):
        return agent.run(state)  # ❌ 直接调用run()
    return node
```

✅ **正确示例：**
```python
def _create_node(agent):
    def node(state):
        return agent.safe_run(state)  # ✅ 通过safe_run()调用
    return node
```

**影响：**
- ❌ 没有trace节点
- ❌ 没有metadata收集
- ❌ 没有输入验证
- ❌ 没有错误处理

**教训：**
1. **所有Agent调用必须通过safe_run()**
   - main_graph节点：使用safe_run()
   - orchestrator内部：使用safe_run()
   - 任何地方调用Agent：使用safe_run()

2. **修改base_agent.py时必须检查所有调用点**
   ```bash
   # 搜索所有agent.run()调用
   grep -r "\.run(" src/evaluator --include="*.py"
   
   # 确认都改为.safe_run()
   ```

3. **测试必须验证trace**
   - 不能只测试功能
   - 必须启用LangSmith验证trace结构
   - 必须检查所有Agent都有trace节点

4. **修改时的完整流程：**
   - Step 1: 修改base_agent.py
   - Step 2: 搜索所有调用点（`grep "\.run("`）
   - Step 3: 逐个检查并修改为safe_run()
   - Step 4: 运行测试
   - Step 5: 启用LangSmith验证trace
   - Step 6: Git提交

**历史案例：**
- 问题：Trace增强后，main_graph.py等文件仍使用run()
- 原因：只修改了base_agent.py，未检查所有调用点
- 影响：8个Agent没有trace，metadata收集失效
- 修复：将所有agent.run()改为agent.safe_run()
- 文件：main_graph.py (4处), cicd_agent.py (1处), intelligence_pipeline.py (3处)

**详细说明见** [ARCHITECTURE.md - Trace设计](./ARCHITECTURE.md)

## 开发流程

### 添加新Agent

1. **检查是否可复用**：搜索现有Agent，确认无相似实现
2. **创建文件**：在 `agents/` 目录创建文件，继承BaseAgent
3. **实现方法**：实现 `describe()` 和 `run()` 方法
4. **导出Agent**：在 `agents/__init__.py` 导出
5. **添加节点**：在 `core/graphs/` 添加节点和路由
6. **更新文档**：更新本文档Agent列表和ARCHITECTURE.md

### 添加新功能

1. **检查是否可扩展**：确认现有功能无法满足需求
2. **确定实现层次**：
   - 协调逻辑 → Core层
   - 业务逻辑 → Agent层
   - 工具函数 → Skills层
   - 数据存储 → Storage层
3. **遵从架构原则**：不破坏分层、单一入口等原则
4. **更新文档**：同步更新相关文档

### 修改现有代码

1. **分析影响范围**：确认修改影响的Agent和流程
2. **检查约束破坏**：确认不破坏现有架构约束
3. **确保向后兼容**：不破坏现有接口和功能
4. **更新测试和文档**：同步更新测试和文档

## 开发工具

```bash
# 代码检查
ruff check src/

# 格式化
ruff format src/

# 测试
pytest tests/

# 类型检查
mypy src/
```

## 参考文档

- [CLAUDE.md](./CLAUDE.md) - Claude Code 快速指南（自动加载）
- [ARCHITECTURE.md](./ARCHITECTURE.md) - 详细架构设计
- [README.md](./README.md) - 使用说明
- [CHANGELOG.md](./CHANGELOG.md) - 更新日志
