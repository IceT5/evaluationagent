"""重试处理Agent - 处理重试和补充模式"""
import json
import re
from pathlib import Path
from typing import Optional, Dict, Any, List

try:
    from evaluator.llm import LLMClient
    HAS_LLM = True
except ImportError:
    HAS_LLM = False
    LLMClient = None

from .state import CICDState
from evaluator.agents.base_agent import BaseAgent, AgentMeta


class RetryHandlingAgent(BaseAgent):
    """重试处理Agent
    
    负责处理ReviewerAgent返回的重试请求：
    1. retry模式：根据问题修正报告
    2. supplement模式：补充缺失内容
    
    输入（CICDState）:
    - retry_mode: retry/supplement
    - retry_issues: 问题列表
    - cicd_existing_report: 现有报告
    - ci_data: 项目数据
    
    输出（CICDState）:
    - merged_response: 修正/补充后的响应（替换原有merged_response）
    - retry_count: 重试次数
    """
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="RetryHandlingAgent",
            description="处理重试和补充模式",
            category="analysis",
            inputs=["retry_mode", "retry_issues", "cicd_existing_report", "ci_data"],
            outputs=["merged_response", "retry_count"],
            dependencies=["QualityCheckAgent"],
        )
    
    def __init__(self, llm: Optional["LLMClient"] = None):
        super().__init__()
        self.llm = llm
    
    def run(self, state: CICDState) -> CICDState:
        """执行重试处理"""
        retry_mode = state.get("retry_mode")
        retry_issues = state.get("retry_issues", [])
        existing_report = state.get("cicd_existing_report")
        ci_data = state.get("ci_data", {})
        output_dir = state.get("storage_dir")
        
        if not retry_mode or not retry_issues:
            return state
        
        if output_dir:
            output_dir = Path(output_dir)
        else:
            output_dir = Path(state.get("project_path", "."))
        
        if retry_mode == "retry":
            llm_response = self._retry_analysis(
                ci_data, output_dir, retry_issues, existing_report
            )
            response_filename = "llm_response_retry.md"
        elif retry_mode == "supplement":
            llm_response = self._supplement_analysis(
                ci_data, output_dir, retry_issues, existing_report
            )
            response_filename = "llm_response_supplement.md"
        else:
            return state
        
        response_path = output_dir / response_filename
        response_path.write_text(llm_response, encoding="utf-8")
        
        llm_responses = [{
            "success": True,
            "response": llm_response,
            "prompt_path": response_filename,
            "index": 0,
        }]
        
        return {
            **state,
            "llm_responses": llm_responses,
            "merged_response": llm_response,
            "retry_count": state.get("retry_count", 0) + 1,
        }
    
    def _retry_analysis(
        self,
        ci_data: dict,
        output_dir: Path,
        issues: List[dict],
        existing_report: Optional[str] = None
    ) -> str:
        """重做模式：根据问题修正报告"""
        print("\n[Retry Step] 生成修正 Prompt...")
        
        issues_text = []
        for i, issue in enumerate(issues[:10], 1):
            issues_text.append(f"{i}. {issue.get('message', '未知问题')}")
            if issue.get('workflow'):
                issues_text.append(f"   工作流: {issue['workflow']}")
            if issue.get('expected'):
                issues_text.append(f"   正确内容: {issue['expected']}")
            if issue.get('actual'):
                issues_text.append(f"   报告内容: {issue['actual']}")
        
        issues_str = "\n".join(issues_text)
        
        workflow_count = len(ci_data.get('workflows', {}))
        job_count = sum(len(wf.get('jobs', {})) for wf in ci_data.get('workflows', {}).values())
        
        prompt = f"""你是一个 CI/CD 报告审核员。之前的报告存在以下问题，请修正：

## 需要修正的问题
{issues_str}

## 原始报告摘要
{existing_report[:8000] if existing_report else '(无)'}

## 修正要求
1. 修正报告中与实际项目不符的内容
2. 保持报告的整体结构和格式
3. 确保所有工作流、Job、触发条件等信息与实际项目一致
4. 只输出修正后的完整报告，不要说明修改了哪些内容

## 项目数据
- 工作流数量: {workflow_count}
- Job 总数: {job_count}

请输出修正后的完整报告："""
        
        print("  正在调用 LLM 修正报告...")
        llm_response = self.llm.chat(prompt)
        print(f"  修正完成 ({len(llm_response)} 字符)")
        
        return llm_response
    
    def _supplement_analysis(
        self,
        ci_data: dict,
        output_dir: Path,
        issues: List[dict],
        existing_report: Optional[str] = None
    ) -> str:
        """补充模式：基于现有报告补充缺失内容"""
        print("\n[Supplement Step] 生成补充 Prompt...")
        
        supplement_text = []
        for i, issue in enumerate(issues[:10], 1):
            msg = issue.get('message', '内容不够详尽')
            suggestion = issue.get('suggestion', '')
            workflow = issue.get('workflow', '')
            
            supplement_text.append(f"{i}. {msg}")
            if workflow:
                supplement_text.append(f"   工作流: {workflow}")
            if suggestion:
                supplement_text.append(f"   建议: {suggestion}")
        
        supplement_str = "\n".join(supplement_text)
        
        missing_workflows = []
        for issue in issues:
            if issue.get('type') in ['missing_workflow_detail', 'weak_analysis'] and issue.get('workflow'):
                if issue['workflow'] not in missing_workflows:
                    missing_workflows.append(issue['workflow'])
        
        workflows_detail = {}
        for wf_name in missing_workflows:
            if wf_name in ci_data.get('workflows', {}):
                workflows_detail[wf_name] = ci_data['workflows'][wf_name]
        
        workflows_json = json.dumps(workflows_detail, ensure_ascii=False, indent=2)
        
        prompt = f"""你是一个 CI/CD 报告审核员。之前的报告内容不够详尽，请补充：

## 需要补充的内容
{supplement_str}

## 现有报告
{existing_report[:6000] if existing_report else '(无)'}

## 需要详细分析的工作流数据
{workflows_json}

## 补充要求
1. 补充缺失的工作流详细分析
2. 扩展现有分析不够详尽的部分
3. 确保关键发现和建议充分（至少3条有价值的建议）
4. 保持报告的整体结构和格式
5. 只输出补充后的完整报告，不要输出 JSON 架构数据

请输出补充后的完整报告："""
        
        print("  正在调用 LLM 补充内容...")
        llm_response = self.llm.chat(prompt)
        print(f"  补充完成 ({len(llm_response)} 字符)")
        
        return llm_response
