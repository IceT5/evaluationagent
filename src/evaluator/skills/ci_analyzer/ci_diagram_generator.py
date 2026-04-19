#!/usr/bin/env python3
"""
CI Architecture Diagram Generator - Generate architecture diagrams from LLM analysis

This module generates LLM prompts and processes LLM responses.
ALL classification and organization logic is handled by LLM for maximum flexibility.
"""

import json
import re
import math
from pathlib import Path
from typing import Dict, List, Any, Optional


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
    
    try:
        from evaluator.config import config
        HAS_CONFIG = True
    except ImportError:
        HAS_CONFIG = False
        config = None
    
    os.makedirs(output_dir, exist_ok=True)
    
    workflows = raw_data.get("workflows", {})
    workflow_names = list(workflows.keys())
    
    global_context = _generate_global_context(raw_data)
    
    # 使用动态分批（如果配置可用）
    if HAS_CONFIG and config:
        batches = _split_workflows_by_tokens(raw_data, config, global_context)
        print(f"  [Dynamic Split] 按 token 大小分批: {len(batches)} 个批次")
    else:
        # 回退：使用固定分批
        batches = []
        for i in range(0, len(workflow_names), max_workflows_per_batch):
            batch_names = workflow_names[i:i + max_workflows_per_batch]
            batches.append(batch_names)
    
    generated_files = []
    batch_inputs = []
    
    main_system_prompt = _generate_multi_round_system_prompt()
    
    # 构建 main_rounds (6轮)
    main_rounds = []
    main_rounds.append(_generate_round_0(raw_data))
    main_rounds.append(_generate_round_1(raw_data))
    main_rounds.append(_generate_round_2())
    main_rounds.append(_generate_round_3())
    main_rounds.append(_generate_round_4())
    main_rounds.append(_generate_round_5())
    
    print(f"  [Multi-Round] 生成了 {len(main_rounds)} 个 rounds 用于 main 分析")
    
    # Batch 1-N: Workflow详情
    for batch_idx, batch_names in enumerate(batches, 1):
        batch_prompt = _generate_batch_prompt(raw_data, global_context, batch_names, batch_idx, len(batches))
        batch_file = os.path.join(output_dir, f"prompt_workflow_{batch_idx}.txt")
        with open(batch_file, "w", encoding="utf-8") as f:
            f.write(batch_prompt)
        generated_files.append(batch_file)
        batch_inputs.append({
            "path": batch_file,
            "batch_type": "workflow_detail",
            "batch_index": batch_idx,
            "workflow_names": batch_names,
            "related_scripts": [s.get("path", "") for s in raw_data.get("scripts", []) if s.get("called_by") and any(wf in s.get("called_by", []) for wf in batch_names)],
            "empty_script": False,
        })
        print(f"Generated: {batch_file}")
    
    # Batch N+1: 脚本分析（可能分批）
    if HAS_CONFIG and config:
        script_analysis_prompts = _generate_script_analysis_prompts(raw_data, config, global_context)
    else:
        script_analysis_prompts = [_format_script_analysis_content(raw_data.get("scripts", []))]

    if not script_analysis_prompts:
        script_analysis_prompts = [_format_script_analysis_content([])]
    
    for i, prompt in enumerate(script_analysis_prompts):
        batch_file = os.path.join(output_dir, f"prompt_script_{i+1}.txt")
        with open(batch_file, "w", encoding="utf-8") as f:
            f.write(prompt)
        generated_files.append(batch_file)
        batch_inputs.append({
            "path": batch_file,
            "batch_type": "script_detail",
            "batch_index": i + 1,
            "workflow_names": [],
            "related_scripts": [s.get("path", "") for s in raw_data.get("scripts", [])],
            "empty_script": len(raw_data.get("scripts", [])) == 0,
        })
        print(f"Generated: {batch_file} (script analysis batch {i+1}/{len(script_analysis_prompts)})")
    
    merge_file = os.path.join(output_dir, "README.txt")
    
    if len(batches) == 0:
        batch_info = "无详细批次（项目无工作流）"
    elif len(batches) == 1:
        batch_info = "prompt_workflow_1.txt - 详细文档"
    else:
        batch_info = f"prompt_workflow_1.txt ~ prompt_workflow_{len(batches)}.txt - 详细文档批次"
    
    if len(script_analysis_prompts) == 0:
        script_batch_info = "无脚本分析批次（未检测到脚本）"
    elif len(script_analysis_prompts) == 1:
        script_batch_info = "prompt_script_1.txt"
    else:
        script_batch_info = f"prompt_script_1.txt ~ prompt_script_{len(script_analysis_prompts)}.txt"
    
    merge_content = f"""# Prompt文件说明

此项目CI/CD分析使用多轮对话模式：

## Main 分析（多轮对话）

main 分析使用 {len(main_rounds)} 轮对话：
- Round 0: 项目概述
- Round 1: 阶段划分
- Round 2: JSON架构
- Round 3: 架构图
- Round 4: 调用关系树
- Round 5: 评分与建议

## Batch 分析（并发）

{batch_info}：
- 每个包含完整调用关系图
- 当前批次的详细工作流信息

{script_batch_info}：
- 脚本内容分析
- 关键配置识别

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
        "batch_inputs": batch_inputs,
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
    
    # Workflow/script high-level summary only
    workflows = raw_data.get("workflows", {})
    if workflows:
        context += f"### 工作流概况\n共 {len(workflows)} 个工作流。详细工作流清单与逐项分析由 main rounds 或 workflow batch 提供。\n\n"

    scripts = raw_data.get("scripts", [])
    if scripts:
        context += f"### CI脚本概况\n共 {len(scripts)} 个 CI 脚本。详细脚本目录、脚本内容与关键配置分析由 script batch 提供。\n\n"
    
    return context


def _generate_batch_prompt(raw_data: Dict, global_context: str, batch_names: List[str], batch_idx: int, total_batches: int) -> str:
    """Generate batch prompt - 每个 workflow 逐个输出详情，不做阶段划分"""
    prompt = f"""# CI/CD 架构分析 - 详细文档（批次 {batch_idx}/{total_batches}）

**重要：本文档必须使用中文输出！完整列出所有Job！**

你正在分析一个大型项目的CI/CD架构。这是第{batch_idx}批次详细分析。

---

## 输出要求

### 1. 工作流输出格式

**注意：本批次只负责输出每个工作流的详情，不要做阶段划分。阶段划分由其他环节统一处理。**

**本批次只输出 workflow 的事实性详情，不输出阶段划分、阶段命名或架构归纳结论。**

**必须严格遵守以下格式，不要简化！**

每个工作流按如下格式输出：

#### X.X workflow-name.yml

**目的**: [一句话说明]

**触发条件**:
```yaml
[完整触发配置，从数据中提取，不要省略]
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

**关键要求**：
1. **必须包含"目的"字段**：使用 `**目的**:`，不要使用其他字段名（如"用途"、"功能"等）
2. **必须包含"触发条件"字段**：使用 `**触发条件**:`，不要使用其他字段名（如"触发方式"、"触发器"等）
3. **必须包含Job表格**：使用 `**包含的Job**:`，必须包含表格（| 序号 | Job名称 | 运行环境 | 目的 |）
4. **禁止使用简化格式**：
   - ❌ 不要使用：`- **用途**:`、`- **特点**:`、`- **被调用者**:`
   - ✅ 必须使用：`**目的**:`、`**触发条件**:`、`**包含的Job**:`

**禁止的简化格式示例**（不要这样写）：
```
#### X.X workflow-name.yml
- **用途**: xxx
- **特点**: xxx
- **被调用者**: xxx
```
↑ 这是简化格式，禁止使用！

**正确的完整格式示例**：
```
#### 1. ci-workflow-pull-request.yml

**目的**: PR验证的主CI流程，在代码提交协作者PR时执行构建和验证测试

**触发条件**:
```yaml
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
```

**包含的Job**（共15个）:
| 序号 | Job名称 | 运行环境 | 目的 |
|-----|---------|---------|------|
| 1 | build-workflow | ubuntu-latest | 构建主工作流，初始化构建环境 |
| 2 | dispatch-groups-linux-two-stage | - | 分发Linux两阶段构建任务 |
| ... | ... | ... | ... |

**依赖关系**: build-workflow → dispatch-groups-linux-two-stage → verify-workflow

**执行步骤详情**:
- Job 1: build-workflow
  - 步骤1: Export workflow flags
  - 步骤2: Checkout repo
```
↑ 这是完整格式，必须这样写！

### 2. 必须完整列出所有 Job

**重要**：
- ✅ 对**所有工作流**（包括被调用的辅助工作流）都必须生成完整的分析
- ✅ 不要因为工作流是通过 workflow_call 被调用就简化处理
- ✅ 即使工作流只有 1-2 个 Job，也要生成完整表格
- ✅ 不能省略任何 Job
- ✅ 标注 Job 之间的依赖关系
- ✅ 说明触发条件和调用关系

---

"""
    
    # Add global context
    prompt += global_context
    
    # Add current batch workflows
    prompt += "## 本批次工作流数据\n\n"
    prompt += "以下是本批次需要详细分析的工作流，逐个输出完整详情：\n\n"
    
    workflows = raw_data.get("workflows", {})
    scripts = raw_data.get("scripts", [])
    
    for wf_name in batch_names:
        if wf_name in workflows:
            wf = workflows[wf_name]
            prompt += _format_workflow_detail(wf_name, wf, scripts)
    
    # Add related scripts content
    prompt += "\n## 本批次相关脚本内容\n\n"
    prompt += "以下脚本内容仅用于帮助理解当前 workflow 的执行上下文、job 目的和脚本调用关系，不要求你对脚本做独立的深度分析。\n\n"
    
    batch_related_scripts = []
    for wf_name in batch_names:
        related = _get_workflow_related_scripts(wf_name, scripts)
        batch_related_scripts.extend(related)
    
    # 去重并输出
    seen = set()
    for script in batch_related_scripts:
        script_name = script.get("name", "")
        if script_name and script_name not in seen:
            seen.add(script_name)
            prompt += _format_script_detail(script)
    
    if not seen:
        prompt += "本批次工作流未检测到调用的脚本。\n\n"
    
    # Add other batches summary
    prompt += "\n## 其他批次工作流（简要）\n\n"
    prompt += "以下工作流在其他批次中详细分析，提供这些概览仅用于避免将当前批次误判为完整系统，不要求你做阶段划分：\n\n"
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
2. 必须完整列出每个工作流的所有 Job
3. 如输出脚本目录索引，应仅作为当前 batch 的辅助信息，最终以 script batch 汇总为准
4. 相关脚本内容仅用于辅助理解 workflow，不要展开为独立脚本分析，也不要输出脚本实现级优化建议
"""
    
    return prompt


def _format_workflow_detail(wf_name: str, wf: Dict, scripts: List[dict] = None) -> str:
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
            for i, step in enumerate(steps[:20], 1):
                step_name = step.get("name", "") or step.get("uses", "") or f"step-{i}"
                if step.get("uses"):
                    result += f"  {i}. {step_name} → {step.get('uses', '')}\n"
                elif step.get("run"):
                    run_preview = step.get("run", "")[:500]
                    result += f"  {i}. {step_name} → run: {run_preview}...\n"
                else:
                    result += f"  {i}. {step_name}\n"
            if len(steps) > 20:
                result += f"  ... 共{len(steps)}步\n"
            result += "\n"
        
        # Calls
        calls_workflows = job.get("calls_workflows", [])
        calls_actions = job.get("calls_actions", [])
        if calls_workflows:
            result += f"**调用工作流**: {', '.join(calls_workflows)}\n\n"
        if calls_actions:
            result += f"**使用Action**: {', '.join(calls_actions[:5])}\n\n"
    
    # 外部 CI 调用信息
    if scripts:
        external_ci_calls = _get_workflow_external_ci_calls(wf_name, scripts)
        if external_ci_calls:
            result += "**外部 CI 系统调用**:\n\n"
            for call_key, call_info in external_ci_calls.items():
                result += f"- **{call_key}**\n"
                result += f"  - 触发 Job: {', '.join(call_info['trigger_jobs'])}\n"
                scripts_list = call_info['called_scripts']
                if scripts_list:
                    result += f"  - 调用脚本: {', '.join(scripts_list[:10])}"
                    if len(scripts_list) > 10:
                        result += f" (+{len(scripts_list)-10})"
                    result += "\n"
            result += "\n"
    
    result += "---\n\n"
    return result


def _get_workflow_related_scripts(wf_name: str, scripts: List[dict]) -> List[dict]:
    """获取与 workflow 相关的所有脚本（直接 + 间接调用）
    
    Args:
        wf_name: workflow 名称
        scripts: 所有脚本列表
    
    Returns:
        相关脚本列表
    """
    related = []
    for script in scripts:
        for caller in script.get("called_by", []):
            # 直接调用：workflow::job
            # 间接调用：workflow::job→system:pipeline
            if caller.startswith(f"{wf_name}::"):
                if script not in related:
                    related.append(script)
                break
    return related


def _get_workflow_external_ci_calls(wf_name: str, scripts: List[dict]) -> Dict[str, dict]:
    """获取 workflow 的外部 CI 调用信息
    
    Args:
        wf_name: workflow 名称
        scripts: 所有脚本列表
    
    Returns:
        {
            "jenkins:Build.groovy": {
                "system": "jenkins",
                "pipeline": "Build.groovy",
                "trigger_jobs": ["Job-trigger"],
                "called_scripts": ["build_wheel.py", ...],
            },
            ...
        }
    """
    external_calls = {}
    
    for script in scripts:
        for caller in script.get("called_by", []):
            # 匹配格式：workflow::job→system:pipeline
            match = re.match(
                rf"^{re.escape(wf_name)}::(\w+)→(\w+):(.+)$",
                caller
            )
            if match:
                job_name = match.group(1)
                system = match.group(2)
                pipeline_name = match.group(3)
                
                key = f"{system}:{pipeline_name}"
                if key not in external_calls:
                    external_calls[key] = {
                        "system": system,
                        "pipeline": pipeline_name,
                        "trigger_jobs": [],
                        "called_scripts": [],
                    }
                
                if job_name not in external_calls[key]["trigger_jobs"]:
                    external_calls[key]["trigger_jobs"].append(job_name)
                
                script_name = script.get("name", "")
                if script_name and script_name not in external_calls[key]["called_scripts"]:
                    external_calls[key]["called_scripts"].append(script_name)
    
    return external_calls


def _format_script_detail(script: Dict) -> str:
    """格式化单个脚本的详细内容
    
    根据文件类型采用不同策略：
    - 配置文件：传递完整内容（最多 50KB）
    - 可执行脚本：传递元信息 + 前 500 字符预览
    - 其他类型：只传递预览（前 2000 字符）
    """
    result = f"#### `{script.get('name')}`\n\n"
    result += f"**路径**: `{script.get('path')}`\n\n"
    
    script_type = script.get("type", "")
    result += f"**类型**: {script_type}\n\n"
    
    # 被调用
    called_by = script.get("called_by", [])
    if called_by:
        result += f"**被调用**: {', '.join(called_by[:5])}"
        if len(called_by) > 5:
            result += f" (+{len(called_by)-5})"
        result += "\n\n"
    
    content = script.get("content", "")
    
    # 配置文件：传递内容
    if script_type in [".yaml", ".yml", ".json"]:
        if content:
            if len(content) < 50 * 1024:
                lang = script_type[1:] if script_type else "yaml"
                result += f"**内容**:\n```{lang}\n{content}\n```\n\n"
            else:
                lang = script_type[1:] if script_type else "yaml"
                result += f"**大小**: {len(content)} 字符\n"
                result += f"**内容预览** (前10000字符):\n```{lang}\n{content[:10000]}\n```\n\n"
    
    # 可执行脚本：传递元信息 + 轻量预览
    elif script_type in [".py", ".sh", ".ps1", ".bat", ".groovy"]:
        functions = script.get("functions", [])
        if functions:
            result += f"**函数** ({len(functions)}个): {', '.join(functions[:20])}"
            if len(functions) > 20:
                result += f" (+{len(functions)-20})"
            result += "\n\n"
        
        imports = script.get("imports", [])
        if imports:
            result += f"**导入** ({len(imports)}个): {', '.join(imports[:20])}"
            if len(imports) > 20:
                result += f" (+{len(imports)-20})"
            result += "\n\n"

        if content:
            result += f"**内容预览** (前500字符):\n```{script_type[1:] if script_type else ''}\n{content[:500]}\n```\n\n"
    
    # 其他类型：只输出预览
    elif content:
        result += f"**内容预览** (前2000字符):\n```\n{content[:2000]}\n```\n\n"
    
    return result


def _calculate_script_detail_size(script: Dict) -> int:
    """计算单个脚本详细信息的大小
    
    根据文件类型采用不同策略：
    - 配置文件：完整内容（最多 50KB）
    - 可执行脚本：元信息 + 500 字符预览
    - 其他类型：预览（2000 字符）
    """
    script_type = script.get("type", "")
    content = script.get("content", "")
    
    # 配置文件：完整内容（最多 50KB）
    if script_type in [".yaml", ".yml", ".json"]:
        return min(len(content), 50 * 1024) + 200
    
    # 可执行脚本：元信息 + 轻量预览
    elif script_type in [".py", ".sh", ".ps1", ".bat", ".groovy"]:
        size = 200
        size += len(", ".join(script.get("functions", [])[:20]))
        size += len(", ".join(script.get("imports", [])[:20]))
        size += len(", ".join(script.get("called_by", [])[:5]))
        size += min(len(content), 500)
        return size
    
    # 其他类型：预览
    elif content:
        return min(len(content), 2000) + 200
    
    return 200


def _calculate_workflow_detail_size(
    wf_name: str,
    wf: Dict,
    scripts: List[dict]
) -> int:
    """计算单个 workflow 详细信息的大小
    
    包括：
    - workflow 基本信息
    - jobs 信息
    - 相关脚本大小
    """
    size = 0
    
    # workflow 基本信息
    size += 500
    size += len(str(wf.get("trigger_details", {})))
    
    # jobs 信息
    jobs = wf.get("jobs", {})
    for job_name, job in jobs.items():
        size += 200
        steps = job.get("steps", [])
        for step in steps:
            size += len(step.get("run", ""))
    
    # 相关脚本大小
    related_scripts = _get_workflow_related_scripts(wf_name, scripts)
    for script in related_scripts:
        size += _calculate_script_detail_size(script)
    
    return size


def _split_workflows_by_tokens(
    raw_data: Dict,
    config: Any,
    global_context: str
) -> List[List[str]]:
    """按 token 大小动态分批 workflow
    
    原则：同一个 workflow 不截断
    
    Args:
        raw_data: CI/CD 数据
        config: 配置对象
        global_context: 全局上下文
    
    Returns:
        分批后的 workflow 名称列表
    """
    workflows = raw_data.get("workflows", {})
    workflow_names = list(workflows.keys())
    scripts = raw_data.get("scripts", [])
    
    max_batch_tokens = int(config.llm_max_tokens * config.max_batch_prompt_ratio)
    
    # 计算固定开销
    fixed_size = len(global_context) + 2000  # global_context + prompt 模板
    other_batch_size = 20 * 100  # 其他批次简要
    
    batches = []
    current_batch = []
    current_size = fixed_size + other_batch_size
    
    for wf_name in workflow_names:
        # 计算该 workflow 的详细信息大小
        wf_size = _calculate_workflow_detail_size(wf_name, workflows[wf_name], scripts)
        
        # 检查是否需要新开批次
        if current_size + wf_size > max_batch_tokens and current_batch:
            # 当前批次已满，开始新批次
            batches.append(current_batch)
            current_batch = []
            current_size = fixed_size + other_batch_size
        
        # 添加到当前批次
        current_batch.append(wf_name)
        current_size += wf_size
    
    # 添加最后一个批次
    if current_batch:
        batches.append(current_batch)
    
    return batches


def decide_prompt_strategy(raw_data: Dict, config: Any) -> Dict[str, Any]:
    """动态决定 prompt 策略
    
    Args:
        raw_data: CI/CD 数据
        config: 配置对象
    
    Returns:
        {
            "strategy": "multi_round",
            "batch_size": int,
            "estimated_tokens": int,
        }
    """
    # 估算 token 数
    total_tokens = _estimate_prompt_tokens(raw_data)
    
    # 计算批次大小
    max_batch_tokens = int(config.llm_max_tokens * config.max_batch_prompt_ratio)
    workflow_count = len(raw_data.get("workflows", {}))
    
    if total_tokens > 0:
        batch_size = min(
            config.max_workflows_batch,
            max(1, int(workflow_count * max_batch_tokens / total_tokens))
        )
    else:
        batch_size = config.max_workflows_batch
    
    return {
        "strategy": "multi_round",
        "batch_size": batch_size,
        "estimated_tokens": total_tokens,
    }


def _estimate_global_context_size(raw_data: Dict) -> int:
    """估算 global_context 大小
    
    global_context 包含：
    - 仓库名称
    - CI 目录
    - Jenkins Pipeline 数量
    - 外部 CI 脚本数量
    - 调用关系图
    - Action 使用统计
    - 所有工作流列表
    - 所有脚本列表
    """
    size = 0
    
    # 基本信息
    size += 500
    
    # 工作流列表
    workflows = raw_data.get("workflows", {})
    for wf_name, wf in workflows.items():
        size += 100  # 每个工作流一行
        size += len(wf_name)
    
    # 脚本列表
    scripts = raw_data.get("scripts", [])
    for s in scripts:
        size += 50  # �$个脚本一行
        size += len(s.get("name", ""))
    
    # 调用关系图
    relationships = raw_data.get("relationships", {})
    workflow_calls = relationships.get("workflow_calls", {})
    for callee, callers in workflow_calls.items():
        size += len(callee)
        size += sum(len(c) for c in callers[:5])
    
    # Action 使用统计
    action_usages = relationships.get("action_usages", {})
    for action, users in list(action_usages.items())[:10]:
        size += len(action)
        size += 20  # 使用次数
    
    return size


def _estimate_prompt_tokens(raw_data: Dict) -> int:
    """估算 prompt token 数
    
    根据文件类型采用不同策略：
    - 配置文件：计算完整内容（最多 50KB）
    - 可执行脚本：只计算元信息
    - 其他类型：只计算预览（2000 字符）
    """
    # 基础信息
    base_size = _estimate_base_prompt_size(raw_data)
    
    # 脚本内容 - 根据文件类型分别计算
    scripts = raw_data.get("scripts", [])
    script_size = 0
    
    for s in scripts:
        script_type = s.get("type", "")
        content = s.get("content", "")
        
        # 配置文件：计算完整内容（最多 50KB）
        if script_type in [".yaml", ".yml", ".json"]:
            script_size += min(len(content), 50 * 1024)
        
        # 可执行脚本：只计算元信息
        elif script_type in [".py", ".sh", ".ps1", ".bat", ".groovy"]:
            script_size += 200  # 基本信息
            script_size += len(", ".join(s.get("functions", [])[:20]))
            script_size += len(", ".join(s.get("imports", [])[:20]))
        
        # 其他类型：只计算预览（2000 字符）
        elif content:
            script_size += min(len(content), 2000)
    
    # global_context 大小
    global_context_size = _estimate_global_context_size(raw_data)
    
    # prompt 模板大小
    template_size = 2000
    
    # 其他批次工作流简要（最多 20 个工作流，每个约 100 字符）
    other_batch_size = 20 * 100
    
    total_size = base_size + script_size + global_context_size + template_size + other_batch_size
    return int(total_size / 4)


def _estimate_base_prompt_size(raw_data: Dict) -> int:
    """估算基础 prompt 大小（不含脚本内容）
    
    Args:
        raw_data: CI/CD 数据
    
    Returns:
        估算的字节数
    """
    size = 0
    
    # workflow 详情
    workflows = raw_data.get("workflows", {})
    for wf_name, wf in workflows.items():
        # 基本信息 + 触发条件 + Jobs
        size += 500  # 基本信息
        size += len(str(wf.get("trigger_details", {})))  # 触发条件
        jobs = wf.get("jobs", {})
        for job_name, job in jobs.items():
            size += 200  # Job 基本信息
            steps = job.get("steps", [])
            for step in steps:
                size += len(step.get("run", ""))  # run 命令
    
    # 其他信息
    size += 5000  # 输出格式要求等固定内容
    
    return size


def _generate_round_0(raw_data: Dict) -> str:
    """Round 0: 项目概述"""
    workflows = raw_data.get("workflows", {})
    scripts = raw_data.get("scripts", [])
    jenkins_pipelines = raw_data.get("jenkins_pipelines", [])
    external_ci_scripts = raw_data.get("external_ci_scripts", [])
    other_ci_configs = raw_data.get("other_ci_configs", [])
    
    # 统计脚本类型
    script_types = {}
    for s in scripts:
        t = s.get("type", "unknown")
        script_types[t] = script_types.get(t, 0) + 1
    
    prompt = f"""# CI/CD 架构分析 - 项目概述

**重要：本文档必须使用中文输出！**

## 项目概况

- **仓库名称**: {raw_data.get('repo_name', 'Unknown')}
- **CI目录**: {', '.join(raw_data.get('ci_directories', []))}

## Workflow 列表

| 名称 | Jobs数 | 触发条件 |
|------|--------|---------|
"""
    
    for wf_name, wf in workflows.items():
        jobs_count = len(wf.get("jobs", {}))
        triggers = list(wf.get("on", {}).keys()) if isinstance(wf.get("on"), dict) else []
        prompt += f"| {wf_name} | {jobs_count} | {', '.join(triggers[:3])} |\n"
    
    prompt += f"""
## 脚本目录结构

| 目录 | 脚本数 | 主要类型 |
|------|--------|---------|
"""
    
    # 按目录统计脚本
    scripts_by_dir = {}
    for s in scripts:
        path = s.get("path", "")
        dir_name = path.split("/")[0] if "/" in path else "root"
        if dir_name not in scripts_by_dir:
            scripts_by_dir[dir_name] = {"count": 0, "types": set()}
        scripts_by_dir[dir_name]["count"] += 1
        scripts_by_dir[dir_name]["types"].add(s.get("type", "unknown"))
    
    for dir_name, info in scripts_by_dir.items():
        types_str = ", ".join(list(info["types"])[:3])
        prompt += f"| {dir_name}/ | {info['count']} | {types_str} |\n"
    
    prompt += f"""
## 外部CI系统

- **Jenkins Pipeline**: {len(jenkins_pipelines)} 个
- **外部CI脚本**: {len(external_ci_scripts)} 个
- **其他CI配置**: {len(other_ci_configs)} 个

---

## 输出要求

请输出【项目概述】章节：

## 项目概述

本项目是一个 [项目类型]，采用 [CI系统] 架构。

**CI/CD 整体特点**：
- 工作流总数：{len(workflows)} 个
- 主要触发方式：...
- 外部系统集成：...
- 核心功能：...

**架构特点**：
- ...

**注意**：只输出此章节，不要输出其他内容。
"""
    
    return prompt


def _generate_round_1(raw_data: Dict) -> str:
    """Round 1: 阶段划分"""
    workflows = raw_data.get("workflows", {})

    # 从 ci_data 提取项目实际使用的触发类型（权威来源）
    trigger_types = sorted({
        t
        for wf_data in workflows.values()
        for t in (wf_data.get("triggers") or [])
        if t
    })
    trigger_list_str = ", ".join(trigger_types) if trigger_types else "push, pull_request, schedule, workflow_dispatch"
    trigger_detail_lines = "\n".join(f"- {t}" for t in trigger_types) if trigger_types else (
        "- push\n- pull_request\n- schedule\n- workflow_dispatch"
    )

    prompt = """# CI/CD 架构分析 - 阶段划分

## 所有 Workflow 列表

以下是所有需要分配到阶段的工作流，请确保**每一个都必须分配到具体阶段**，不得遗漏任何工作流。

"""

    # 列出所有 workflow 名称
    for wf_name in workflows.keys():
        prompt += f"- {wf_name}\n"

    prompt += f"""
---

## 输出要求

请输出【阶段划分】章节：

## 阶段划分

根据工作流的触发条件和功能，划分为以下阶段：

**重要：必须将上面列出的每一个工作流都明确分配到一个阶段中，不得使用通配符或概括性描述（如 generated-linux-*.yml）。每个工作流必须出现在下面的表格中。**

**注意：阶段一（触发入口）只列触发类型，不列 workflow 文件名。其他阶段列出各自归属的 workflow 文件名。**

| 阶段 | 内容 | 说明 |
|------|------|------|
| 阶段一：触发入口 | {trigger_list_str} | 各类触发类型，不包含具体 workflow |
| 阶段二：[阶段名称] | ci-workflow.yml, check-label.yml, ... | 该阶段下的所有 workflow |
| 阶段三：[阶段名称] | lint.yml, test.yml, ... | 该阶段下的所有 workflow |
| ... | ... | ... |

每个阶段展开说明：

### 阶段一：触发入口

本项目实际使用的触发类型（必须全部列出，不得增减）：
{trigger_detail_lines}

### 阶段二：[阶段名称]

归属工作流：
- workflow-a.yml: ...
- workflow-b.yml: ...

**注意**：只输出此章节，不要输出其他内容。
"""

    return prompt


def _generate_round_2() -> str:
    """Round 2: JSON架构"""
    return """# CI/CD 架构分析 - JSON架构数据

## 输出要求

请输出JSON架构数据。

**重要**：
1. 不要输出ASCII架构图
2. 只输出JSON数据

## 多轮对话延续性

1. Round 2 是 Round 1 的延续，不是重新设计
2. 本轮任务：将 Round 1 的阶段划分转换为 JSON 格式（格式转换，不做决策）

## 阶段划分一致性要求

1. 必须沿用 Round 1 已确定的阶段划分
2. 映射规则：Round 1 的每个阶段 → JSON 的一个 layer
3. layers 数组长度 = Round 1 识别的阶段数量

**禁止行为**：
- ❌ 合并阶段（如将多个阶段合并为"工作流层"）
- ❌ 简化结构
- ❌ 重新分类或重新命名

## 触发层特殊要求（重要！）

**触发入口层（第一个layer）必须包含触发类型节点，而不是工作流节点！**

**触发类型来源**：
触发类型从工作流数据的 `on` 字段中提取，常见类型包括：
- push、pull_request、schedule、workflow_dispatch、workflow_call、issues、issue_comment、release 等

**重要**：以实际提取到的 `on` 字段为准，不要遗漏任何触发类型！

**触发层格式**：
```json
{
  "id": "layer-trigger",
  "name": "触发入口",
  "nodes": [
    {"id": "trigger-push", "label": "push", "description": "代码推送触发"},
    {"id": "trigger-pr", "label": "pull_request", "description": "PR事件触发"},
    {"id": "trigger-schedule", "label": "schedule", "description": "定时触发"}
  ]
}
```

**注意**：
- ✅ 节点label是触发类型（push、pull_request等），不是工作流名称
- ✅ 节点id格式：trigger-{触发类型}
- ❌ 不要把工作流名称（xxx.yml）放在触发层

## JSON格式规范

**JSON结构说明**：
- layers: 架构层数组，按执行顺序排列
- 每个layer包含：
  - id: 层唯一标识
  - name: 层名称（必须与 Round 1 的阶段名称一致）
  - nodes: 该层的节点数组
- 每个node包含：
  - id: 节点唯一标识
  - label: 节点标签（触发类型或工作流名称）
  - description: 节点描述
  - jobs: （仅工作流节点）Job数量
  - calls_scripts: （仅工作流节点）调用的脚本列表
- connections: 连接关系数组，体现调用关系
  - source: 源节点ID
  - target: 目标节点ID
  - 规则：
    - 触发层节点 → 被触发的工作流节点
    - 工作流节点 → 调用的脚本/外部系统

## 正确示例

假设项目有以下触发条件：
- push
- pull_request
- schedule

Round 1 识别了以下阶段：
- 阶段一：触发入口
- 阶段二：项目自动化
- 阶段三：代码质量检查

则 JSON 应有 **3个 layer**：

<!-- ARCHITECTURE_JSON
{
  "layers": [
    {
      "id": "layer-trigger",
      "name": "触发入口",
      "nodes": [
        {"id": "trigger-push", "label": "push", "description": "代码推送触发"},
        {"id": "trigger-pr", "label": "pull_request", "description": "PR事件触发"},
        {"id": "trigger-schedule", "label": "schedule", "description": "定时触发"}
      ]
    },
    {
      "id": "layer-automation",
      "name": "项目自动化",
      "nodes": [
        {"id": "wf-auto-assign", "label": "auto-assign.yml", "description": "自动分配负责人", "jobs": 1},
        {"id": "wf-label", "label": "label-issue.yml", "description": "自动标签", "jobs": 1}
      ]
    },
    {
      "id": "layer-quality",
      "name": "代码质量检查",
      "nodes": [
        {"id": "wf-pr-check", "label": "pr-check.yml", "description": "PR格式检查", "jobs": 2}
      ]
    }
  ],
  "connections": [
    {"source": "trigger-pr", "target": "wf-pr-check"},
    {"source": "trigger-push", "target": "wf-auto-assign"}
  ]
}
ARCHITECTURE_JSON -->

## 错误示例

❌ **错误1**：触发层包含工作流节点

<!-- ARCHITECTURE_JSON
{
  "layers": [
    {
      "id": "layer-1",
      "name": "触发入口",
      "nodes": [
        {"id": "node-1-1", "label": "ci-workflow.yml", "description": "主CI流程", "jobs": 10}
      ]
    }
  ]
}
ARCHITECTURE_JSON -->
↑ 错误：触发层包含的是工作流节点，而不是触发类型节点

❌ **错误2**：将多个阶段合并为"工作流层"

<!-- ARCHITECTURE_JSON
{
  "layers": [
    {
      "id": "layer-workflows",
      "name": "工作流层",
      "nodes": [...]
    }
  ]
}
ARCHITECTURE_JSON -->
↑ 错误：合并了多个阶段

## 输出要求

**必须输出**：
1. 完整的JSON架构数据
2. 包含所有触发类型节点
3. connections从触发节点连接到工作流节点

**禁止输出**：
1. ASCII架构图
2. 其他任何内容
"""


def _generate_round_3() -> str:
    """Round 3: 架构图"""
    return """# CI/CD 架构分析 - 架构图

## 输出要求

请根据前面输出的JSON架构数据，生成架构图。

**格式要求**：
1. **必须以 `## 架构图` 作为章节标题**
2. 使用ASCII框线(┌─┐│└┘)和箭头(→▶▼▲)
3. 必须包含JSON中的所有layers
4. 每个节点包含关键信息（Job数量、触发条件等）

**示例**：
## 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    CI/CD 整体架构                            │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────── 触发入口层 ───────────┐                        │
│  │  push   │  pull_request  │  schedule  │                  │
│  └───────────────┬───────────────────┘                       │
│                  ▼                                           │
│  ┌─────────── 主CI入口层 ───────────┐                        │
│  │  workflow-a (5 jobs)  │  workflow-b (3 jobs)  │          │
│  └─────────────────────────────────┘                         │
└─────────────────────────────────────────────────────────────┘
```

只输出架构图章节，不要其他内容。
"""


def _generate_round_4() -> str:
    """Round 4: 调用关系树"""
    return """# CI/CD 架构分析 - 调用关系树

## 输出要求

请输出调用关系树。

**格式要求**：
- 使用树形结构（├─ └─ │）
- 展示workflow之间的调用关系
- 展示workflow与脚本的调用关系
- 展示外部系统调用

**示例**：
```
## 附录：调用关系树

├─ push
│  └─ workflow-a.yml
│     └─ job1 → script1.sh
│     └─ job2 → jenkins:Build.groovy
├─ pull_request
│  └─ workflow-b.yml
│     └─ job1 → workflow-c.yml (调用)
│     └─ job2 → script2.py
├─ schedule
│  └─ workflow-d.yml
│     └─ job1 → external_ci:system
...
```

只输出此章节，不要其他内容。
"""


def _generate_round_5() -> str:
    """Round 5: 合并JSON输出"""
    return """# CI/CD 架构分析 - 评分与建议

## 输出要求

请输出分析结果JSON。

**输出格式**：
```json
{
  "scores": {
    "architecture_design": {"score": 8, "rationale": "工作流按阶段清晰划分，依赖关系明确"},
    "best_practices": {"score": 7, "rationale": "使用了缓存和矩阵构建，但缺少复用策略"},
    "security": {"score": 6, "rationale": "缺少安全扫描步骤，密钥管理需加强"},
    "maintainability": {"score": 7, "rationale": "脚本复用较好，但文档不够完整"},
    "scalability": {"score": 6, "rationale": "支持多平台构建，但环境配置分散"}
  },
  "strengths": [
    {"title": "矩阵构建策略", "description": "使用矩阵策略支持多平台并行构建", "evidence": "workflow中使用matrix配置"},
    {"title": "缓存优化", "description": "完善的缓存配置加速构建", "evidence": "配置了pip、ccache等缓存"}
  ],
  "weaknesses": [
    {"title": "缺乏安全扫描", "description": "未集成安全扫描工具", "impact": "可能存在安全漏洞", "suggestion": "集成Snyk或Trivy"}
  ],
  "recommendations": [
    {"priority": "high", "content": "添加安全扫描步骤", "expected_benefit": "提高代码安全性"},
    {"priority": "medium", "content": "优化缓存策略", "expected_benefit": "减少构建时间"}
  ]
}
```

**评分标准（1-10分）**：
- 9-10: 优秀，业界最佳实践
- 7-8: 良好，大部分实践到位
- 5-6: 一般，有明显短板
- 3-4: 较差，需要系统性改进
- 1-2: 很差，建议重构

**严格要求**：
1. 必须使用 ```json 代码块包裹
2. scores包含全部5个维度
3. strengths至少2个
4. weaknesses至少1个
5. recommendations按优先级排序（high > medium > low）

只输出JSON，不要其他内容。
"""


def _generate_script_analysis_prompts(
    raw_data: Dict,
    config: Any,
    global_context: str
) -> List[str]:
    """生成脚本分析Prompt（可能分批）
    
    改进：
    1. 添加 global_context
    2. 动态分批，同一个脚本不截断
    
    Args:
        raw_data: CI/CD 数据
        config: 配置对象
        global_context: 全局上下文
    
    Returns:
        [prompt]           # 单次传递
        [prompt_1, ...]    # 分批传递
    """
    scripts = raw_data.get("scripts", [])
    
    max_tokens = int(config.llm_max_tokens * config.max_single_prompt_ratio)
    
    # 计算固定开销
    fixed_size = len(global_context) + 2000  # global_context + prompt 模板
    
    # 动态分批
    batches = []
    current_batch = []
    current_size = fixed_size
    
    for script in scripts:
        script_size = _calculate_script_detail_size(script)
        
        # 检查是否需要新开批次
        if current_size + script_size > max_tokens and current_batch:
            batches.append(current_batch)
            current_batch = []
            current_size = fixed_size
        
        current_batch.append(script)
        current_size += script_size
    
    if current_batch:
        batches.append(current_batch)
    
    # 生成 prompt
    prompts = []
    for i, batch in enumerate(batches):
        prompt = _format_script_analysis_batch_with_context(
            batch, global_context, i + 1, len(batches)
        )
        prompts.append(prompt)
    
    return prompts


def _format_script_analysis_batch_with_context(
    scripts: List[dict],
    global_context: str,
    batch_num: int,
    total_batches: int
) -> str:
    """格式化脚本分析批次（包含 global_context）"""
    prompt = f"""# CI/CD 脚本分析 - 批次 {batch_num}/{total_batches}

**重要：本文档必须使用中文输出！**

---

{global_context}

---

## 脚本内容

"""
    
    for s in scripts:
        script_type = s.get("type", "")
        content = s.get("content", "")
        
        prompt += f"### `{s.get('path', '')}`\n\n"
        
        # 配置文件：传递内容
        if script_type in [".yaml", ".yml", ".json"]:
            if content:
                if len(content) < 50 * 1024:
                    lang = script_type[1:] if script_type else "yaml"
                    prompt += f"**内容**:\n```{lang}\n{content}\n```\n\n"
                else:
                    lang = script_type[1:] if script_type else "yaml"
                    prompt += f"**大小**: {len(content)} 字符\n"
                    prompt += f"**内容预览** (前10000字符):\n```{lang}\n{content[:10000]}\n```\n\n"
        
        # 可执行脚本：按 called_by 和内容长度决定全文/预览/元信息
        elif script_type in [".py", ".sh", ".ps1", ".bat", ".groovy"]:
            called_by = s.get("called_by", []) or []
            prompt += f"- 类型: {script_type}\n"
            if s.get("functions"):
                prompt += f"- 函数 ({len(s['functions'])}个): {', '.join(s['functions'][:20])}\n"
            if s.get("imports"):
                prompt += f"- 导入 ({len(s['imports'])}个): {', '.join(s['imports'][:20])}\n"
            if called_by:
                prompt += f"- 被调用: {', '.join(called_by[:10])}\n"

            if called_by and content:
                lang = script_type[1:] if script_type else "text"
                if len(content) <= 10000:
                    prompt += f"**内容**:\n```{lang}\n{content}\n```\n"
                else:
                    prompt += f"**大小**: {len(content)} 字符\n"
                    prompt += f"**内容预览** (前3000字符):\n```{lang}\n{content[:3000]}\n```\n"
            prompt += "\n"
    
    prompt += """---

## 输出要求

请分析以上脚本内容，输出：

### 关键配置详细分析

| 配置文件 | 作用 | 规模 |
|---------|------|------|
| ... | ... | ... |

### 脚本调用关系

- script1.sh ← workflow-a.yml
- ...

### 配置优化建议

1. ...
"""
    
    return prompt


def _estimate_script_analysis_tokens(scripts: List[dict]) -> int:
    """估算脚本分析token数"""
    total_size = 0
    
    for s in scripts:
        content = s.get("content", "")
        script_type = s.get("type")
        called_by = s.get("called_by", []) or []

        # 配置文件：完整内容或截断
        if script_type in [".yaml", ".yml", ".json"]:
            total_size += min(len(content), 50 * 1024)
        # 可执行脚本：按 called_by 和内容长度选择全文/预览/元信息
        elif script_type in [".py", ".sh", ".ps1", ".bat", ".groovy"]:
            total_size += 200
            total_size += len(script_type or "")
            total_size += len(", ".join(s.get("functions", [])[:20]))
            total_size += len(", ".join(s.get("imports", [])[:20]))
            total_size += len(", ".join(called_by[:10]))
            if called_by and content:
                if len(content) <= 10000:
                    total_size += len(content)
                else:
                    total_size += min(len(content), 3000)
        # 其他类型：预览
        else:
            total_size += min(len(content), 2000) + 200
    
    return int(total_size / 4)


def _format_script_analysis_content(scripts: List[dict]) -> str:
    """格式化脚本分析内容"""
    return _format_script_analysis_batch(scripts, 1, 1)


def _format_script_analysis_batch(scripts: List[dict], batch_num: int, total_batches: int) -> str:
    """格式化脚本分析批次"""
    prompt = f"""# CI/CD 脚本分析 - 批次 {batch_num}/{total_batches}

**重要：本文档必须使用中文输出！**

---

## 脚本内容

"""
    
    for s in scripts:
        script_type = s.get("type", "")
        content = s.get("content", "")
        
        prompt += f"### `{s.get('path', '')}`\n\n"
        
        # 配置文件：传递内容
        if script_type in [".yaml", ".yml", ".json"]:
            if content:
                if len(content) < 50 * 1024:
                    lang = script_type[1:] if script_type else "yaml"
                    prompt += f"**内容**:\n```{lang}\n{content}\n```\n\n"
                else:
                    lang = script_type[1:] if script_type else "yaml"
                    prompt += f"**大小**: {len(content)} 字符\n"
                    prompt += f"**内容预览** (前10000字符):\n```{lang}\n{content[:10000]}\n```\n\n"
        
        # 可执行脚本：按 called_by 和内容长度决定全文/预览/元信息
        elif script_type in [".py", ".sh", ".ps1", ".bat", ".groovy"]:
            called_by = s.get("called_by", []) or []
            prompt += f"- 类型: {script_type}\n"
            if s.get("functions"):
                prompt += f"- 函数 ({len(s['functions'])}个): {', '.join(s['functions'][:20])}\n"
            if s.get("imports"):
                prompt += f"- 导入 ({len(s['imports'])}个): {', '.join(s['imports'][:20])}\n"
            if called_by:
                prompt += f"- 被调用: {', '.join(called_by[:10])}\n"

            if called_by and content:
                lang = script_type[1:] if script_type else "text"
                if len(content) <= 10000:
                    prompt += f"**内容**:\n```{lang}\n{content}\n```\n"
                else:
                    prompt += f"**大小**: {len(content)} 字符\n"
                    prompt += f"**内容预览** (前3000字符):\n```{lang}\n{content[:3000]}\n```\n"
            prompt += "\n"
    
    prompt += """---

## 输出要求

请分析以上脚本内容，输出：

### 关键配置详细分析

| 配置文件 | 作用 | 规模 |
|---------|------|------|
| ... | ... | ... |

### 脚本调用关系

- script1.sh ← workflow-a.yml
- ...

### 配置优化建议

1. ...
"""
    
    return prompt


def _generate_round0_base_info(raw_data: Dict) -> str:
    """生成 Round 0 基本信息
    
    Args:
        raw_data: CI/CD 数据
    
    Returns:
        基本信息字符串
    """
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
    
    # All workflows summary
    workflows = raw_data.get("workflows", {})
    if workflows:
        context += f"### 工作流列表（共{len(workflows)}个）\n"
        for wf_name, wf in workflows.items():
            triggers = wf.get("triggers", [])
            jobs = wf.get("jobs", {})
            context += f"- {wf_name}: {len(jobs)}个Jobs, 触发: {', '.join(triggers[:3])}\n"
        context += "\n"
    
    # Scripts summary (只包含列表，不包含详细内容)
    scripts = raw_data.get("scripts", [])
    if scripts:
        context += f"### CI脚本列表（共{len(scripts)}个）\n"
        for script in scripts:
            called_by = script.get("called_by", [])
            context += f"- {script.get('path')} ({script.get('type')})"
            if called_by:
                context += f" - 被调用: {len(called_by)} 次"
            context += "\n"
        context += "\n"
    
    return context


def _format_all_scripts_for_round0(scripts: List[dict]) -> str:
    """格式化所有脚本内容（用于 Round 0）
    
    Args:
        scripts: 脚本列表
    
    Returns:
        Markdown 格式的脚本内容
    """
    result = "### CI脚本详细内容\n\n"
    result += """**关键配置识别**：
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
                    result += f"#### `{script.get('name')}`\n**内容** (前 10000 字符，文件共 {len(script_content)} 字符):\n```\n{content_to_show}\n```\n\n"
                else:
                    result += f"#### `{script.get('name')}`\n**内容**:\n```\n{script_content}\n```\n\n"
        elif script_type not in [".sh", ".py", ".ps1", ".bat", ".groovy"]:
            if script_content:
                content_preview = script_content[:2000]
                result += f"#### `{script.get('name')}`\n**内容预览**:\n```\n{content_preview}\n```\n\n"
    
    return result


def _split_scripts_by_size(scripts: List[dict], batch_count: int) -> List[List[dict]]:
    """按数量分批脚本
    
    Args:
        scripts: 脚本列表
        batch_count: 批次数量
    
    Returns:
        分批后的脚本列表
    """
    batch_size = math.ceil(len(scripts) / batch_count)
    batches = []
    for i in range(0, len(scripts), batch_size):
        batches.append(scripts[i:i + batch_size])
    return batches


def _format_external_ci_for_round0(raw_data: Dict) -> str:
    """统一格式化所有外部CI"""
    result = "## 外部 CI 系统\n\n"
    
    # 1. Jenkins Pipelines
    jenkins = raw_data.get("jenkins_pipelines", [])
    if jenkins:
        result += "### Jenkins Pipeline\n\n"
        for p in jenkins:
            result += f"#### `{p.get('name', '')}`\n"
            result += f"- 路径: `{p.get('path', '')}`\n"
            if p.get("shared_libraries"):
                result += f"- 共享库: {', '.join(p['shared_libraries'])}\n"
            if p.get("stages"):
                stages = p['stages'][:20]
                result += f"- 阶段 ({len(p['stages'])}个): {', '.join(stages)}\n"
            if p.get("function_calls"):
                funcs = p['function_calls'][:15]
                result += f"- 函数调用: {', '.join(funcs)}\n"
            if p.get("env_vars"):
                envs = p['env_vars'][:15]
                result += f"- 环境变量 ({len(p['env_vars'])}个): {', '.join(envs)}\n"
            result += "\n"
    
    # 2. Other CI Configs
    other_ci = raw_data.get("other_ci_configs", [])
    if other_ci:
        for config in other_ci:
            system = config.get("system", "Unknown")
            content = config.get("content", "")
            result += f"### {system}\n\n"
            result += f"#### `{config.get('path', '')}`\n"
            
            # 标准CI配置：结构化元信息
            if system in ["circleci", "gitlab_ci", "azure_pipelines", "travis_ci", "appveyor"]:
                parsed = config.get("parsed_data", {})
                if system == "circleci":
                    result += f"- 版本: {parsed.get('version', '-')}\n"
                    jobs = parsed.get("jobs", {})
                    result += f"- Jobs ({len(jobs)}个): {', '.join(list(jobs.keys())[:15])}\n"
                    workflows = parsed.get("workflows", {})
                    result += f"- Workflows ({len(workflows)}个): {', '.join(list(workflows.keys())[:10])}\n"
                elif system == "gitlab_ci":
                    stages = parsed.get("stages", [])
                    result += f"- 阶段 ({len(stages)}个): {', '.join(stages[:15])}\n"
                result += "\n"
            # 自定义CI配置：传递内容（方案C）
            else:
                if len(content) < 50 * 1024:
                    result += f"**内容**:\n```yaml\n{content}\n```\n\n"
                else:
                    result += f"**大小**: {len(content)} 字符\n"
                    result += f"**内容预览** (前10000字符):\n```yaml\n{content[:10000]}\n```\n\n"
    
    # 3. External CI Scripts
    ext_scripts = raw_data.get("external_ci_scripts", [])
    if ext_scripts:
        result += "### 外部 CI 调用的脚本\n\n"
        for s in ext_scripts[:20]:
            result += f"- `{s.get('path', '')}` ({s.get('type', '')})\n"
        result += "\n"
    
    return result


def _format_executable_scripts_for_round0(scripts: List[dict]) -> str:
    """格式化可执行脚本元信息（不含content）"""
    result = "## 可执行脚本\n\n"
    
    exec_scripts = [s for s in scripts 
                    if s.get("type") in [".py", ".sh", ".ps1", ".bat", ".groovy"]]
    
    if not exec_scripts:
        return result
    
    result += f"共 {len(exec_scripts)} 个\n\n"
    
    for s in exec_scripts[:30]:
        result += f"### `{s.get('name', '')}`\n"
        result += f"- 路径: `{s.get('path', '')}`\n"
        result += f"- 类型: {s.get('type', '')}\n"
        if s.get("functions"):
            funcs = s["functions"][:20]
            result += f"- 函数 ({len(s['functions'])}个): {', '.join(funcs)}\n"
        if s.get("imports"):
            imports = s["imports"][:20]
            result += f"- 导入 ({len(s['imports'])}个): {', '.join(imports)}\n"
        if s.get("called_by"):
            result += f"- 被调用: {', '.join(s['called_by'][:10])}\n"
        result += "\n"
    
    if len(exec_scripts) > 30:
        result += f"... 还有 {len(exec_scripts) - 30} 个脚本\n"
    
    return result


def _format_config_files_for_round0(scripts: List[dict]) -> str:
    """格式化配置文件"""
    result = "## 配置文件\n\n"
    
    config_scripts = [s for s in scripts 
                      if s.get("type") in [".yaml", ".yml", ".json"]]
    
    for s in config_scripts:
        content = s.get("content", "")
        result += f"### `{s.get('path', '')}`\n"
        
        if not content:
            result += "- 内容: 空\n\n"
            continue
        
        if len(content) < 50 * 1024:
            lang = s.get('type', '')[1:] if s.get('type') else 'yaml'
            result += f"**内容**:\n```{lang}\n{content}\n```\n\n"
        else:
            lang = s.get('type', '')[1:] if s.get('type') else 'yaml'
            result += f"**大小**: {len(content)} 字符\n"
            result += f"**内容预览** (前10000字符):\n```{lang}\n{content[:10000]}\n```\n\n"
    
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
