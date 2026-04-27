# Eval-Agent - Claude Code 指南

> 完整开发规范见 [AGENTS.md](./AGENTS.md)，详细架构见 [ARCHITECTURE.md](./ARCHITECTURE.md)

---

## 项目简介

基于 LangGraph + LangChain 的多 Agent CI/CD 架构评估工具。用户通过交互式 CLI 分析开源项目的 CI/CD 配置，生成 Markdown + HTML 报告，并提供智能建议。

**技术栈**：Python 3.10+、LangGraph、LangChain、OpenAI 兼容 API、Pydantic v2、Rich

**入口**：`eval-agent` 命令 → `src/evaluator/cli/app.py` → LangGraph (`src/evaluator/core/graphs/main_graph.py`)

---

## 核心约束（必须遵守）

### 架构约束

- 所有执行必须通过 LangGraph，禁止绕过
- 所有 Agent 必须继承 `BaseAgent`，通过 `safe_run()` 调用，禁止直接调用 `run()`
- CLI 层不处理业务逻辑，只负责输入/输出
- 图定义只允许在 `src/evaluator/core/graphs/` 下，当前只有 `main_graph.py`

### 并发约束

```python
# ✅ 必须用统一工具
from evaluator.utils import parallel_execute
results = parallel_execute([lambda: task1(), lambda: task2()], max_concurrent=4)

# ❌ 禁止直接使用
ThreadPoolExecutor(...)
RunnableParallel(...)
```

### 状态约束

- 所有字段在 `src/evaluator/state.py` 中定义，新增字段必须同步更新 `EvaluatorState`
- Agent 返回必须是 state 超集：`return {**state, "new_field": value}`，不能删除字段
- `cicd_assembled_data` 是 CI/CD 唯一结构化真相源，`merged_response` 仅用于展示/调试
- `cicd_retry_result` 是唯一重试决策对象

### 禁止事项速查

| 禁止 | 原因 |
|------|------|
| `agent.run(state)` | 必须用 `agent.safe_run(state)` |
| `ThreadPoolExecutor` | 无法关联 LangSmith trace |
| 绕过 LangGraph 调用 Agent | 破坏单一入口原则 |
| 从 `merged_response` 反向提取结构化事实 | 应消费 `cicd_assembled_data` |
| 在 `report_contract` 未冻结时改动报告章节 | 破坏报告契约 |
| 让 batch 继承隐式 LLM 会话上下文 | 必须通过显式 state 字段传递 |

---

## 关键文件速查

| 文件 | 作用 |
|------|------|
| `src/evaluator/state.py` | 统一状态定义（EvaluatorState） |
| `src/evaluator/config.py` | 全局配置（从环境变量读取） |
| `src/evaluator/agents/base_agent.py` | Agent 基类，定义 `safe_run()` |
| `src/evaluator/core/graphs/main_graph.py` | 主工作流图 |
| `src/evaluator/core/routes.py` | 条件路由函数 |
| `src/evaluator/utils/concurrency.py` | 统一并发工具 `parallel_execute` |
| `src/storage/manager.py` | 存储管理器 |

---

## Agent 开发模板

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
        value = state["input_field"]
        result = self._process(value)
        return {**state, "output_field": result}
```

新增 Agent 后需要：在 `agents/__init__.py` 导出 → 在 `core/graphs/main_graph.py` 添加节点 → 更新 `AGENTS.md` Agent 列表。

---

## 错误处理规范

```python
# Agent 内部捕获并记录，不抛出
errors = state.get("errors", [])
errors.append(f"MyAgent: ErrorType: 描述")
return {**state, "errors": errors}

# 中断支持
from evaluator.core.interrupt import interrupt_controller, InterruptException
interrupt_controller.check()  # 在耗时操作前调用
```

---

## 配置命名规范

- `EVAL_*`：业务配置（如 `EVAL_MAX_RETRIES`）
- `OPENAI_*`：LLM 配置
- `LANGCHAIN_*`：LangChain/LangSmith 配置

---

## 提交规范

每次代码修改完成后，必须执行本地 git 提交，不得遗漏。
