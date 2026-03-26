# LoaderAgent

## 概述

项目加载 Agent，负责克隆远程仓库或初始化本地项目存储。

## 职责

1. 初始化存储目录结构
2. 创建版本目录
3. 克隆远程仓库（如果需要）
4. 返回项目路径供后续 Agent 使用

## 输入

| 参数 | 类型 | 必需 | 描述 |
|------|------|------|------|
| `project_url` | `str` | 是* | 项目 URL（URL 输入时） |
| `project_name` | `str` | 是 | 项目名称 |
| `project_path` | `str` | 是* | 项目路径（本地输入时） |
| `should_download` | `bool` | 是 | 是否需要下载 |
| `storage_version_id` | `str` | 否 | 指定版本 ID |
| `storage_dir` | `str` | 否 | 存储目录路径 |

*注：URL 输入时需要 `project_url`，本地输入时需要 `project_path`

## 输出

```python
{
    "project_path": str,                    # 项目本地路径
    "clone_status": "success|failed|skipped",  # 克隆状态
    "clone_error": Optional[str],          # 克隆错误信息
    "storage_version_id": str,             # 版本 ID
    "storage_dir": str,                   # 存储目录
    "current_step": "loader",             # 当前步骤标识
    "errors": list[str],                 # 错误列表
}
```

## 依赖

| 依赖 | 说明 |
|------|------|
| `GitOperations` | Git 操作工具 |
| `StorageManager` | 存储管理 |

## 配置

| 配置项 | 默认值 | 描述 |
|--------|--------|------|
| `DEFAULT_DOWNLOAD_DIR` | `./downloaded_projects` | 默认下载目录 |

## 使用示例

```python
from evaluator.agents import LoaderAgent

agent = LoaderAgent()

# URL 输入场景
state = {
    "project_url": "https://github.com/owner/repo",
    "project_name": "repo",
    "should_download": True,
}
result = agent.run(state)

# 本地路径场景
state = {
    "project_path": "/path/to/project",
    "project_name": "my-project",
    "should_download": False,
}
result = agent.run(state)
```

## 存储结构

```
data/projects/
├── project-name/
│   ├── metadata.json          # 项目元数据
│   ├── latest -> v1_xxx     # 最新版本符号链接
│   ├── v1_xxx/
│   │   ├── metadata.json    # 版本元数据
│   │   ├── ci_data.json    # CI/CD 数据
│   │   ├── CI_ARCHITECTURE.md  # 分析报告
│   │   └── ...
```

## LangSmith 追踪

```python
@traceable(name="LoaderAgent", run_type="agent")
def run(self, state):
    # LangSmith 自动追踪
    ...
```
