#!/usr/bin/env python3
"""
CI Architecture Diagram Generator - Generate architecture diagrams from LLM analysis

This module generates LLM prompts and processes LLM responses.
ALL classification and organization logic is handled by LLM for maximum flexibility.
"""

import json
from pathlib import Path
from typing import Dict, List, Any


def generate_llm_prompt(raw_data: Dict) -> str:
    """Generate a comprehensive prompt for LLM to analyze CI architecture.
    
    The LLM is responsible for:
    - Determining category structure and order
    - Analyzing workflow execution flow
    - Identifying call relationships
    - Organizing content by logical software engineering stages
    - Creating readable architecture documentation
    """
    
    prompt = """# CI/CD 架构分析请求

**重要：本文档必须使用中文输出！所有内容、标题、描述、分析都必须使用中文！**

你是一位资深DevOps工程师，请深入分析项目的CI/CD架构，并生成一份结构清晰的架构文档。

## 你的任务

### 1. 分析并确定CI/CD流程阶段

请根据项目的实际情况，分析并确定CI/CD的各个阶段。不要使用预设的分类，而是根据项目的工作流内容来定义合理的阶段划分。

考虑：
- 工作流的触发条件（on字段）
- 工作流之间的调用关系（uses字段）
- Job之间的依赖关系（needs字段）
- 每个工作流/Job的实际目的

### 2. 按照执行逻辑顺序组织

请按照CI/CD的实际执行顺序来组织文档内容：
- 首先是触发入口
- 然后是前置检查和准备
- 接着是构建、测试等核心流程
- 最后是收尾和发布

### 3. 展示完整的调用链

对于每个工作流，请展示：
- 它被哪些工作流调用（或被什么事件触发）
- 它调用了哪些其他工作流
- 它使用了哪些Action
- 它执行了哪些脚本

### 4. 提供关键配置信息

对于重要的Job，请列出：
- 运行环境（runs-on）
- 关键配置参数
- Matrix配置内容
- 输入输出参数

### 5. 【必须】完整列出所有Job

**严格要求**：必须完整列出每个工作流中的所有Job，不能省略任何Job！
- 必须包含所有Job的名称
- 必须描述每个Job的目的
- 不能使用"..."或其他省略符号
- 即使Job数量很多，也必须全部列出

### 6. 深度分析与隐式关联发现

除了显式调用关系，请分析以下隐式关联：

1. **外部系统集成**：
   - 识别工作流调用的外部系统（如 blossom-action、自定义 Action）
   - 关联项目中的外部 CI 配置（Jenkins Pipeline、其他 CI 脚本）
   - 推断外部系统调用与本地脚本的关联

2. **脚本调用链**：
   - 分析工作流执行的脚本
   - 追踪脚本调用的其他脚本
   - 构建完整的脚本依赖链

3. **多 CI 系统协作**：
   - 分析项目是否使用多套 CI 系统
   - 识别不同 CI 系统之间的协作关系
   - 在调用关系树中展示跨系统调用

在附录的调用关系树中，请包含：
- 显式调用（Action、脚本）
- 外部系统调用（标注为 [外部系统]）
- 推断的隐式关联（标注为 [推断]）

---

## 项目数据

"""
    
    # Add repository info
    prompt += f"### 仓库名称\n{raw_data.get('repo_name', 'Unknown')}\n\n"
    
    # Add CI directories
    ci_dirs = raw_data.get("ci_directories", [])
    if ci_dirs:
        prompt += "### CI相关目录\n```\n"
        for d in ci_dirs:
            prompt += f"{d}\n"
        prompt += "```\n\n"
    
    # Add scripts by directory
    scripts_by_dir = raw_data.get("scripts_by_directory", {})
    if scripts_by_dir:
        prompt += "### 脚本目录结构\n```\n"
        for dir_path, scripts in scripts_by_dir.items():
            prompt += f"{dir_path}/\n"
            for s in scripts[:10]:
                prompt += f"  - {s}\n"
            if len(scripts) > 10:
                prompt += f"  ... (+{len(scripts)-10} more)\n"
        prompt += "```\n\n"
    
# Add Jenkins pipelines
    jenkins_pipelines = raw_data.get("jenkins_pipelines", [])
    if jenkins_pipelines:
        prompt += "### Jenkins Pipeline 文件\n```\n"
        for jp in jenkins_pipelines[:20]:
            jp_path = jp.get('path', jp.get('name', str(jp))) if isinstance(jp, dict) else str(jp)
            prompt += f"- {jp_path}\n"
        if len(jenkins_pipelines) > 20:
            prompt += f"... 共 {len(jenkins_pipelines)} 个\n"
        prompt += "```\n\n"
    
    # Add external CI related scripts
    external_ci_scripts = raw_data.get("external_ci_scripts", [])
    if external_ci_scripts:
        prompt += "### 外部 CI 相关脚本\n```\n"
        for script in external_ci_scripts[:30]:
            script_path = script.get('path', script.get('name', str(script))) if isinstance(script, dict) else str(script)
            prompt += f"- {script_path}\n"
        if len(external_ci_scripts) > 30:
            prompt += f"... 共 {len(external_ci_scripts)} 个\n"
        prompt += "```\n\n"
    
    # Add other CI configs
    other_ci_configs = raw_data.get("other_ci_configs", {})
    if other_ci_configs:
        prompt += "### 其他 CI 配置\n```\n"
        for config_type, configs in other_ci_configs.items():
            if configs and isinstance(configs, list):
                for cfg in configs[:5]:
                    prompt += f"- {cfg}\n"
            elif configs:
                prompt += f"- {config_type}: {configs}\n"
        prompt += "```\n\n"
    
    # Add workflow relationships first
    relationships = raw_data.get("relationships", {})
    workflow_calls = relationships.get("workflow_calls", {})
    if workflow_calls:
        prompt += "### 工作流调用关系\n```\n"
        prompt += "# 格式: 被调用工作流 <- 调用者\n"
        for callee, callers in workflow_calls.items():
            caller_list = ", ".join(callers[:5])
            if len(callers) > 5:
                caller_list += f" (+{len(callers)-5})"
            prompt += f"{callee}\n  <- {caller_list}\n"
        prompt += "```\n\n"
    
    # Add actions usage
    action_usages = relationships.get("action_usages", {})
    if action_usages:
        prompt += "### Action使用统计\n```\n"
        for action, users in list(action_usages.items())[:20]:
            prompt += f"- {action}: 被 {len(users)} 处使用\n"
        prompt += "```\n\n"
    
    # Add detailed workflow information
    workflows = raw_data.get("workflows", {})
    if workflows:
        prompt += f"### 工作流完整信息（共 {len(workflows)} 个）\n\n"
        for wf_name, wf in workflows.items():
            prompt += f"---\n\n#### {wf_name}\n\n"
            
            # Basic info
            prompt += f"**名称**: {wf.get('name', 'N/A')}\n\n"
            prompt += f"**路径**: `{wf.get('path', 'N/A')}`\n\n"
            
            # Triggers
            triggers = wf.get("triggers", [])
            trigger_details = wf.get("trigger_details", {})
            prompt += f"**触发条件**: {', '.join(triggers)}\n"
            if trigger_details:
                prompt += "```yaml\n"
                for trigger, details in list(trigger_details.items())[:3]:
                    if isinstance(details, dict):
                        prompt += f"# {trigger}:\n"
                        for k, v in list(details.items())[:3]:
                            prompt += f"#   {k}: {v}\n"
                prompt += "```\n"
            prompt += "\n"
            
            # Jobs
            jobs = wf.get("jobs", {})
            if jobs:
                prompt += f"**Jobs** ({len(jobs)}个):\n\n"
                for job_name, job in jobs.items():
                    prompt += f"##### `{job_name}`\n\n"
                    
                    # Display name
                    display_name = job.get("display_name", "")
                    if display_name and display_name != job_name:
                        prompt += f"显示名称: {display_name}\n\n"
                    
                    # Dependencies
                    needs = job.get("needs", [])
                    if needs:
                        prompt += f"**依赖**: {', '.join(needs)}\n\n"
                    
                    # Reusable workflow
                    uses = job.get("uses", "")
                    if uses:
                        prompt += f"**调用工作流**: `{uses}`\n\n"
                        # with params
                        with_params = job.get("with_params", {})
                        if with_params:
                            prompt += "**传入参数**:\n```yaml\n"
                            for k, v in list(with_params.items())[:8]:
                                v_str = str(v)
                                if len(v_str) > 100:
                                    v_str = v_str[:100] + "..."
                                prompt += f"{k}: {v_str}\n"
                            prompt += "```\n\n"
                    
                    # Runner
                    runs_on = job.get("runs_on", "")
                    if runs_on:
                        prompt += f"**运行环境**: `{runs_on}`\n\n"
                    
                    # Condition
                    if_condition = job.get("if_condition", "")
                    if if_condition:
                        prompt += f"**条件**: `{if_condition[:100]}`\n\n"
                    
                    # Matrix - 完整展示所有展开的配置
                    matrix = job.get("matrix")
                    matrix_configs = job.get("matrix_configs", [])
                    
                    if matrix:
                        prompt += f"**Matrix配置**:\n"
                        
                        # 显示原始matrix定义
                        if isinstance(matrix, dict):
                            prompt += "```\n原始定义:\n"
                            for k, v in matrix.items():
                                if k not in ["include", "exclude"]:
                                    if isinstance(v, list):
                                        prompt += f"  {k}: {v}\n"
                                    else:
                                        prompt += f"  {k}: {str(v)[:100]}\n"
                            if matrix.get("include"):
                                prompt += f"  include: {len(matrix['include'])}个配置\n"
                            if matrix.get("exclude"):
                                prompt += f"  exclude: {len(matrix['exclude'])}个排除项\n"
                            prompt += "```\n\n"
                        
                        # 完整展示所有展开后的配置（不限制数量）
                        if matrix_configs:
                            prompt += f"**展开后的Job变体** ({len(matrix_configs)}个，必须全部列出):\n```\n"
                            for idx, cfg in enumerate(matrix_configs, 1):
                                if isinstance(cfg, dict):
                                    items = list(cfg.items())
                                    cfg_str = ", ".join(f"{k}={v}" for k, v in items)
                                    prompt += f"  {idx}. {cfg_str}\n"
                            prompt += "```\n\n"
                        else:
                            # 如果没有展开的配置，说明可能是表达式
                            prompt += f"**注意**: Matrix可能使用表达式动态生成，无法静态展开\n\n"
                    
                    # Steps
                    steps = job.get("steps", [])
                    if steps:
                        prompt += f"**执行步骤** ({len(steps)}步):\n```\n"
                        for i, step in enumerate(steps[:15], 1):
                            step_name = step.get("name", "") or step.get("uses", "") or step.get("id", f"step-{i}")
                            if step.get("uses"):
                                prompt += f"{i}. [{step_name}] -> uses: {step.get('uses', '')}\n"
                            elif step.get("run"):
                                run_preview = step.get("run", "")[:80].replace("\n", " ")
                                prompt += f"{i}. [{step_name}] -> run: {run_preview}...\n"
                            else:
                                prompt += f"{i}. [{step_name}]\n"
                        if len(steps) > 15:
                            prompt += f"   ... (+{len(steps)-15} more)\n"
                        prompt += "```\n\n"
                    
                    # Calls
                    calls_workflows = job.get("calls_workflows", [])
                    calls_actions = job.get("calls_actions", [])
                    if calls_workflows:
                        prompt += f"**调用工作流**: {', '.join(calls_workflows)}\n\n"
                    if calls_actions:
                        prompt += f"**使用Action**: {', '.join(calls_actions[:10])}\n\n"
                    
                    prompt += "---\n\n"
    
    # Add actions
    actions = raw_data.get("actions", [])
    if actions:
        prompt += "### Composite Actions\n\n"
        for action in actions:
            prompt += f"#### `{action.get('name')}`\n\n"
            prompt += f"**路径**: `{action.get('path')}`\n\n"
            desc = action.get("description", "")
            if desc:
                prompt += f"**描述**: {desc}\n\n"
            
            inputs = action.get("inputs", {})
            if inputs:
                prompt += f"**输入参数**:\n```\n"
                for name, inp in inputs.items():
                    req = "required" if inp.get("required") else "optional"
                    default = inp.get("default", "")
                    prompt += f"  {name} ({req}): {inp.get('description', '')[:50]}"
                    if default:
                        prompt += f" [default: {str(default)[:30]}]"
                    prompt += "\n"
                prompt += "```\n\n"
            
            used_by = action.get("used_by", [])
            if used_by:
                prompt += f"**被使用于**: {len(used_by)} 处\n\n"
    
    # Add scripts
    scripts = raw_data.get("scripts", [])
    if scripts:
        prompt += "### CI脚本\n\n"
        for script in scripts:
            prompt += f"#### `{script.get('name')}`\n\n"
            prompt += f"**路径**: `{script.get('path')}`\n\n"
            prompt += f"**类型**: {script.get('type')}\n\n"
            
            # 函数（全部传递）
            funcs = script.get("functions", [])
            if funcs:
                prompt += f"**函数**: {', '.join(funcs)}\n\n"
            
            # 引入（全部传递）
            imports = script.get("imports", [])
            if imports:
                prompt += f"**引入**: {', '.join(imports)}\n\n"
            
            # 被调用
            called_by = script.get("called_by", [])
            if called_by:
                prompt += f"**被调用**: {len(called_by)} 次\n\n"
            
            # 调用的脚本（全部传递）
            calls_scripts = script.get("calls_scripts", [])
            if calls_scripts:
                prompt += f"**调用的脚本**: {', '.join(calls_scripts)}\n\n"
            
            script_type = script.get("type", "")
            content = script.get("content", "")
            
            if script_type in [".yaml", ".yml"]:
                if content:
                    if len(content) > 50 * 1024:
                        content_to_show = content[:10000]
                        prompt += f"**内容** (前 10000 字符，文件共 {len(content)} 字符):\n```\n{content_to_show}\n```\n\n"
                    else:
                        prompt += f"**内容**:\n```\n{content}\n```\n\n"
            elif script_type not in [".sh", ".py", ".ps1", ".bat", ".groovy"]:
                if content:
                    content_preview = content[:2000]
                    prompt += f"**内容预览**:\n```\n{content_preview}\n```\n\n"
    
    # Add pre-commit configurations
    pre_commit_configs = raw_data.get("pre_commit_configs", [])
    if pre_commit_configs:
        prompt += "### Pre-commit 配置\n\n"
        prompt += "**说明**: Pre-commit 是一个本地代码质量检查框架，在git commit前自动运行检查。虽然不通过GitHub Actions触发，但属于CI/CD整体能力的一部分。\n\n"
        
        for config in pre_commit_configs:
            prompt += f"#### 配置文件: `{config.get('path')}`\n\n"
            
            # CI settings
            ci_settings = config.get("ci", {})
            if ci_settings:
                prompt += f"**CI设置**:\n```\n"
                for k, v in ci_settings.items():
                    prompt += f"  {k}: {v}\n"
                prompt += "```\n\n"
            
            # Default stages
            default_stages = config.get("default_stages", [])
            if default_stages:
                prompt += f"**默认阶段**: {', '.join(default_stages)}\n\n"
            
            # External repo hooks
            repos = config.get("repos", [])
            if repos:
                prompt += f"**外部Hook** ({len(repos)}个):\n```\n"
                # Group by repo for better readability
                repos_by_source = {}
                for hook in repos:
                    repo = hook.get("repo", "unknown")
                    if repo not in repos_by_source:
                        repos_by_source[repo] = []
                    repos_by_source[repo].append(hook)
                
                for repo_url, hooks in repos_by_source.items():
                    prompt += f"\n# 来源: {repo_url}\n"
                    for hook in hooks:
                        hook_id = hook.get("id", "")
                        desc = hook.get("description", "")[:50] if hook.get("description") else ""
                        prompt += f"  - {hook_id}"
                        if desc:
                            prompt += f": {desc}"
                        prompt += "\n"
                prompt += "```\n\n"
            
            # Local hooks
            local_hooks = config.get("local_hooks", [])
            if local_hooks:
                prompt += f"**本地Hook** ({len(local_hooks)}个):\n```\n"
                for hook in local_hooks:
                    hook_id = hook.get("id", "")
                    desc = hook.get("description", "")[:50] if hook.get("description") else ""
                    prompt += f"  - {hook_id}"
                    if desc:
                        prompt += f": {desc}"
                    prompt += "\n"
                prompt += "```\n\n"
    
    # Expected output format
    prompt += """
---

## 输出格式要求

**语言要求：本文档必须使用中文输出！所有标题、描述、分析内容都必须是中文！**

请输出两部分内容：
1. **Markdown 文档** - 完整的架构分析文档
2. **JSON 数据** - 架构图的结构化数据（用于图形化展示）

---

## 第一部分：Markdown 文档

### 文档结构要求

1. **项目概述** - 简要描述项目类型和CI/CD整体架构

2. **CI/CD整体架构图** - **必须**在文档开头部分使用ASCII diagram形式展示整体架构：
   - 展示完整的CI/CD流程阶段
   - 使用框线(┌─┐│└┘)和箭头(→▶▼▲)表示流程方向
   - 标注每个阶段的关键操作（如触发条件、具体工作流名称）
   - 清晰展示阶段之间的依赖关系
   - **重要**：每个节点要包含详细信息，如触发条件列表、工作流名称等
   
   **触发入口层特殊要求**：
   - 触发入口层的节点必须是**触发条件类型**，不是工作流名称
     - 正确示例：`push`、`pull_request`、`workflow_dispatch`、`schedule`、`issue_comment`
     - 错误示例：`ci-workflow-pull-request.yml`（这是工作流名称，不是触发条件）
   - 每个触发条件节点要标注触发的工作流数量
     - 示例：`push (3)` 表示有 3 个工作流使用 push 触发
     - 示例：`workflow_dispatch (15)` 表示有 15 个工作流可手动触发
   - 触发入口层不展示具体的工作流名称，只展示触发条件类型和数量
   
   示例格式：
   ```
   ┌─────────────────────────────────────────────────────────────────────────────┐
   │                           CI/CD 整体架构                                     │
   ├─────────────────────────────────────────────────────────────────────────────┤
   │                                                                             │
   │   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐              │
   │   │   触发入口    │────▶│   代码检查    │────▶│   外部CI     │              │
   │   │              │     │              │     │              │              │
   │   │ • push       │     │ • pr-check   │     │ • blossom-ci │              │
   │   │ • PR         │     │ • precommit  │     │ • l0-test    │              │
   │   │ • schedule   │     │ • model-reg  │     │              │              │
   │   │ • dispatch   │     │              │     │              │              │
   │   └──────────────┘     └──────────────┘     └──────────────┘              │
   │          │                    │                    │                      │
   │          │                    │                    ▼                      │
   │          │                    │            ┌──────────────┐              │
   │          │                    └───────────▶│   测试结果    │              │
   │          │                                 │              │              │
   │          ▼                                 └──────────────┘              │
   │   ┌──────────────┐                                                        │
   │   │   自动化管理  │                                                        │
   │   │              │                                                        │
   │   │ • auto-assign│                                                        │
   │   │ • label_issue│                                                        │
   │   │ • bot-cmd    │                                                        │
   │   └──────────────┘                                                        │
   │                                                                             │
   └─────────────────────────────────────────────────────────────────────────────┘
   ```

3. **按阶段组织的内容** - 每个阶段包含：
   - 阶段说明（这个阶段做什么）
   - 触发条件分类
   - 相关工作流列表
   - 工作流详情（触发条件、**完整Job列表**、关键配置）
   - 调用的脚本和Action
   - 与其他阶段的关系

4. **脚本和Action索引** - 按目录或用途组织
   - 脚本路径、用途、被哪些工作流调用
   - Action 路径、输入参数、使用位置

5. **Pre-commit配置**（如存在）
   - 外部Hook列表（来源仓库、hook id、用途）
   - 本地Hook列表
   - 默认阶段配置

6. **关键发现和建议**
   - 架构特点总结
   - 改进建议

7. **附录：工作流调用关系图**（**必须包含**）
   
   **必须**在附录中输出完整的工作流调用关系图，使用树状结构展示：
   
   ```
   项目CI/CD调用关系树
   ├── 触发入口
   │   ├── push事件
   │   │   └── build.yml
   │   ├── pull_request事件
   │   │   ├── pr-check.yml
   │   │   └── precommit-check.yml
   │   ├── schedule事件
   │   │   └── auto-close.yml
   │   └── workflow_dispatch事件
   │       └── blossom-ci.yml
   │
   ├── pr-check.yml (PR触发)
   │   ├── Jobs:
   │   │   └── check-pr-title → check-pr-body
   │   └── 调用:
   │       └── .github/scripts/pr_checklist_check.py
   │
    ├── blossom-ci.yml (手动/评论触发)
    │   ├── Jobs:
    │   │   └── Authorization → Vulnerability-scan → Job-trigger
    │   └── 调用:
    │       ├── NVIDIA/blossom-action@main [外部系统]
    │       ├── 外部 Jenkins 系统 [推断]
    │       └── jenkins/scripts/*.groovy [推断关联]
    │
    └── ...
   ```
   
   树状结构要求：
   - 根节点显示项目名称
   - 第一层：触发入口类型（事件类型）
   - 第二层：工作流文件
   - 第三层：Job依赖链和调用的其他工作流/Action/脚本
   - 使用 `→` 表示Job依赖关系（needs）
   - 使用缩进表示层级关系

### Job列表要求

**必须完整列出所有Job！** 对于每个工作流：
- 列出所有Job的名称（不能省略任何一个）
- 每个Job都要有简要描述
- 标注Job之间的依赖关系（needs）
- 如果有Matrix配置，**必须完整展开并列出所有变体**

### Matrix Job完整展示要求

对于使用Matrix策略的Job，**必须完整展开并列出所有Matrix变体**：
- 不能只说"有N个变体"或使用省略号
- 必须逐个列出每个Matrix组合生成的Job实例
- 即使有几十个变体，也必须全部列出
- 每个变体需要说明其具体配置参数

示例：
```
#### build (Matrix Job)
Matrix配置展开后生成 12 个Job实例：
1. build (ubuntu-latest, python-3.9) - Linux + Python 3.9
2. build (ubuntu-latest, python-3.10) - Linux + Python 3.10
3. build (ubuntu-latest, python-3.11) - Linux + Python 3.11
... (必须列出所有变体)
```

---

## 第二部分：JSON 架构图数据

**必须**在 Markdown 文档末尾输出架构图的结构化 JSON 数据，格式如下：

```json
<!-- ARCHITECTURE_JSON
{
  "layers": [
    {
      "id": "layer-trigger",
      "name": "触发条件",
      "nodes": [
        {
          "id": "push-event",
          "label": "push 事件",
          "description": "代码推送到分支",
          "detail_section": "阶段一：触发与入口"
        },
        {
          "id": "pr-event",
          "label": "PR 事件",
          "description": "pull_request opened, edited, synchronize",
          "detail_section": "阶段一：触发与入口"
        }
      ]
    },
    {
      "id": "layer-check",
      "name": "代码检查层",
      "nodes": [
        {
          "id": "pr-check",
          "label": "pr-check.yml",
          "description": "PR 标题和清单检查",
          "detail_section": "阶段二：代码检查"
        },
        {
          "id": "precommit-check",
          "label": "precommit-check.yml",
          "description": "Pre-commit 代码格式检查",
          "detail_section": "阶段二：代码检查"
        }
      ]
    }
  ],
  "connections": [
    {"source": "push-event", "target": "pr-check"},
    {"source": "pr-event", "target": "pr-check"},
    {"source": "pr-event", "target": "precommit-check"}
  ]
}
ARCHITECTURE_JSON -->
```

**JSON 数据要求**：
1. `layers`：按 CI/CD 执行顺序排列的层级
2. `nodes`：每个节点包含 id、label、description、detail_section
3. `description`：包含关键信息（如触发条件、工作流名称等）
4. `detail_section`：对应 Markdown 文档中的章节标题（用于点击跳转）
5. `connections`：节点之间的连接关系
6. 使用 `<!-- ARCHITECTURE_JSON ... ARCHITECTURE_JSON -->` 包裹，方便提取

---

**重要提醒**:
1. **必须使用中文输出所有内容**
2. **必须完整列出每个工作流的所有Job，不能省略**
3. **必须输出 JSON 架构图数据**
4. **必须包含附录：工作流调用关系图**
5. **必须输出评估评分 JSON（见第三部分）**
6. 不要硬编码分类，根据实际内容分析
7. 展示调用关系和依赖关系
8. 提供足够的细节但不冗余
9. 使用清晰的层级结构

---

## 第三部分：评估评分（必须输出）

**必须**在 Markdown 文档末尾、JSON 架构图数据之后，输出评估评分 JSON：

```json
<!-- ANALYSIS_SUMMARY
{
  "scores": {
    "architecture_design": 8,
    "best_practices": 7,
    "security": 6,
    "maintainability": 7,
    "scalability": 6
  },
  "score_rationale": {
    "architecture_design": "工作流按阶段清晰划分，依赖关系明确...",
    "best_practices": "使用了缓存和矩阵构建，但缺少复用策略...",
    "security": "缺少安全扫描步骤，密钥管理需加强...",
    "maintainability": "脚本复用较好，但文档不够完整...",
    "scalability": "支持多平台构建，但环境配置分散..."
  },
  "findings": {
    "strengths": [
      "使用了矩阵构建，支持多平台测试",
      "缓存配置完善，构建速度快"
    ],
    "weaknesses": [
      "缺少 SAST/DAST 安全扫描",
      "部署流程缺少审批机制"
    ]
  },
  "recommendations": [
    {"priority": "high", "content": "添加 SAST 安全扫描（如 CodeQL）"},
    {"priority": "high", "content": "实现部署审批流程"},
    {"priority": "medium", "content": "使用 Reusable Workflow 减少重复配置"},
    {"priority": "low", "content": "完善工作流文档注释"}
  ]
}
ANALYSIS_SUMMARY -->
```

**评分维度说明**：
| 维度 | 评分标准 | 考虑因素 |
|------|----------|----------|
| architecture_design | 工作流组织、阶段划分、依赖管理 | 1. 工作流是否按功能合理划分 2. 阶段之间依赖关系是否清晰 3. 是否避免不必要的跨阶段依赖 |
| best_practices | 缓存使用、矩阵构建、复用策略、错误处理 | 1. 是否使用缓存加速构建 2. 是否使用矩阵策略测试多平台 3. 是否有复用策略（Reusable Workflow/Action）4. 错误处理是否完善 |
| security | 权限控制、密钥管理、安全扫描、审计日志 | 1. 权限是否遵循最小原则 2. 密钥是否通过 secrets 管理 3. 是否有安全扫描（SAST/DAST/依赖扫描）4. 敏感操作是否有审计 |
| maintainability | 代码复用、文档完整性、命名规范、测试覆盖 | 1. 是否有独立的脚本库 2. 工作流是否有注释和文档 3. 命名是否规范清晰 4. 是否覆盖主要场景 |
| scalability | 环境支持、部署策略、配置管理、扩展能力 | 1. 支持多少种运行环境 2. 部署策略是否灵活 3. 配置是否集中管理 4. 新增工作流是否容易 |

**评分标准（1-10分）**：
- 9-10: 优秀，业界最佳实践，在大多数开源项目中属于Top 10%
- 7-8: 良好，大部分实践到位，有少量改进空间
- 5-6: 一般，基本实践到位，但有明显短板
- 3-4: 较差，存在较多问题，需要系统性改进
- 1-2: 很差，架构设计有严重问题，建议重构

**评分要求**：
1. 必须基于实际分析结果评分，不能套用模板
2. 每个维度的评分必须有对应的 `score_rationale` 说明
3. `findings` 必须从实际分析中提炼，不能凭空编造
4. `recommendations` 必须与 `findings` 对应，有优先级区分
5. high 优先级建议最多 2 条，medium 最多 3 条，low 适量

**检查清单**：
- [ ] scores 包含全部 5 个维度
- [ ] score_rationale 对每个维度都有说明
- [ ] findings.strengths 和 findings.weaknesses 都至少 1 条
- [ ] recommendations 有明确的 priority 区分
- [ ] JSON 格式正确，可被解析
"""

    return prompt


def parse_llm_response(llm_response: str) -> str:
    """Parse LLM response - just return the content as-is.
    
    The LLM is expected to produce a complete Markdown document.
    We don't need to do any processing - just save it.
    """
    # Extract content - if wrapped in code blocks, extract it
    content = llm_response.strip()
    
    # Remove markdown code block wrapper if present
    if content.startswith("```markdown"):
        content = content[len("```markdown"):]
    elif content.startswith("```"):
        content = content[3:]
    
    if content.endswith("```"):
        content = content[:-3]
    
    return content.strip()


def generate_architecture_diagram(
    raw_data: Dict,
    llm_response: str,
    output_file: str
) -> str:
    """Generate architecture diagram from LLM's analysis.
    
    This function simply processes and saves the LLM's output.
    All the intelligence is in the LLM prompt and response.
    """
    
    # Parse the LLM response (just clean up any code block wrappers)
    content = parse_llm_response(llm_response)
    
    # Write to file
    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Architecture diagram saved to: {output_file}")
    
    return content


def generate_split_prompts(raw_data: Dict, output_dir: str, max_workflows_per_batch: int = 10) -> List[str]:
    """Generate multiple prompt files for large projects.
    
    Args:
        raw_data: Extracted CI/CD data
        output_dir: Directory to save prompt files
        max_workflows_per_batch: Maximum workflows per batch
    
    Returns:
        List of generated prompt file paths
    """
    import os
    
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    workflows = raw_data.get("workflows", {})
    workflow_names = list(workflows.keys())
    
    # Generate global context (included in all batches)
    global_context = _generate_global_context(raw_data)
    
    # Split workflows into batches
    batches = []
    for i in range(0, len(workflow_names), max_workflows_per_batch):
        batch_names = workflow_names[i:i + max_workflows_per_batch]
        batches.append(batch_names)
    
    generated_files = []
    
    # Generate main prompt (overview)
    main_prompt = _generate_main_prompt(raw_data, global_context)
    main_file = os.path.join(output_dir, "prompt_main.txt")
    with open(main_file, "w", encoding="utf-8") as f:
        f.write(main_prompt)
    generated_files.append(main_file)
    print(f"Generated: {main_file}")
    
    # Generate batch prompts
    for batch_idx, batch_names in enumerate(batches, 1):
        batch_prompt = _generate_batch_prompt(raw_data, global_context, batch_names, batch_idx, len(batches))
        batch_file = os.path.join(output_dir, f"prompt_{batch_idx}.txt")
        with open(batch_file, "w", encoding="utf-8") as f:
            f.write(batch_prompt)
        generated_files.append(batch_file)
        print(f"Generated: {batch_file}")
    
    # Generate merge instructions
    merge_file = os.path.join(output_dir, "README.txt")
    
    if len(batches) == 0:
        batch_info = "无详细批次（项目无工作流）"
    elif len(batches) == 1:
        batch_info = "prompt_1.txt - 详细文档"
    else:
        batch_info = f"prompt_1.txt ~ prompt_{len(batches)}.txt - 详细文档批次"
    
    merge_content = f"""# Prompt文件说明

此项目CI/CD较大，已自动分割为多个prompt文件：

1. prompt_main.txt - 概览文档，包含：
   - 项目基本信息
   - 完整调用关系图
   - 所有工作流简要列表

2. {batch_info}：
   - 每个包含完整调用关系图
   - 当前批次的详细工作流信息
   - 其他批次的简要信息

## 使用方式

### 方式一：并行处理（推荐）
使用多个subagent并行处理各批次：
- Subagent 1: 处理 prompt_main.txt → 生成概览文档
- Subagent 2: 处理 prompt_1.txt → 生成第1批详细分析
- Subagent 3: 处理 prompt_2.txt → 生成第2批详细分析
- ...
最后合并所有结果。

### 方式二：顺序处理
依次处理每个prompt文件，最后合并结果。

## 合并结果

所有subagent完成后，将响应合并为一个文件后执行：
python ci_diagram_generator.py diagram ci_data.json merged_response.md CI_ARCHITECTURE.md
"""
    with open(merge_file, "w", encoding="utf-8") as f:
        f.write(merge_content)
    generated_files.append(merge_file)
    print(f"Generated: {merge_file}")
    
    return generated_files


def generate_multi_round_prompts(raw_data: Dict, output_dir: str, max_workflows_per_batch: int = 10) -> Dict[str, Any]:
    """Generate multi-round prompts for main analysis.
    
    Returns a structure containing:
    - main_rounds: List of round prompts for main analysis
    - main_system_prompt: System prompt for main analysis
    - batch_files: List of batch prompt file paths
    - all_files: List of all prompt file paths
    - prompt_strategy: "multi_round"
    
    Args:
        raw_data: Extracted CI/CD data
        output_dir: Directory to save prompt files
        max_workflows_per_batch: Maximum workflows per batch
    
    Returns:
        Dict containing multi-round prompt data
    """
    import os
    
    os.makedirs(output_dir, exist_ok=True)
    
    workflows = raw_data.get("workflows", {})
    workflow_names = list(workflows.keys())
    
    global_context = _generate_global_context(raw_data)
    
    batches = []
    for i in range(0, len(workflow_names), max_workflows_per_batch):
        batch_names = workflow_names[i:i + max_workflows_per_batch]
        batches.append(batch_names)
    
    generated_files = []
    
    main_system_prompt = _generate_multi_round_system_prompt()
    main_rounds = _generate_multi_round_prompts_content(global_context)
    
    print(f"  [Multi-Round] 生成了 {len(main_rounds)} 个 rounds 用于 main 分析")
    
    for batch_idx, batch_names in enumerate(batches, 1):
        batch_prompt = _generate_batch_prompt(raw_data, global_context, batch_names, batch_idx, len(batches))
        batch_file = os.path.join(output_dir, f"prompt_{batch_idx}.txt")
        with open(batch_file, "w", encoding="utf-8") as f:
            f.write(batch_prompt)
        generated_files.append(batch_file)
        print(f"Generated: {batch_file}")
    
    merge_file = os.path.join(output_dir, "README.txt")
    
    if len(batches) == 0:
        batch_info = "无详细批次（项目无工作流）"
    elif len(batches) == 1:
        batch_info = "prompt_1.txt - 详细文档"
    else:
        batch_info = f"prompt_1.txt ~ prompt_{len(batches)}.txt - 详细文档批次"
    
    merge_content = f"""# Prompt文件说明

此项目CI/CD分析使用多轮对话模式：

## Main 分析（多轮对话）

main 分析使用 10 轮对话：
- Round 0: 建立上下文
- Round 1-2: 基础信息输出
- Round 3-7: 关键发现和建议
- Round 8: 调用关系树
- Round 9: JSON 架构数据

## Batch 分析（并发）

{batch_info}：
- 每个包含完整调用关系图
- 当前批次的详细工作流信息

## 合并结果

所有分析完成后，将响应合并为一个文件后执行：
python ci_diagram_generator.py diagram ci_data.json merged_response.md CI_ARCHITECTURE.md
"""
    with open(merge_file, "w", encoding="utf-8") as f:
        f.write(merge_content)
    generated_files.append(merge_file)
    print(f"Generated: {merge_file}")
    
    return {
        "main_rounds": main_rounds,
        "main_system_prompt": main_system_prompt,
        "batch_files": generated_files[:-1] if generated_files else [],
        "all_files": generated_files,
        "prompt_strategy": "multi_round",
        "global_context": global_context,
    }


def _generate_multi_round_system_prompt() -> str:
    """Generate system prompt for multi-round main analysis."""
    return """你是 CI/CD 架构分析专家，负责分析项目的 CI/CD 架构并生成详细报告。

**重要规则**：
1. 必须使用中文输出
2. 每轮只输出当前要求的章节，不要输出其他内容
3. 等待用户指令后再输出下一章节
4. 输出格式必须严格按照要求
5. 所有分析必须基于提供的项目数据，不要凭空编造"""


def _generate_multi_round_prompts_content(global_context: str) -> List[str]:
    """Generate content for each round of multi-round main analysis.
    
    Args:
        global_context: Global context string to include in Round 0
    
    Returns:
        List of user prompts for each round
    """
    rounds = []
    
    rounds.append(_generate_round_0_context(global_context))
    rounds.append(_generate_round_1_overview())
    rounds.append(_generate_round_2_stage_division())
    rounds.append(_generate_round_3_arch_summary())
    rounds.append(_generate_round_4_strength_patterns())
    rounds.append(_generate_round_5_problems())
    rounds.append(_generate_round_6_recommendations())
    rounds.append(_generate_round_7_call_tree())
    rounds.append(_generate_round_8_json_data())
    rounds.append(_generate_round_9_architecture_diagram())
    
    return rounds


def _generate_round_0_context(global_context: str) -> str:
    """Round 0: 建立上下文"""
    return f"""我需要你分析一个项目的 CI/CD 架构。以下是完整的项目数据：

## 全局信息

{global_context}

---

请确认你已理解以上数据。回复"已理解，请开始分析"即可，不要输出其他内容。"""


def _generate_round_1_overview() -> str:
    """Round 1: 项目概述"""
    return """请输出【项目概述】章节，格式如下：

## 项目概述

本项目是一个 [项目类型]，使用 GitHub Actions 进行 CI/CD 管理。

**CI/CD 整体特点**：
- 工作流总数：X 个
- 主要触发方式：push、PR、schedule 等
- 外部系统集成：xxx
- 核心功能：xxx

**注意**：只输出此章节，不要输出其他内容。"""


def _generate_round_2_stage_division() -> str:
    """Round 2: 阶段划分说明"""
    return """请输出【阶段划分说明】章节，格式如下：

## 阶段划分

| 阶段 | 工作流 | 说明 |
|------|--------|------|
| 阶段一：触发入口 | - | 各类触发条件入口 |
| 阶段二：代码检查 | pr-check, precommit | 代码质量检查 |
| ... | ... | ... |

**典型 CI/CD 阶段参考**（按执行顺序）：

1. **触发入口层**
   - 功能：响应外部事件，调度后续流程
   - 特点：被 push、schedule、workflow_dispatch 等事件触发
   - 作用：作为 CI/CD 流程的入口，调用其他工作流

2. **任务调度层**
   - 功能：分发任务到不同平台/组件
   - 特点：接收主入口调用，按平台/组件分发
   - 作用：协调多平台、多组件的并行构建

3. **构建编译层**
   - 功能：执行核心构建任务
   - 特点：编译代码、打包产物、生成构建产物
   - 作用：产出可部署的构建产物

4. **测试验证层**
   - 功能：运行测试、验证构建结果
   - 特点：单元测试、集成测试、性能测试
   - 作用：确保构建质量

5. **发布部署层**
   - 功能：版本发布、包发布、部署
   - 特点：创建版本标签、发布到仓库、部署到环境
   - 作用：将构建产物发布到生产环境

6. **安全扫描层**
   - 功能：安全合规检查
   - 特点：依赖扫描、漏洞检测、合规审计
   - 作用：确保代码安全

7. **项目自动化层**
   - 功能：PR/Issue 自动处理
   - 特点：状态同步、自动分配、标签管理
   - 作用：减少人工操作

8. **辅助工具层**
   - 功能：开发辅助工具
   - 特点：非核心流程，辅助开发效率
   - 作用：提供开发便利工具

**划分原则**：
1. 根据工作流的**实际功能**划分，而非名称
2. 分析工作流的 jobs、steps、调用关系来判断功能
3. 同一功能领域的工作流归为同一阶段
4. 不是所有项目都包含所有阶段，根据实际情况调整
5. 阶段顺序应反映 CI/CD 执行流程

**注意**：
1. 只输出此章节，不要输出其他内容
2. 确保每个工作流只出现在一个阶段中"""


def _generate_round_9_architecture_diagram() -> str:
    """Round 9: 基于 JSON 数据生成架构图"""
    return """请根据前面输出的 JSON 架构数据，生成【CI/CD 整体架构图】章节。

## CI/CD 整体架构图

**重要**：必须基于 JSON 数据的 `layers` 结构生成架构图！

**要求**：
1. **必须**包含 JSON 中的所有层（layers）
2. 每个层的节点必须与 JSON 中的 `nodes` 对应
3. 使用 ASCII 框线(┌─┐│└┘)和箭头(→▶▼▲)表示流程方向
4. 触发入口层节点是触发条件类型，其他层节点是工作流名称
5. 每个节点要包含关键信息（如 Job 数量、触发条件等）

**格式示例**：
```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CI/CD 整体架构                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────── 触发入口层 ───────────────────┐                       │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐      │                       │
│  │  │ push (3) │  │ schedule │  │workflow_ │      │                       │
│  │  └────┬─────┘  └────┬─────┘  │dispatch  │      │                       │
│  └───────┼─────────────┼────────└────┬─────┘──────┘                       │
│          ▼             ▼             ▼                                     │
│  ┌─────────────────── 主 CI 入口层 ──────────────────┐                     │
│  │  ...                                              │                     │
│  └───────────────────────────────────────────────────┘                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

**只输出此章节，不要输出其他内容。**
"""


def _generate_round_3_arch_summary() -> str:
    """Round 4: 架构评分（JSON 格式）"""
    return """请输出架构评分 JSON。

**输出格式**：必须是纯 JSON，不要添加任何解释。

```json
{
  "scores": {
    "architecture_design": {"score": 8, "rationale": "工作流按阶段清晰划分，依赖关系明确"},
    "best_practices": {"score": 7, "rationale": "使用了缓存和矩阵构建，但缺少复用策略"},
    "security": {"score": 6, "rationale": "缺少安全扫描步骤，密钥管理需加强"},
    "maintainability": {"score": 7, "rationale": "脚本复用较好，但文档不够完整"},
    "scalability": {"score": 6, "rationale": "支持多平台构建，但环境配置分散"}
  }
}
```

**评分标准（1-10分）**：
- 9-10: 优秀，业界最佳实践，在大多数开源项目中属于Top 10%
- 7-8: 良好，大部分实践到位，有少量改进空间
- 5-6: 一般，基本实践到位，但有明显短板
- 3-4: 较差，存在较多问题，需要系统性改进
- 1-2: 很差，架构设计有严重问题，建议重构

**严格要求**：
1. 只输出 JSON，不要输出 "好的"、"以下是" 等文字
2. 不要使用 Markdown 表格
3. 确保 JSON 格式正确（引号、逗号、括号）
4. scores 必须包含全部 5 个维度
5. 每个 score 必须有 score 和 rationale 两个字段

开始输出：
"""


def _generate_round_4_strength_patterns() -> str:
    """Round 5: 优势架构模式（JSON 格式）"""
    return """请输出优势架构模式 JSON。

**输出格式**：必须是纯 JSON，不要添加任何解释。

```json
{
  "strengths": [
    {
      "title": "矩阵构建策略",
      "description": "使用矩阵策略支持多平台并行构建",
      "evidence": "ci-workflow-pull-request.yml 使用 matrix 配置"
    },
    {
      "title": "缓存优化",
      "description": "完善的缓存配置加速构建",
      "evidence": "配置了 pip、ccache 等多种缓存"
    }
  ]
}
```

**要求**：
1. 识别 2-5 个优势模式
2. 每个包含 title、description、evidence 三个字段
3. evidence 应引用具体的工作流或配置
4. 只输出 JSON，不要其他内容

开始输出：
"""


def _generate_round_5_problems() -> str:
    """Round 6: 架构问题（JSON 格式）"""
    return """请输出架构问题 JSON。

**输出格式**：必须是纯 JSON，不要添加任何解释。

```json
{
  "weaknesses": [
    {
      "title": "缺少安全扫描",
      "description": "未配置 SAST/DAST 安全扫描",
      "impact": "可能遗漏安全漏洞，增加安全风险",
      "suggestion": "添加 CodeQL 或 Snyk 扫描"
    }
  ]
}
```

**要求**：
1. 识别 1-5 个问题
2. 每个包含 title、description、impact、suggestion 四个字段
3. impact 说明问题的后果，suggestion 提供改进建议
4. 只输出 JSON，不要其他内容

开始输出：
"""


def _generate_round_6_recommendations() -> str:
    """Round 7: 改进建议（JSON 格式）"""
    return """请输出改进建议 JSON。

**输出格式**：必须是纯 JSON，不要添加任何解释。

```json
{
  "recommendations": [
    {"priority": "high", "content": "添加 SAST 安全扫描", "expected_benefit": "提高代码安全性"},
    {"priority": "medium", "content": "使用 Reusable Workflow", "expected_benefit": "减少重复配置"},
    {"priority": "low", "content": "完善文档注释", "expected_benefit": "提高可维护性"}
  ]
}
```

**要求**：
1. priority 必须是 "high"、"medium" 或 "low"
2. high 最多 2 条，medium 最多 3 条，low 适量
3. content 是建议的具体内容
4. expected_benefit 说明实施后的预期效果
5. 只输出 JSON，不要其他内容

开始输出：
"""


def _generate_round_7_call_tree() -> str:
    """Round 8: 调用关系树"""
    return """请输出【附录 - 工作流调用关系树】章节：

## 附录

### 工作流调用关系树

项目CI/CD调用关系树
├── 触发入口
│   ├── push事件
│   │   └── workflow1.yml
│   ├── pull_request事件
│   │   ├── workflow2.yml
│   │   └── workflow3.yml
│   └── schedule事件
│       └── workflow4.yml
│
├── workflow1.yml (push触发)
│   ├── Jobs:
│   │   └── job1 → job2 → job3
│   └── 调用:
│       └── script1.py
│
└── ...

**要求**：
1. 使用树状结构展示完整的调用关系
2. 包含触发条件、Job 依赖、脚本调用
3. 只输出此章节，不要输出其他内容"""


def _generate_round_8_json_data() -> str:
    """Round 8: JSON 架构图数据"""
    return """请输出【JSON 架构图数据】：

<!-- ARCHITECTURE_JSON
{
  "layers": [
    {
      "id": "layer-1",
      "name": "触发条件",
      "nodes": [
        {
          "id": "node-1-1",
          "label": "push 事件",
          "description": "代码推送到分支触发",
          "detail_section": "阶段一：触发与入口"
        }
      ]
    }
  ],
  "connections": [
    {"source": "node-1-2", "target": "node-2-1"}
  ]
}
ARCHITECTURE_JSON -->

**重要：必须参考前面输出的【阶段划分】表格！**

**阶段一致性要求**：
1. 每个工作流节点的 `detail_section` 必须与阶段划分表格完全一致
2. 同一阶段的工作流节点必须放在同一个 layer 中
3. 不要因为工作流之间的调用关系而改变其阶段归属
4. 阶段划分表格是工作流阶段归属的唯一依据

**格式要求**：
- `layers` 数组包含所有层级
- 每个层必须有 `id`、`name`、`nodes` 三个字段
- `nodes` 数组包含该层的所有节点
- 每个节点必须有 `id`、`label`、`description`、`detail_section` 四个字段
- `connections` 数组包含节点之间的连接，使用 `source` 和 `target` 字段
- `id` 使用英文和连字符，如 `layer-1`、`node-1-1`
- `label` 使用简短的中文名称
- `description` 包含关键信息（触发条件、Job数量等）
- `detail_section` 对应报告中的阶段标题

**节点命名要求**：
1. 工作流节点必须使用**完整的工作流文件名**（包含 .yml 后缀）
   - 正确示例：`workflow-dispatch-two-stage-group-linux.yml`
   - 正确示例：`ci-workflow-pull-request.yml`
   - 错误示例：`two-stage-group-linux`（简短名称）
   - 错误示例：`two-stage-group-linux.yml`（不存在的工作流）
2. 触发类型节点使用触发条件名称（如 `push`、`workflow_dispatch`）
3. 不要使用简短名称或缩写

**层结构要求**：
1. 第一层是触发入口层，节点是触发条件类型
2. 后续层按阶段划分表格的阶段顺序排列
3. 每个工作流只能出现在一个层中，不能重复

**重要**：不要修改格式！不要添加额外字段！只输出 JSON 数据！"""


def _generate_global_context(raw_data: Dict) -> str:
    """Generate global context (included in all batches)."""
    context = "## 全局信息\n\n"
    
    # Repository info
    context += f"### 仓库名称\n{raw_data.get('repo_name', 'Unknown')}\n\n"
    
    # CI directories
    ci_dirs = raw_data.get("ci_directories", [])
    if ci_dirs:
        context += f"### CI相关目录\n{', '.join(ci_dirs)}\n\n"
    
    # Jenkins pipelines
    jenkins_pipelines = raw_data.get("jenkins_pipelines", [])
    if jenkins_pipelines:
        context += f"### Jenkins Pipeline 文件\n共 {len(jenkins_pipelines)} 个\n\n"
    
    # External CI scripts
    external_ci_scripts = raw_data.get("external_ci_scripts", [])
    if external_ci_scripts:
        context += f"### 外部 CI 相关脚本\n共 {len(external_ci_scripts)} 个\n\n"
    
    # Workflow relationships (complete)
    relationships = raw_data.get("relationships", {})
    workflow_calls = relationships.get("workflow_calls", {})
    if workflow_calls:
        context += "### 完整调用关系图\n```\n"
        context += "# 格式: 被调用工作流 <- 调用者\n"
        for callee, callers in workflow_calls.items():
            context += f"{callee}\n  <- {', '.join(callers[:5])}"
            if len(callers) > 5:
                context += f" (+{len(callers)-5})"
            context += "\n"
        context += "```\n\n"
    
    # Action usage summary
    action_usages = relationships.get("action_usages", {})
    if action_usages:
        context += "### Action使用统计\n"
        for action, users in list(action_usages.items())[:10]:
            context += f"- {action}: {len(users)}处使用\n"
        if len(action_usages) > 10:
            context += f"- ... 共{len(action_usages)}个Action\n"
        context += "\n"
    
    # All workflows summary
    workflows = raw_data.get("workflows", {})
    if workflows:
        context += f"### 工作流列表（共{len(workflows)}个）\n"
        for wf_name, wf in workflows.items():
            triggers = wf.get("triggers", [])
            jobs = wf.get("jobs", {})
            context += f"- {wf_name}: {len(jobs)}个Jobs, 触发: {', '.join(triggers[:3])}\n"
        context += "\n"
    
    # Scripts summary
    scripts = raw_data.get("scripts", [])
    if scripts:
        context += f"### CI脚本列表（共{len(scripts)}个）\n"
        scripts_by_dir = {}
        for script in scripts:
            path = script.get("path", "")
            dir_name = str(Path(path).parent) if path else "unknown"
            if dir_name not in scripts_by_dir:
                scripts_by_dir[dir_name] = []
            scripts_by_dir[dir_name].append(script.get("name", "unknown"))
        
        for dir_name, script_names in scripts_by_dir.items():
            context += f"- {dir_name}/: {', '.join(script_names[:5])}"
            if len(script_names) > 5:
                context += f" ... (+{len(script_names)-5})"
            context += "\n"
        if len(scripts) > 50:
            context += f"- ... 共{len(scripts)}个脚本\n"
        context += "\n"
        
        context += "### CI脚本详细内容\n\n"
        context += """**关键配置识别**：
请检查以下配置文件，识别是否为构建矩阵或其他关键 CI 配置文件。判断依据：
- 包含多个构建组合定义
- 定义了系统架构、编译器、运行环境等维度
- 用于驱动 CI 工作流的动态配置

如果识别到关键配置文件，请在"脚本目录索引"章节的 **关键配置** 小节中简要描述其作用和规模。

"""
        for script in scripts:
            script_type = script.get("type", "")
            script_content = script.get("content", "")
            
            if script_type in [".yaml", ".yml"]:
                if script_content:
                    if len(script_content) > 50 * 1024:
                        content_to_show = script_content[:10000]
                        context += f"#### `{script.get('name')}`\n**内容** (前 10000 字符，文件共 {len(script_content)} 字符):\n```\n{content_to_show}\n```\n\n"
                    else:
                        context += f"#### `{script.get('name')}`\n**内容**:\n```\n{script_content}\n```\n\n"
            elif script_type not in [".sh", ".py", ".ps1", ".bat", ".groovy"]:
                if script_content:
                    content_preview = script_content[:2000]
                    context += f"#### `{script.get('name')}`\n**内容预览**:\n```\n{content_preview}\n```\n\n"
    
    return context


def _generate_main_prompt(raw_data: Dict, global_context: str) -> str:
    """Generate main overview prompt - 输出概览、架构图、附录、JSON"""
    prompt = """# CI/CD 架构分析 - 概览文档

**重要：本文档必须使用中文输出！**

你正在分析一个大型项目的CI/CD架构。请生成概览文档。

**注意**：本文档只输出概览内容，详细的工作流分析将由其他批次完成。

---

## 必须输出的内容（按顺序）

### 1. 项目概述（必须）

```
## 项目概述

本项目是一个 [项目类型]，使用 GitHub Actions 进行 CI/CD 管理。

**CI/CD 整体特点**：
- 工作流总数：X 个
- 主要触发方式：push、PR、schedule 等
- 外部系统集成：xxx
- 核心功能：xxx
```

### 2. CI/CD 整体架构图（必须）

使用 ASCII diagram 展示整体架构：
- 展示完整的 CI/CD 流程阶段
- 使用框线(┌─┐│└┘)和箭头(→▶▼▲)表示流程方向
- **每个节点必须包含详细信息**：触发条件、工作流名称、Job 数量等
- 清晰展示阶段之间的依赖关系

示例：
```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CI/CD 整体架构                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐              │
│   │   触发入口    │────▶│   代码检查    │────▶│   外部CI     │              │
│   │              │     │              │     │              │              │
│   │ • push       │     │ • pr-check   │     │ • blossom-ci │              │
│   │ • PR         │     │ • precommit  │     │ • l0-test    │              │
│   │ • schedule   │     │ • model-reg  │     │              │              │
│   └──────────────┘     └──────────────┘     └──────────────┘              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3. 阶段划分说明（必须）

列出所有阶段及其包含的工作流：
```
## 阶段划分

| 阶段 | 工作流 | 说明 |
|------|--------|------|
| 阶段一：触发入口 | - | 各类触发条件入口 |
| 阶段二：代码检查 | pr-check, precommit | 代码质量检查 |
| ... | ... | ... |
```

### 4. 关键发现和建议（必须）

**必须**输出详细的分析报告，包含以下结构：

```
## 关键发现和建议

### 一、架构特点总结

| 维度 | 评估 | 说明 |
|------|------|------|
| 工作流规模 | 大/中/小 | 工作流数量、Job 数量评估 |
| 架构深度 | 深/中/浅 | 层级数量、调用链深度 |
| 矩阵构建 | 支持/不支持 | 是否使用矩阵策略 |
| 可复用性 | 高/中/低 | Reusable Workflows、Composite Actions 使用情况 |
| 可观测性 | 高/中/低 | 日志、状态、错误追踪能力 |

### 二、优势架构模式

#### ✅ 模式一：[模式名称]

[模式描述，包括架构图、优势说明]

#### ✅ 模式二：[模式名称]

[模式描述]

...

### 三、架构问题与反模式

#### ⚠️ 反模式一：[问题名称]

[问题描述，包括影响分析和改进建议]

#### ⚠️ 问题二：[问题名称]

[问题描述]

...

### 四、改进建议

| 优先级 | 建议 | 预期效果 |
|--------|------|----------|
| P0 | [建议1] | [效果] |
| P1 | [建议2] | [效果] |
| P2 | [建议3] | [效果] |

### 五、架构演进建议

[长期演进方向和建议]
```

**分析角度要求**：
1. **工作流设计模式**：串行/并行/矩阵/分发调度等
2. **复用策略**：Reusable Workflows、Composite Actions、模板使用情况
3. **依赖管理**：Caching、依赖预取、版本管理
4. **触发策略**：push/PR/schedule/dispatch 的使用合理性
5. **安全最佳实践**：权限控制、密钥管理、pull_request_target 风险
6. **可维护性**：代码重复、配置集中化、文档完整性
7. **可观测性**：日志、状态追踪、失败通知
8. **扩展性**：新增平台/变体的便捷性

### 5. 附录：工作流调用关系树（必须）

使用树状结构展示完整的调用关系：

```
## 附录

### 工作流调用关系树

项目CI/CD调用关系树
├── 触发入口
│   ├── push事件
│   │   └── workflow1.yml
│   ├── pull_request事件
│   │   ├── workflow2.yml
│   │   └── workflow3.yml
│   └── schedule事件
│       └── workflow4.yml
│
├── workflow1.yml (push触发)
│   ├── Jobs:
│   │   └── job1 → job2 → job3
│   └── 调用:
│       └── script1.py
│
└── ...
```

### 6. JSON 架构图数据（必须）

**必须严格按照以下格式输出**，不要修改结构，不要添加额外字段：

```json
<!-- ARCHITECTURE_JSON
{
  "layers": [
    {
      "id": "layer-1",
      "name": "触发条件",
      "nodes": [
        {
          "id": "node-1-1",
          "label": "push 事件",
          "description": "代码推送到分支触发",
          "detail_section": "阶段一：触发与入口"
        },
        {
          "id": "node-1-2",
          "label": "PR 事件",
          "description": "pull_request 触发",
          "detail_section": "阶段一：触发与入口"
        }
      ]
    },
    {
      "id": "layer-2",
      "name": "代码检查层",
      "nodes": [
        {
          "id": "node-2-1",
          "label": "pr-check.yml",
          "description": "PR基础检查, 2 Jobs",
          "detail_section": "阶段二：代码检查"
        }
      ]
    }
  ],
  "connections": [
    {"source": "node-1-2", "target": "node-2-1"}
  ]
}
ARCHITECTURE_JSON -->
```

**格式要求**：
- `layers` 数组包含所有层级
- 每个层必须有 `id`、`name`、`nodes` 三个字段
- `nodes` 数组包含该层的所有节点
- 每个节点必须有 `id`、`label`、`description`、`detail_section` 四个字段
- `connections` 数组包含节点之间的连接，使用 `source` 和 `target` 字段
- `id` 使用英文和连字符，如 `layer-1`、`node-1-1`
- `label` 使用简短的中文名称
- `description` 包含关键信息（触发条件、Job数量等）
- `detail_section` 对应报告中的阶段标题

**不要修改这个格式！不要添加额外字段！**

---

"""
    
    prompt += global_context
    
    prompt += """
---

**检查清单**（输出前确认）：
- [ ] 项目概述章节已输出
- [ ] ASCII 架构图已输出，包含详细信息
- [ ] 阶段划分表格已输出
- [ ] 关键发现和建议已输出
- [ ] 附录：调用关系树已输出
- [ ] JSON 数据已输出，格式完全符合要求（layers/nodes/connections结构）

**必须使用中文输出！所有章节都必须输出！JSON格式必须严格按要求！**
"""
    
    return prompt


def _generate_batch_prompt(raw_data: Dict, global_context: str, batch_names: List[str], batch_idx: int, total_batches: int) -> str:
    """Generate batch prompt - 让 LLM 根据工作流功能动态决定阶段划分"""
    prompt = f"""# CI/CD 架构分析 - 详细文档（批次 {batch_idx}/{total_batches}）

**重要：本文档必须使用中文输出！完整列出所有Job！**

你正在分析一个大型项目的CI/CD架构。这是第{batch_idx}批次详细分析。

---

## 输出要求

### 1. 阶段划分（动态决定）

**重要**：不要使用预设的阶段划分，请根据本批次工作流的实际功能和触发条件，自行决定合理的阶段划分。

分析原则：
- 根据工作流的触发条件（on字段）归类
- 根据工作流的实际目的归类
- 按照执行顺序组织：触发入口 → 前置检查 → 核心流程 → 收尾处理
- 每个阶段命名要准确反映其功能

### 2. 每个阶段的输出格式

```
## 阶段X：[阶段名称]

### 阶段说明
[这个阶段做什么，为什么需要]

### 触发条件
[该阶段的触发条件分类]

### 工作流详情

#### X.X workflow-name.yml

**目的**: xxx

**触发条件**:
```yaml
触发配置
```

**包含的Job**（共X个）:
| 序号 | Job名称 | 运行环境 | 目的 |
|-----|---------|---------|------|
| 1 | job1 | ubuntu-latest | 描述 |

**依赖关系**: job1 → job2 → job3

**执行步骤详情**:
- Job 1: job1
  - 步骤1: xxx
  - 步骤2: xxx

**使用的Action**: xxx

**调用的脚本**: xxx

**构建矩阵**（可选，仅当工作流使用矩阵配置时输出）:
- 配置文件: [矩阵配置文件名]
- 支持的编译器: [编译器列表]
- 支持的 CUDA 版本: [版本列表]
- 估算构建组合数: [数量]
```

### 3. 脚本和 Action 索引（必须输出）

在所有阶段之后，必须输出完整的脚本索引：

**重要**：如果在 CI 脚本详细内容中识别到关键配置文件（如构建矩阵配置），必须在"关键配置"小节中输出。

```
## 脚本目录索引

### 关键配置
| 配置文件 | 作用 | 规模 |
|---------|------|------|
| [文件名] | [简要描述作用] | [如：~200 种组合] |

### .github/scripts/
| 脚本名称 | 用途说明 | 被调用的工作流 |
|---------|---------|---------------|
| pr_checklist_check.py | PR清单检查 | pr-check.yml |
| check_model_registry.py | 模型注册表验证 | model-registry-check.yml |
| label_community_user.py | 社区用户标记 | label_community_pr.yml |

### 外部 Action 使用统计
| Action | 用途 | 使用次数 |
|--------|------|---------|
| actions/checkout@v6 | 代码检出 | 7 |
| actions/github-script@v8 | 脚本执行 | 5 |
| actions/setup-python@v6 | Python环境 | 4 |

### 本地 Action
| Action路径 | 用途 | 输入参数 |
|-----------|------|---------|
| .github/actions/xxx | xxx | xxx |
```

**注意**：即使没有找到脚本文件，也要输出此章节，说明"未检测到独立脚本文件"。

### 4. 必须完整列出所有 Job

- 不能省略任何 Job
- 标注 Job 之间的依赖关系
- 说明触发条件和调用关系

---

"""
    
    # Add global context
    prompt += global_context
    
    # Add current batch workflows
    prompt += "## 本批次工作流数据\n\n"
    prompt += "以下是本批次需要详细分析的工作流，请根据它们的实际功能进行阶段划分：\n\n"
    
    workflows = raw_data.get("workflows", {})
    for wf_name in batch_names:
        if wf_name in workflows:
            wf = workflows[wf_name]
            prompt += _format_workflow_detail(wf_name, wf)
    
    # Add other batches summary
    prompt += "\n## 其他批次工作流（简要）\n\n"
    prompt += "以下工作流在其他批次中详细分析，了解它们有助于整体阶段划分：\n\n"
    other_workflows = [wf for wf in workflows.keys() if wf not in batch_names]
    for wf_name in other_workflows[:20]:
        wf = workflows[wf_name]
        triggers = wf.get("triggers", [])
        jobs = wf.get("jobs", {})
        prompt += f"- {wf_name}: {len(jobs)}个Jobs, 触发: {', '.join(triggers[:3])}\n"
    if len(other_workflows) > 20:
        prompt += f"- ... 共{len(other_workflows)}个工作流\n"
    
    prompt += """
---

**提醒**：
1. 必须使用中文输出
2. 必须根据实际功能动态划分阶段，不要硬编码
3. 必须完整列出每个工作流的所有 Job
4. 必须输出脚本目录索引
"""
    
    return prompt


def _format_workflow_detail(wf_name: str, wf: Dict) -> str:
    """Format a single workflow for prompt."""
    result = f"### {wf_name}\n\n"
    
    # Basic info
    result += f"**名称**: {wf.get('name', 'N/A')}\n\n"
    result += f"**路径**: `{wf.get('path', 'N/A')}`\n\n"
    
    # Triggers
    triggers = wf.get("triggers", [])
    result += f"**触发条件**: {', '.join(triggers)}\n\n"
    
    # Jobs
    jobs = wf.get("jobs", {})
    result += f"**Jobs** ({len(jobs)}个):\n\n"
    
    for job_name, job in jobs.items():
        result += f"#### `{job_name}`\n\n"
        
        needs = job.get("needs", [])
        if needs:
            result += f"**依赖**: {', '.join(needs)}\n\n"
        
        runs_on = job.get("runs_on", "")
        if runs_on:
            result += f"**运行环境**: `{runs_on}`\n\n"
        
        uses = job.get("uses", "")
        if uses:
            result += f"**调用工作流**: `{uses}`\n\n"
        
        # Steps summary
        steps = job.get("steps", [])
        if steps:
            result += f"**步骤** ({len(steps)}步):\n"
            for i, step in enumerate(steps[:10], 1):
                step_name = step.get("name", "") or step.get("uses", "") or f"step-{i}"
                if step.get("uses"):
                    result += f"  {i}. {step_name} → {step.get('uses', '')}\n"
                elif step.get("run"):
                    run_preview = step.get("run", "")[:50].replace("\n", " ")
                    result += f"  {i}. {step_name} → run: {run_preview}...\n"
                else:
                    result += f"  {i}. {step_name}\n"
            if len(steps) > 10:
                result += f"  ... 共{len(steps)}步\n"
            result += "\n"
        
        # Calls
        calls_workflows = job.get("calls_workflows", [])
        calls_actions = job.get("calls_actions", [])
        if calls_workflows:
            result += f"**调用工作流**: {', '.join(calls_workflows)}\n\n"
        if calls_actions:
            result += f"**使用Action**: {', '.join(calls_actions[:5])}\n\n"
    
    result += "---\n\n"
    return result


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 3:
        print("Usage:")
        print("  python ci_diagram_generator.py prompt <raw_data.json> [output_file]")
        print("  python ci_diagram_generator.py split <raw_data.json> <output_dir> [max_workflows_per_batch]")
        print("  python ci_diagram_generator.py diagram <raw_data.json> <llm_response.md> [output_file]")
        print()
        print("Commands:")
        print("  prompt  - Generate single prompt file")
        print("  split   - Split large project into multiple prompt files")
        print("  diagram - Generate final document from LLM response")
        print()
        print("Workflow:")
        print("  Small projects:")
        print("    1. python ci_diagram_generator.py prompt ci_data.json prompt.txt")
        print("    2. Send prompt to LLM, save as response.md")
        print("    3. python ci_diagram_generator.py diagram ci_data.json response.md output.md")
        print()
        print("  Large projects (>20 workflows):")
        print("    1. python ci_diagram_generator.py split ci_data.json ./prompts/")
        print("    2. Process each prompt file with subagents")
        print("    3. Merge responses and run diagram command")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "prompt":
        # Generate single LLM prompt
        with open(sys.argv[2], "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        
        prompt = generate_llm_prompt(raw_data)
        
        if len(sys.argv) > 3:
            output_file = sys.argv[3]
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(prompt)
            print(f"Prompt saved to: {output_file}")
        else:
            sys.stdout.buffer.write(prompt.encode("utf-8"))
    
    elif command == "split":
        # Generate split prompts for large projects
        with open(sys.argv[2], "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        
        output_dir = sys.argv[3] if len(sys.argv) > 3 else "./prompts"
        max_per_batch = int(sys.argv[4]) if len(sys.argv) > 4 else 10
        
        files = generate_split_prompts(raw_data, output_dir, max_per_batch)
        print(f"\nGenerated {len(files)} files in {output_dir}")
        print("Check README.txt for usage instructions")
    
    elif command == "diagram":
        # Generate diagram from LLM response
        with open(sys.argv[2], "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        
        with open(sys.argv[3], "r", encoding="utf-8") as f:
            llm_response = f.read()
        
        output_file = sys.argv[4] if len(sys.argv) > 4 else "CI_ARCHITECTURE.md"
        
        diagram = generate_architecture_diagram(raw_data, llm_response, output_file)
        print(f"Done. Output saved to: {output_file}")
    
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
