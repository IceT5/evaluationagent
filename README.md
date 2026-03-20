# Open-Source Evaluator

基于 Multi-Agent 的开源项目 CI/CD 架构评估工具。

## 功能特性

- **CI/CD 架构分析**：自动提取并分析 GitHub Actions、GitLab CI 等工作流配置
- **项目对比**：使用 LLM 对多个项目的 CI/CD 架构进行智能对比分析
- **持久化存储**：支持项目版本管理和历史记录
- **交互式 CLI**：友好的命令行界面，支持命令补全
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

编辑 `.env`：

```env
# OpenAI API (支持 OpenAI 兼容 API)
OPENAI_API_KEY=your-api-key-here
OPENAI_BASE_URL=https://api.openai.com/v1

# 分析设置
DEFAULT_MODEL=gpt-4o-mini
MAX_TOKENS=4096

# UI 设置
USE_RICH=true
```

### 环境变量说明

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `OPENAI_API_KEY` | LLM API Key | - |
| `OPENAI_BASE_URL` | API 地址 | https://api.openai.com/v1 |
| `DEFAULT_MODEL` | 默认模型 | gpt-4o-mini |
| `MAX_TOKENS` | 最大 token 数 | 4096 |
| `USE_RICH` | 使用 Rich 终端美化 | true |
| `EVALUATOR_ENV_FILE` | 自定义 .env 路径 | - |

### 打包后配置

打包成二进制后，`.env` 文件按以下优先级查找：

1. `EVALUATOR_ENV_FILE` 环境变量指定的自定义路径
2. **运行命令的当前目录** `.env`
3. **二进制同目录** `.env`
4. `~/.evaluator/.env`

## 使用

### 运行 CLI

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
├── metadata.json        # 元数据
├── ci_data.json         # CI 原始数据
├── report.md            # Markdown 报告
├── report.html          # HTML 报告
└── architecture.json    # 架构图数据
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

# Windows
pyinstaller --onefile --name eval-agent.exe src\evaluator\main.py

# macOS/Linux
pyinstaller --onefile --name eval-agent src/evaluator/main.py
```

### 独立二进制注意事项

1. 打包后确保 `.env` 文件位于正确位置
2. Windows 下运行 `eval-agent.exe`
3. 可设置 `EVALUATOR_ENV_FILE` 环境变量指定配置文件路径

## License

Apache2.0
