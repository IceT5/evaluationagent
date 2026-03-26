# InputAgent

## 概述

输入处理 Agent，负责解析用户输入并判断输入类型（URL 或本地路径）。

## 职责

1. 获取用户输入（项目路径或 URL）
2. 判断输入类型（URL vs 本地路径）
3. 解析 URL 获取项目信息
4. 更新状态供后续 Agent 使用

## 输入

| 参数 | 类型 | 必需 | 描述 |
|------|------|------|------|
| `user_input` | `str` | 是 | 用户输入（URL 或本地路径） |

## 输出

```python
{
    "user_input": str,                    # 原始用户输入
    "project_url": Optional[str],        # 解析后的 URL（URL 输入时）
    "project_path": Optional[str],        # 本地路径（本地输入时）
    "project_name": str,                 # 项目名称
    "should_download": bool,              # 是否需要下载（URL 时为 True）
    "current_step": "input",            # 当前步骤标识
    "errors": list[str],                 # 错误列表
}
```

## 依赖

| 依赖 | 说明 |
|------|------|
| `UrlParser` | URL 解析工具 |

## 使用示例

```python
from evaluator.agents import InputAgent

# 方式 1：交互式输入
agent = InputAgent()
result = agent.run({"current_step": "init"})

# 方式 2：直接传入输入
agent = InputAgent(user_input="https://github.com/owner/repo")
result = agent.run({"current_step": "init"})

# 方式 3：本地路径
agent = InputAgent(user_input="F:/projects/my-project")
result = agent.run({"current_step": "init"})
```

## 支持的输入格式

| 类型 | 示例 |
|------|------|
| GitHub URL | `https://github.com/owner/repo` |
| GitLab URL | `https://gitlab.com/owner/repo` |
| 本地路径 | `F:/projects/my-project` |
| 带引号路径 | `"F:/projects/my-project"` 或 `'F:/projects/my-project'` |

## LangSmith 追踪

```python
@traceable(name="InputAgent", run_type="agent")
def run(self, state):
    # LangSmith 自动追踪
    ...
```
