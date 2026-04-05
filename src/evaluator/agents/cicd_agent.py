"""CI/CD 分析 Agent - 分析项目的 CI/CD 架构

使用子 Agent 架构，由 CICDOrchestrator 编排各个子 Agent：

1. DataExtractionAgent: 提取 CI/CD 数据
2. AnalysisPlanningAgent: 决定处理策略
3. LLMInvocationAgent: 执行 LLM 调用
4. ResultMergingAgent: 合并结果
5. QualityCheckAgent: 质量检查
6. RetryHandlingAgent: 重试处理
7. StageOrganizationAgent: 阶段组织
8. ReportGenerationAgent: 报告生成
9. SummaryGenerationAgent: 摘要生成

编排流程：
extract → plan → invoke → merge → check → retry? → organize → report → summary
"""
from typing import Optional, Dict, Any

try:
    from evaluator.llm import LLMClient
    HAS_LLM = True
except ImportError:
    HAS_LLM = False
    LLMClient = None

try:
    from evaluator.core.interrupt import InterruptException
    HAS_INTERRUPT = True
except ImportError:
    HAS_INTERRUPT = False
    InterruptException = Exception

from evaluator.agents.base_agent import BaseAgent, AgentMeta


class CICDAgent(BaseAgent):
    """CI/CD 分析 Agent
    
    使用子 Agent 架构，提供更清晰的职责分离。
    内部使用 CICDOrchestrator 编排各个子 Agent。
    
    输入（EvaluatorState）:
    - project_path: 项目路径
    - storage_dir: 存储目录
    - display_name: 显示名称
    
    输出（EvaluatorState）:
    - cicd_analysis: 分析结果
    - errors: 错误列表
    """
    
    def __init__(self, llm: Optional["LLMClient"] = None):
        super().__init__()
        self.llm = llm
        self._orchestrator = None
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="CICDAgent",
            description="分析项目的CI/CD架构",
            category="analysis",
            inputs=["project_path", "storage_dir", "display_name"],
            outputs=["cicd_analysis", "ci_data", "errors"],
            dependencies=["LoaderAgent"],
        )
    
    def _get_orchestrator(self):
        """延迟初始化编排器"""
        if self._orchestrator is None:
            from evaluator.agents.cicd import CICDOrchestrator
            self._orchestrator = CICDOrchestrator(llm=self.llm)
        return self._orchestrator
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行 CI/CD 分析"""
        from evaluator.agents.cicd.state import to_cicd_state, from_cicd_state
        
        project_path = state.get("project_path")
        storage_dir = state.get("storage_dir")
        
        if not project_path:
            return {
                **state,
                "current_step": "cicd",
                "cicd_analysis": {"status": "failed", "error": "项目路径未设置"},
                "errors": state.get("errors", []) + ["CICDAgent: 项目路径未设置"],
            }
        
        print(f"\n{'='*50}")
        print("  CI/CD 架构分析 (Agent 架构)")
        print(f"{'='*50}")
        
        cicd_state = to_cicd_state(state)
        cicd_state["architecture_json_path"] = f"{storage_dir}/architecture.json" if storage_dir else None
        
        max_retries = 3
        result_state = None
        
        for attempt in range(max_retries):
            if attempt > 0:
                print(f"\n[CICDAgent] 完全重试 ({attempt + 1}/{max_retries})...")
            
            try:
                orchestrator = self._get_orchestrator()
                result_state = orchestrator.run(cicd_state)
                
                # 检查是否需要完全重试
                validation_result = result_state.get("validation_result", {})
                if validation_result.get("needs_retry"):
                    retry_reason = validation_result.get("retry_reason", "未知原因")
                    print(f"  [CICDAgent] 检测到需要重试: {retry_reason}")
                    continue  # 继续下一次循环，完全重试
                
                # 成功或不需要重试
                break
                
            except InterruptException:
                # 用户中断：立即停止，不重试
                print(f"\n⚠️  用户中断，停止执行")
                return {
                    **state,
                    "current_step": "cicd",
                    "cicd_analysis": {"status": "interrupted", "error": "用户中断"},
                    "errors": state.get("errors", []) + ["用户中断"],
                }
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                
                if attempt < max_retries - 1:
                    print(f"  [CICDAgent] 发生异常，准备重试...")
                    continue
                else:
                    return {
                        **state,
                        "current_step": "cicd",
                        "cicd_analysis": {"status": "failed", "error": str(e)},
                        "errors": state.get("errors", []) + [f"CICDAgent: {e}"],
                    }
        
        if result_state is None:
            return {
                **state,
                "current_step": "cicd",
                "cicd_analysis": {"status": "failed", "error": "未知错误"},
                "errors": state.get("errors", []) + ["CICDAgent: 未知错误"],
            }
        
        output_dir = storage_dir or project_path
        
        if result_state.get("errors"):
            return {
                **state,
                "current_step": "cicd",
                "cicd_analysis": {"status": "failed", "error": str(result_state.get("errors"))},
                "ci_data": result_state.get("ci_data"),
                "workflow_count": result_state.get("workflow_count", 0),
                "errors": state.get("errors", []) + result_state.get("errors", []),
            }
        
        workflow_count = result_state.get("workflow_count", 0)
        actions_count = len(result_state.get("ci_data", {}).get("actions", []))
        
        print(f"\n{'='*50}")
        print("  CI/CD 分析完成!")
        print(f"{'='*50}")
        
        return from_cicd_state(state, result_state) | {
            "current_step": "cicd",
            "cicd_analysis": {
                "status": "success",
                "workflows_count": workflow_count,
                "actions_count": actions_count,
                "ci_data_path": result_state.get("ci_data_path"),
                # 字段名映射：内部 state 使用 report_md，对外接口 cicd_analysis 使用 report_path
                # 这样保持向后兼容，同时内部代码使用统一的命名规范
                "report_path": result_state.get("report_md"),
                "architecture_json_path": result_state.get("architecture_json_path"),
                "analysis_summary_path": f"{output_dir}/analysis_summary.json",
            },
            "errors": state.get("errors", []),
        }
