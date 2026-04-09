# IntentParserAgent

## 概述

意图解析 Agent，负责将用户的自然语言输入转换为结构化的命令和参数。

## 状态

**已实现** - 集成到 CLI

## 职责

1. 解析用户自然语言输入
2. 识别用户意图（analyze/compare/list 等）
3. 提取命令参数
4. 处理模糊输入，请求澄清
5. 支持传统命令格式（以 `/` 开头）

## 意图类型

| 意图 | 描述 | 示例 |
|------|------|------|
| `analyze` | 分析项目 CI/CD | "分析 cccl 项目" |
| `compare` | 对比两个项目 | "对比 cccl 和 TensorRT-LLM" |
| `list` | 列出项目 | "有哪些已分析的项目" |
| `info` | 查看项目详情 | "cccl 项目信息" |
| `help` | 获取帮助 | "怎么使用" |
| `delete` | 删除项目 | "删除 cccl 项目" |
| `unknown` | 无法识别 | "..." |

## 输入

| 参数 | 类型 | 必需 | 描述 |
|------|------|------|------|
| `user_input` | `str` | 是 | 用户输入文本 |
| `known_projects` | `list[str]` | 是 | 已知项目列表 |

## 输出

```python
ParsedIntent(
    intent=Intent.ANALYZE,  # Intent 枚举
    params={"project": "cccl"},  # 提取的参数
    confidence=0.95,  # 置信度 0.0-1.0
    needs_clarification=False,  # 是否需要澄清
    clarification_question=None,  # 澄清问题
    raw_input="分析 cccl 项目",  # 原始输入
)
```

## 使用示例

```python
from evaluator.agents import IntentParserAgent

agent = IntentParserAgent(llm=llm_client)
known_projects = ["cccl", "TensorRT-LLM", "PyTorch"]

# 解析自然语言
result = agent.run(
    "帮我分析一下 cccl 项目",
    known_projects
)

print(result.intent)  # Intent.ANALYZE
print(result.params)  # {"project": "cccl"}
```

## CLI 集成

IntentParserAgent 已集成到 `evaluator.cli.app`，提供自然语言支持：

```bash
$ python -m evaluator.cli.app
eval-agent> 分析 cccl 项目
eval-agent> 对比 cccl 和 PyTorch
eval-agent> 有哪些已分析的项目
eval-agent> 看看 TensorRT-LLM 的详情
```

### 回退机制

1. **有 LLM**：使用 LLM 解析自然语言
2. **无 LLM**：使用规则匹配（_simple_parse）
3. **LLM 失败**：自动回退到规则匹配

## 实现状态

- [x] IntentParserAgent 类
- [x] 自然语言解析（LLM + 规则回退）
- [x] 传统命令解析（/analyze, /compare 等）
- [x] 上下文管理（通过 known_projects）
- [x] 澄清机制
- [x] CLI 集成
- [ ] 多轮对话上下文（待实现）

## 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                        CLI Input                             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    IntentParserAgent                        │
├─────────────────────────────────────────────────────────────┤
│  1. 如果以 / 开头 → _parse_traditional()                    │
│  2. 如果有 LLM → _parse_natural() → LLM                     │
│  3. 否则 → _simple_parse() 规则匹配                         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     ParsedIntent                            │
│  - intent: Intent enum                                      │
│  - params: Dict[str, Any]                                   │
│  - confidence: float                                        │
│  - needs_clarification: bool                                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   CommandHandler                            │
│  - route_intent() → 分发到具体处理函数                        │
└─────────────────────────────────────────────────────────────┘
```
