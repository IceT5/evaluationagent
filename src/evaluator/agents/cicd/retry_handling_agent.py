"""重试处理Agent - 处理重试和补充模式"""
import json
from pathlib import Path
from typing import Optional, Dict, Any, List

from evaluator.agents.base_agent import BaseAgent, AgentMeta


class RetryHandlingAgent(BaseAgent):
    """重试处理Agent
    
    负责处理ReviewerAgent返回的重试请求：
    1. retry模式：根据问题修正报告
    2. supplement模式：补充缺失内容
    
    输入（EvaluatorState）:
    - retry_mode: retry/supplement
    - retry_issues: 问题列表
    - cicd_existing_report: 现有报告
    - ci_data: 项目数据
    
    输出（EvaluatorState）:
    - merged_response: 修正/补充后的响应（替换原有merged_response）
    - cicd_retry_count: 重试次数
    """
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="RetryHandlingAgent",
            description="处理重试和补充模式",
            category="analysis",
            inputs=["ci_data"],
            outputs=["merged_response", "cicd_retry_count"],
            dependencies=["QualityCheckAgent"],
        )
    
    def __init__(self, llm: Optional[Any] = None):
        super().__init__()
        self.llm = llm
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行重试处理"""
        contract_check_result = state.get("contract_check_result") or {}
        validation_result = state.get("validation_result") or {}
        cicd_failure_data = state.get("cicd_failure_data") or {}

        generated_retry_result = self._build_retry_result(
            state=state,
            contract_check_result=contract_check_result,
            validation_result=validation_result,
            cicd_failure_data=cicd_failure_data,
        )
        next_retry_count = generated_retry_result.get("attempt_count", state.get("cicd_retry_count", 0))

        retry_mode = state.get("retry_mode")
        retry_issues = state.get("retry_issues", [])
        existing_report = state.get("cicd_existing_report")
        ci_data = state.get("ci_data") or {}
        output_dir = state.get("storage_dir")
        
        if not retry_mode or not retry_issues:
            return {
                **state,
                "cicd_retry_count": next_retry_count,
                "cicd_retry_result": generated_retry_result,
            }
        
        if output_dir:
            output_dir = Path(output_dir)
        else:
            output_dir = Path(str(state.get("project_path", ".")))
        
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
            return {**state, "cicd_retry_result": generated_retry_result}
        
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
            "cicd_retry_count": next_retry_count,
            "cicd_retry_result": generated_retry_result,
        }

    def _build_retry_result(
        self,
        state: Dict[str, Any],
        contract_check_result: Dict[str, Any],
        validation_result: Dict[str, Any],
        cicd_failure_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        review_result = state.get("review_result") or {}
        requested = False
        trigger_source = ""
        retry_reason = ""
        failure_scope = ""
        retry_entry_stage = ""
        retry_mode = ""

        if contract_check_result.get("status") == "failed":
            requested = True
            trigger_source = "contract_check"
            retry_reason = "; ".join(contract_check_result.get("issues", [])) or "contract_check_failed"
            failure_scope = "contract"
            retry_entry_stage = "multi_round"
            retry_mode = "rerun_multi_round"
        elif validation_result.get("needs_retry"):
            requested = True
            trigger_source = "quality_check"
            retry_reason = validation_result.get("retry_reason", "final_validation_failed")
            failure_scope = validation_result.get("failure_scope", "final_validation")
            retry_entry_stage = "assembly" if failure_scope == "final_validation" else "batch_execute"
            retry_mode = "reassemble" if failure_scope == "final_validation" else "rerun_batch"
        elif review_result.get("status") in {"critical", "incomplete"}:
            requested = True
            trigger_source = "review"
            retry_reason = review_result.get("message", "review_requested_retry")
            failure_scope = "review"
            retry_entry_stage = "report_generation"
            retry_mode = "rerender_report"
        elif cicd_failure_data:
            requested = True
            trigger_source = "graph_guard"
            retry_reason = cicd_failure_data.get("reason", "cicd_failure")
            failure_scope = cicd_failure_data.get("failure_scope", "execution")
            retry_entry_stage = "batch_execute"
            retry_mode = "rerun_batch"
        else:
            # 检测 batch_input_context 不完整（architecture_json 提取失败）
            batch_ctx = state.get("batch_input_context") or {}
            if batch_ctx.get("context_status") == "incomplete":
                requested = True
                trigger_source = "batch_input_incomplete"
                retry_reason = "architecture_json 提取失败，需要重新执行多轮分析"
                failure_scope = "multi_round"
                retry_entry_stage = "multi_round"
                retry_mode = "rerun_multi_round"

        current_attempt_count = state.get("cicd_retry_count", 0)
        max_attempts = state.get("max_retries", 3)
        attempt_count = current_attempt_count + 1 if requested else current_attempt_count
        exhausted = requested and attempt_count > max_attempts

        return {
            "requested": requested,
            "retry_mode": retry_mode,
            "trigger_source": trigger_source,
            "retry_reason": retry_reason,
            "failure_scope": failure_scope,
            "retry_entry_stage": retry_entry_stage,
            "attempt_count": attempt_count,
            "max_attempts": max_attempts,
            "exhausted": exhausted,
            "blocking_error": None,
            "retry_context_data": {
                "contract_check_result": contract_check_result,
                "validation_result": validation_result,
                "review_result": review_result,
            },
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
        if self.llm is None:
            raise RuntimeError("LLM 客户端未初始化")
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
        if self.llm is None:
            raise RuntimeError("LLM 客户端未初始化")
        llm_response = self.llm.chat(prompt)
        print(f"  补充完成 ({len(llm_response)} 字符)")
        
        return llm_response
