# Open-Source Evaluator

基于 Multi-Agent 的开源项目 CI/CD 架构评估工具。

## 功能特性

- **CI/CD 架构分析**：
  - **深度分析**：GitHub Actions（架构图、最佳实践、安全检测、性能优化）
  - **配置提取**：GitLab CI、CircleCI、Azure Pipelines、Jenkins 等 10+ 平台
- **智能报告生成**：生成 Markdown 和交互式 HTML 报告，包含架构图、阶段分析、脚本索引等
- **项目对比**：使用 LLM 对多个项目的 CI/CD 架构进行智能对比分析
- **持久化存储**：支持项目版本管理和历史记录
- **交互式 CLI**：友好的命令行界面，输入 `/` 显示命令列表
- **可扩展架构**：基于 LangGraph 的 Agent 编排框架，便于扩展

## 架构

```
CLI / Web UI / API
         ↓
    Core Library (协调层)
         ↓
┌──────────────────┬──────────────────┐
│   LangGraph      │   StorageManager │
│ (复杂工作流)      │   (简单 CRUD)    │
└──────────────────┴──────────────────┘
         ↓
    Agents (具体功能实现)
```

### 目录结构

```
src/evaluator/
├── core/              # Core Library（协调层）
│   ├── analyze.py     # analyze_project() → LangGraph
│   ├── compare.py     # compare_projects() → LangGraph
│   ├── project.py     # list/get/delete → StorageManager
│   └── types.py       # 数据类型定义
├── agents/            # Agents（功能实现）
│   ├── cicd_agent.py       # CI/CD 分析
│   ├── compare_agent.py    # 对比分析
│   ├── reporter_agent.py   # 报告生成
│   └── ...
├── graph.py           # LangGraph 工作流
├── cli/                # CLI 前端
│   └── app.py
├── llm/               # LLM 客户端
│   └── client.py
└── skills/            # 技能模块
    └── ci_analyzer/   # CI 数据提取器

src/storage/           # 存储层
└── manager.py         # StorageManager

data/                  # 数据目录
├── projects/          # 项目分析结果
└── comparisons/       # 对比结果
```

**详细架构说明**：见 [ARCHITECTURE.md](./ARCHITECTURE.md)

**开发指南**：见 [AGENTS.md](./AGENTS.md)

## 安装

### 环境要求

- Python >= 3.10

### 从源码安装

```bash
# 克隆项目
git clone <repository-url>
cd evaluationagent

# 安装依赖
pip install -e .

# 或安装开发依赖
pip install -e ".[dev]"
```

## 配置

### 配置文件

在项目根目录创建 `.env` 文件：

```bash
cp .env.example .env
```

### 环境变量说明

#### LLM 配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `OPENAI_API_KEY` | LLM API Key（必需） | - |
| `OPENAI_BASE_URL` | API 地址（支持 OpenAI 兼容 API） | https://api.openai.com/v1 |
| `DEFAULT_MODEL` | 默认模型 | gpt-4o-mini |

#### 数据存储配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `EVAL_DATA_DIR` | 数据存储目录 | 用户目录（Windows: `%APPDATA%/eval-agent/data`，Linux/Mac: `~/.eval-agent/data`） |

#### 重试配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `EVAL_MAX_RETRIES` | 业务逻辑最大重试次数 | 3 |
| `EVAL_LLM_MAX_RETRIES` | LLM 调用最大重试次数 | 5 |
| `EVAL_LLM_RETRY_DELAY` | LLM 重试基础延迟（秒），实际延迟 = base_delay × attempt | 1.0 |

#### 并发配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `EVAL_MAX_WORKERS` | 后台任务线程数 | 1 |
| `EVAL_LLM_WORKERS` | Review 并发数 | 4 |
| `EVAL_LLM_CONCURRENT` | LLM 并发调用数 | 4 |

#### 超时配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `EVAL_GIT_TIMEOUT` | Git 克隆超时（秒） | 300 |
| `EVAL_LLM_REQUEST_TIMEOUT` | LLM HTTP 请求超时（秒） | 300 |
| `EVAL_LLM_TIMEOUT` | LLM 调用超时（秒） | 600 |

#### LLM 输出配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `EVAL_LLM_MAX_TOKENS` | LLM 最大输出 token | 131072 |

#### 报告配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `EVAL_MAX_SECTION_LENGTH` | 报告最大章节长度 | 3000 |
| `EVAL_MAX_WORKFLOWS_SINGLE` | 单次 prompt 最大工作流数 | 10 |
| `EVAL_MAX_WORKFLOWS_BATCH` | 每批工作流数 | 10 |

#### UI 配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `USE_RICH` | 使用 Rich 终端美化 | true |

#### LangSmith 追踪配置（可选）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `LANGCHAIN_TRACING_V2` | 启用 LangSmith 追踪 | false |
| `LANGSMITH_API_KEY` | LangSmith API Key（从 https://smith.langchain.com 获取） | - |
| `LANGSMITH_PROJECT` | LangSmith 项目名称 | eval-agent |

### 配置优先级

配置按以下优先级加载（高优先级覆盖低优先级）：

1. **系统环境变量**（最高优先级）
2. **.env 文件**
3. **默认值**（最低优先级）

### 打包后配置查找顺序

打包成二进制后，`.env` 文件按以下优先级查找：

1. `EVALUATOR_ENV_FILE` 环境变量指定的自定义路径
2. **运行命令的当前目录** `.env`
3. **二进制同目录** `.env`
4. `~/.evaluator/.env`（用户主目录）

### 配置示例

**最小配置**（仅必需项）：
```env
OPENAI_API_KEY=your-api-key-here
```

**完整配置**（所有可选项）：
```env
# LLM 配置
OPENAI_API_KEY=your-api-key-here
OPENAI_BASE_URL=https://api.openai.com/v1
DEFAULT_MODEL=gpt-4o-mini

# 数据存储配置
EVAL_DATA_DIR=/path/to/data

# 重试配置
EVAL_MAX_RETRIES=3
EVAL_LLM_MAX_RETRIES=5
EVAL_LLM_RETRY_DELAY=1.0

# 并发配置
EVAL_MAX_WORKERS=1
EVAL_LLM_WORKERS=4
EVAL_LLM_CONCURRENT=4

# 超时配置
EVAL_GIT_TIMEOUT=300
EVAL_LLM_REQUEST_TIMEOUT=300
EVAL_LLM_TIMEOUT=600

# LLM 输出配置
EVAL_LLM_MAX_TOKENS=131072

# 报告配置
EVAL_MAX_SECTION_LENGTH=3000
EVAL_MAX_WORKFLOWS_SINGLE=10
EVAL_MAX_WORKFLOWS_BATCH=10

# UI 配置
USE_RICH=true

# LangSmith 追踪（可选）
LANGCHAIN_TRACING_V2=false
LANGSMITH_API_KEY=your-langsmith-key
LANGSMITH_PROJECT=eval-agent
```

## 使用

### 运行 CLI

启动后进入交互式界面，输入 `/` 可查看所有可用命令。命令必须以 `/` 开头。

```bash
eval-agent
```

或直接运行 Python：

```bash
python -m evaluator.cli.app
```

### 命令

#### /analyze - 分析项目

分析本地项目的 CI/CD 架构。

```bash
/analyze ./my-project
```

#### /compare - 对比项目

对比两个已保存项目的 CI/CD 架构。

```bash
/compare project-a project-b
```

#### /list - 列出项目

查看已保存的所有项目。

```bash
/list
```

#### /show - 显示详情

查看特定项目的详细信息。

```bash
/show my-project
/show my-project --version v1_20260319_184336
```

#### /delete - 删除项目

删除已保存的项目。

```bash
/delete my-project
/delete my-project --version v1_20260319_184336
```

#### /analyzers - 列出分析器

查看可用的分析器。

```bash
/analyzers
```

#### /help - 帮助

查看帮助信息。

```bash
/help
/help analyze
/help compare
```

#### /clear - 清除屏幕

```bash
/clear
```

#### /quit, /exit - 退出

```bash
/quit
```

## 输出文件

### 项目分析结果

```
data/projects/{name}/{version}/
├── metadata.json           # 项目元数据
├── ci_data.json            # CI 原始数据（工作流、脚本、外部系统等）
├── llm_response.md         # LLM 原始响应
├── CI_ARCHITECTURE.md      # Markdown 分析报告
├── report.html             # 交互式 HTML 报告
├── architecture.json       # 架构图数据（用于可视化）
├── analysis_summary.json   # 分析摘要
└── prompts/               # 发送给 LLM 的提示词
```

### 对比结果

```
data/comparisons/{id}/
├── metadata.json        # 对比元数据
├── compare.md           # Markdown 报告
└── compare.html         # HTML 报告
```

## 开发

### 代码风格

使用 Ruff 进行代码检查和格式化：

```bash
# 检查
ruff check src/

# 格式化
ruff format src/
```

### 测试

```bash
pytest tests/
```

## 打包（可选）

默认安装后，`pip install -e .` 会自动生成 `eval-agent` 命令（需要 Python 环境）。

如需打包成**独立二进制**（无需 Python 环境），可使用 PyInstaller：

```bash
pip install pyinstaller

# 打包 Windows 可执行文件
pyinstaller eval-agent.exe.spec
```

打包后的文件位于 `dist/eval-agent/eval-agent.exe`。

### 独立二进制注意事项

1. 打包后确保 `.env` 文件位于正确位置
2. Windows 下运行 `dist/eval-agent/eval-agent.exe`
3. Windows Git Bash 环境下需要使用 `winpty` 运行：
   ```bash
   winpty dist/eval-agent/eval-agent.exe
   ```
4. 可设置 `EVALUATOR_ENV_FILE` 环境变量指定配置文件路径

## License

Apache License 2.0. See [LICENSE](./LICENSE) for details.
