"""修复途径 - 数据提取、LLM生成"""
from abc import ABC, abstractmethod
from typing import Dict, Any
import json


class FixMethod(ABC):
    """修复途径基类"""
    
    @abstractmethod
    def generate_content(self, issue: Dict, context: Dict) -> str:
        """生成修复内容"""
        pass
    
    @abstractmethod
    def can_fix(self, issue_type: str) -> bool:
        """判断是否能处理该问题类型"""
        pass


class DataFixMethod(FixMethod):
    """数据修复途径 - 从 ci_data.json 提取"""
    
    SUPPORTED_TYPES = {
        "trigger_missing",
        "job_fake",
        "workflow_fake",
        "trigger_fabricated",
        "script_fake",
    }
    
    def __init__(self, ci_data: Dict):
        self.ci_data = ci_data
    
    def can_fix(self, issue_type: str) -> bool:
        return issue_type in self.SUPPORTED_TYPES
    
    def generate_content(self, issue: Dict, context: Dict) -> str:
        issue_type = issue.get("type")
        
        if issue_type == "trigger_missing":
            return self._gen_trigger_content(issue)
        elif issue_type == "script_fake":
            return self._gen_script_fix_content(issue)
        elif issue_type in ["job_fake", "workflow_fake", "trigger_fabricated"]:
            return ""
        
        return ""
    
    def _gen_trigger_content(self, issue: Dict) -> str:
        """从 ci_data.json 提取触发条件"""
        wf_name = issue.get("workflow")
        trigger = issue.get("entity")
        
        workflows = self.ci_data.get("workflows", {})
        wf_data = workflows.get(wf_name, {})
        trigger_config = wf_data.get("trigger_config", {})
        trigger_data = trigger_config.get(trigger, {})
        
        return self._format_trigger_yaml(trigger, trigger_data)
    
    def _format_trigger_yaml(self, trigger: str, data: Dict) -> str:
        """格式化触发条件为 YAML"""
        if not data:
            return f"\n  {trigger}:\n"
        
        lines = [f"\n  {trigger}:"]
        for key, value in data.items():
            if isinstance(value, list):
                lines.append(f"    {key}:")
                for v in value:
                    lines.append(f"      - {v}")
            elif isinstance(value, dict):
                lines.append(f"    {key}:")
                for k, v in value.items():
                    lines.append(f"      {k}: {v}")
            else:
                lines.append(f"    {key}: {value}")
        
        return "\n".join(lines) + "\n"
    
    def _gen_script_fix_content(self, issue: Dict) -> str:
        """修正脚本路径"""
        script_path = issue.get("entity", "")
        scripts = self.ci_data.get("scripts", [])
        
        from pathlib import Path
        script_name = Path(script_path).name
        
        for s in scripts:
            s_path = s.get("path", "")
            if script_name in s_path:
                return s_path
        
        return script_path


class LLMFixMethod(FixMethod):
    """LLM 修复途径 - 调用 LLM 生成"""

    SUPPORTED_TYPES = {
        "workflow_missing",
        "job_missing",
        "missing_workflow_detail",
        "missing_job_detail",
    }
    
    def __init__(self, llm_client):
        self.llm = llm_client
    
    def can_fix(self, issue_type: str) -> bool:
        return issue_type in self.SUPPORTED_TYPES
    
    def generate_content(self, issue: Dict, context: Dict) -> str:
        if not self.llm:
            return ""
        
        issue_type = issue.get("type")
        
        if issue_type == "workflow_missing":
            return self._gen_workflow_description(issue, context)
        elif issue_type == "job_missing":
            return self._gen_job_description(issue, context)
        elif issue_type == "missing_workflow_detail":
            return self._gen_workflow_detail(issue, context)
        elif issue_type == "missing_job_detail":
            return self._gen_missing_job_detail(issue, context)
        elif issue_type == "weak_analysis":
            return self._gen_step_supplement(issue, context)

        return ""
    
    def _gen_workflow_description(self, issue: Dict, context: Dict) -> str:
        """生成工作流描述"""
        wf_name = issue.get("entity")
        ci_data = context.get("ci_data", {})
        wf_data = ci_data.get("workflows", {}).get(wf_name, {})
        
        prompt = f"""为以下工作流生成详细描述（只输出该工作流的描述，不要输出其他内容）：

工作流名称：{wf_name}

工作流数据：
```json
{json.dumps(wf_data, ensure_ascii=False, indent=2)}
```

输出格式：
#### X.X {wf_name}
**目的**: xxx

**触发条件**:
```yaml
xxx
```

**包含的Job**（共X个）:
| 序号 | Job名称 | 运行环境 | 目的 |
|-----|---------|---------|------|
| 1 | job1 | ubuntu-latest | 描述 |

**依赖关系**: job1 → job2

**执行步骤详情**:
- Job 1: job1
  - 步骤1: xxx
"""
        
        try:
            return self.llm.chat(prompt)
        except Exception as e:
            print(f"  [WARN] LLM 生成工作流描述失败: {e}")
            return ""
    
    def _gen_job_description(self, issue: Dict, context: Dict) -> str:
        """生成 Job 描述"""
        wf_name = issue.get("workflow")
        job_name = issue.get("entity")
        ci_data = context.get("ci_data", {})
        job_data = ci_data.get("workflows", {}).get(wf_name, {}).get("jobs", {}).get(job_name, {})
        
        prompt = f"""为以下 Job 生成描述（只输出表格行，不要输出其他内容）：

工作流：{wf_name}
Job名称：{job_name}

Job数据：
```json
{json.dumps(job_data, ensure_ascii=False, indent=2)}
```

输出格式（表格行）：
| X | {job_name} | ubuntu-latest | 描述 |
"""
        
        try:
            return self.llm.chat(prompt)
        except Exception as e:
            print(f"  [WARN] LLM 生成 Job 描述失败: {e}")
            return ""
    
    def _gen_workflow_detail(self, issue: Dict, context: Dict) -> str:
        """生成工作流详细分析"""
        wf_name = issue.get("workflow")
        ci_data = context.get("ci_data", {})
        wf_data = ci_data.get("workflows", {}).get(wf_name, {})
        
        prompt = f"""为以下工作流生成详细分析（只输出分析内容，不要输出其他内容）：

工作流名称：{wf_name}

工作流数据：
```json
{json.dumps(wf_data, ensure_ascii=False, indent=2)}
```

输出格式：
**执行步骤详情**:
- Job 1: job1
  - 步骤1: xxx
  - 步骤2: xxx
"""
        
        try:
            return self.llm.chat(prompt)
        except Exception as e:
            print(f"  [WARN] LLM 生成工作流详细分析失败: {e}")
            return ""

    def _gen_missing_job_detail(self, issue: Dict, context: Dict) -> str:
        """补充缺失的 Job 详细分析"""
        ci_data = context.get("ci_data", {})
        workflows = ci_data.get("workflows", {})

        # 收集所有 Job 数据用于补充
        all_jobs_info = []
        for wf_name, wf_data in workflows.items():
            for job_name, job_data in wf_data.get("jobs", {}).items():
                all_jobs_info.append({
                    "workflow": wf_name,
                    "job": job_name,
                    "data": job_data,
                })

        prompt = f"""以下是 CI/CD 项目中所有 Job 的数据，请为每个 Job 补充详细的执行步骤分析。
只输出补充内容，不要输出其他说明。

Job 数据：
```json
{json.dumps(all_jobs_info, ensure_ascii=False, indent=2)}
```

输出格式（为每个 Job 输出）：
- Job: <job_name>（工作流: <workflow_name>）
  - 步骤1: <步骤名称> - <步骤说明>
  - 步骤2: <步骤名称> - <步骤说明>
"""
        try:
            return self.llm.chat(prompt)
        except Exception as e:
            print(f"  [WARN] LLM 生成 Job 详细分析失败: {e}")
            return ""

    def _gen_step_supplement(self, issue: Dict, context: Dict) -> str:
        """补充步骤详情（weak_analysis 修复）"""
        ci_data = context.get("ci_data", {})
        workflows = ci_data.get("workflows", {})
        message = issue.get("message", "")

        # 提取所有步骤数据
        steps_info = {}
        for wf_name, wf_data in workflows.items():
            steps_info[wf_name] = {}
            for job_name, job_data in wf_data.get("jobs", {}).items():
                steps = job_data.get("steps", [])
                steps_info[wf_name][job_name] = steps

        prompt = f"""报告中步骤详情覆盖率不足（{message}），请根据以下 CI/CD 数据补充所有工作流的步骤详情分析。
只输出补充的步骤分析内容，不要输出其他说明。

步骤数据：
```json
{json.dumps(steps_info, ensure_ascii=False, indent=2)}
```

输出格式（按工作流和 Job 组织）：
**执行步骤详情补充**:

工作流: <workflow_name>
- Job: <job_name>
  - 步骤1: <步骤名称> - <步骤说明>
  - 步骤2: <步骤名称> - <步骤说明>
"""
        try:
            return self.llm.chat(prompt)
        except Exception as e:
            print(f"  [WARN] LLM 补充步骤详情失败: {e}")
            return ""