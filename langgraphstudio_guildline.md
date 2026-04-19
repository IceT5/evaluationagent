## LangGraph Studio 安装与使用指南

### 前置条件

| 项目 | 你的状态 | 要求 |
|---|---|---|
| Python | 3.13 ✅ | ≥ 3.11 |
| langgraph | 1.1.2 ✅ | 已安装 |
| langgraph-sdk | 0.3.11 ✅ | 已安装 |
| langgraph-cli | ❌ 未安装 | 需安装 |
| LangSmith API Key | 已配置 ✅ | 必需 |
| `langgraph.json` | 已创建 ✅ | 必需 |
| `src/evaluator/graph.py` | 已创建 ✅ | 必需 |

### 第 1 步：安装 LangGraph CLI

```bash
pip install -U "langgraph-cli[inmem]"
```

`[inmem]` 是必须的——安装内存版 Agent Server，无需 Docker。

验证：

```bash
langgraph --version
```

### 第 2 步：确认配置文件就绪

以下两个文件已创建，无需额外操作：

**`langgraph.json`**（项目根目录）：
```json
{
  "dependencies": ["."],
  "graphs": {
    "evaluator": "./src/evaluator/graph.py:graph"
  },
  "env": ".env"
}
```

**`.env`** 中的关键配置：
```env
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_pt_...
LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com
LANGSMITH_PROJECT=evaluation
```

### 第 3 步：启动 Agent Server + Studio

在项目根目录 `F:\code\evaluationagent\` 执行：

```bash
langgraph dev
```

首次启动会安装依赖（可能需要 1-2 分钟）。成功后输出：

```
╦  ┌─┐┌┐┌┌─┐╔═╗┬─┐┌─┐┌─┐┬ ┬
║  ├─┤││││ ┬║ ╦├┬┘├─┤├─┘├─┤
╩═╝┴ ┴┘└┘└─┘╚═╝┴└─┴ ┴┴  ┴ ┴

Ready!
- API: http://localhost:2024
- Docs: http://localhost:2024/docs
- LangGraph Studio Web UI: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024
```

### 第 4 步：打开 Studio

**因为你的 `LANGSMITH_ENDPOINT` 是 EU 端点**，Studio URL 需要对应：

```
https://eu.smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024
```

浏览器打开这个 URL，你会看到：
- **Graph 模式**：21 个节点的流程图，条件边用虚线标注
- **Chat 模式**：简化对话界面（需要 `messages` 字段，你的项目可能不支持）

### 第 5 步：从 CLI 执行，Studio 实时可视化

打开**第二个终端**，正常使用 CLI：

```bash
cd F:\code\evaluationagent
eval-agent
/analyze ./my-project
```

CLI 会自动检测 `langgraph dev` 在运行，通过 SDK 提交 run 到 Agent Server。Studio 实时显示：
- 节点逐步高亮执行
- 每个节点的输入/输出 state
- 条件分支走向
- LLM 调用的 prompt/response/token

### 常用操作

| 操作 | 命令/URL |
|---|---|
| 启动 Studio | `langgraph dev` |
| 不自动打开浏览器 | `langgraph dev --no-browser` |
| 指定端口 | `langgraph dev --port 3000` |
| 禁用热重载 | `langgraph dev --no-reload` |
| Studio UI（EU） | `https://eu.smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024` |
| Studio UI（US） | `https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024` |
| Agent Server API | `http://localhost:2024/docs` |

### 不启动 Studio 时

直接用 CLI 即可，行为与改动前完全一致——`_try_invoke_via_server()` 检测到 Server 不可用，自动 fallback 到 `graph.invoke()`，零开销。

### 故障排查

| 问题 | 原因 | 解决 |
|---|---|---|
| `langgraph dev` 报错 `Python < 3.11` | Python 版本不足 | 升级 Python（你的是 3.13，不会有此问题） |
| `langgraph dev` 报错 `No module named 'langgraph_cli'` | 未安装 `[inmem]` | `pip install "langgraph-cli[inmem]"` |
| Studio 打开后空白 | `LANGSMITH_API_KEY` 无效 | 检查 `.env` 中的 key |
| Studio 连接失败 | URL 用了 US 但 endpoint 是 EU | 用 `https://eu.smith.langchain.com/studio/...` |
| CLI 没走 SDK | Server 未启动或连接超时 | 确认 `langgraph dev` 在运行 |
| `langgraph dev` 依赖安装慢 | 首次需要安装项目依赖 | 等待完成，后续启动会快 |

---