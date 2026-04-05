# Eval-Agent 开发指南

> AI编程工具请先阅读本文档，遵从所有开发要求

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
- 使用 `RunnableParallel` 实现并发（自动关联trace）
- 使用分批执行 + RunnableParallel 限制并发数

**禁止**：
- ❌ 使用 ThreadPoolExecutor（无法关联trace）
- ❌ 无法追踪的并发方式

**示例**：
```python
# 正确：分批执行 + RunnableParallel
max_concurrent = config.max_concurrent_llm_calls
for batch_start in range(0, len(tasks), max_concurrent):
    batch = tasks[batch_start:batch_start + max_concurrent]
    parallel = RunnableParallel(**create_runnables(batch))
    results.extend(parallel.invoke({}))
```

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

## Agent列表（28个）

### 核心（7个）
- InputAgent, LoaderAgent, IntentParserAgent
- CICDAgent, ReviewerAgent, ReporterAgent, CompareAgent

### 编排（3个）
- OrchestratorAgent, IntelligencePipeline, CICDOrchestrator

### 智能（4个）
- ToolSelectionAgent, StorageAgent
- ReflectionAgent, RecommendationAgent

### CICD子Agent（9个）
- DataExtractionAgent, AnalysisPlanningAgent, LLMInvocationAgent
- ResultMergingAgent, QualityCheckAgent, RetryHandlingAgent
- StageOrganizationAgent, ReportGenerationAgent, SummaryGenerationAgent

### 修复（1个）
- ReportFixAgent

### 处理（4个）
- ListHandlerAgent, InfoHandlerAgent
- DeleteHandlerAgent, HelpHandlerAgent

### 验证（2个）
- ErrorHandlerAgent, StateValidationAgent

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

- [ARCHITECTURE.md](./ARCHITECTURE.md) - 详细架构设计
- [README.md](./README.md) - 使用说明
- [CHANGELOG.md](./CHANGELOG.md) - 更新日志
