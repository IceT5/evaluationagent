"""CI/CD 编排器 - 编排各个子 Agent

新的编排流程：
extract → plan → invoke → merge → check → organize → report → summary → END

可选分支：
- retry: 如果需要重试 (retry/supplement模式)
"""
from typing import Optional, Dict, Any, Literal

try:
    from langgraph.graph import StateGraph, END
    HAS_LANGGRAPH = True
except ImportError:
    HAS_LANGGRAPH = False

try:
    from evaluator.llm import LLMClient
    HAS_LLM = True
except ImportError:
    HAS_LLM = False
    LLMClient = None

from evaluator.agents.base_agent import BaseAgent, AgentMeta
from evaluator.state import EvaluatorState
from .data_extraction_agent import DataExtractionAgent
from .analysis_planning_agent import AnalysisPlanningAgent
from .llm_invocation_agent import LLMInvocationAgent
from .result_merging_agent import ResultMergingAgent
from .quality_check_agent import QualityCheckAgent
from .retry_handling_agent import RetryHandlingAgent
from .stage_organization_agent import StageOrganizationAgent
from .report_generation_agent import ReportGenerationAgent, SummaryGenerationAgent


class CICDOrchestrator(BaseAgent):
    """CI/CD 分析编排器
    
    使用 LangGraph 编排以下 Agent：
    - DataExtractionAgent: 数据提取
    - AnalysisPlanningAgent: 策略规划
    - LLMInvocationAgent: LLM 调用
    - ResultMergingAgent: 结果合并
    - QualityCheckAgent: 质量检查
    - RetryHandlingAgent: 重试处理（retry/supplement模式）
    - StageOrganizationAgent: 阶段组织
    - ReportGenerationAgent: 报告生成
    - SummaryGenerationAgent: 摘要生成
    
    编排流程：
    extract → plan → invoke → merge → check → retry? → organize → report → summary → END
    """
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="CICDOrchestrator",
            description="编排CI/CD分析子Agent",
            category="orchestration",
            inputs=["project_path", "storage_dir", "display_name"],
            outputs=["cicd_analysis", "report_md", "architecture_json"],
            dependencies=[
                "DataExtractionAgent",
                "AnalysisPlanningAgent",
                "LLMInvocationAgent",
                "ResultMergingAgent",
                "QualityCheckAgent",
                "RetryHandlingAgent",
                "StageOrganizationAgent",
                "ReportGenerationAgent",
                "SummaryGenerationAgent",
            ],
        )
    
    def __init__(self, llm: Optional["LLMClient"] = None):
        super().__init__()
        self.llm = llm
        self._init_agents()
        
        if HAS_LANGGRAPH:
            self.graph = self._create_graph()
        else:
            self.graph = None
    
    def _init_agents(self):
        """初始化所有子Agent"""
        self.data_extraction = DataExtractionAgent()
        self.planning = AnalysisPlanningAgent()
        self.invocation = LLMInvocationAgent(self.llm)
        self.merging = ResultMergingAgent()
        self.quality_check = QualityCheckAgent(self.llm)
        self.retry_handling = RetryHandlingAgent(self.llm)
        self.stage_organization = StageOrganizationAgent()
        self.report_generation = ReportGenerationAgent()
        self.summary_generation = SummaryGenerationAgent()
    
    def _create_graph(self):
        """创建 LangGraph 工作流"""
        if not HAS_LANGGRAPH:
            return None
        
        workflow = StateGraph(EvaluatorState)
        
        workflow.add_node("extract", self._wrap(self.data_extraction))
        workflow.add_node("plan", self._wrap(self.planning))
        workflow.add_node("invoke", self._wrap(self.invocation))
        workflow.add_node("merge", self._wrap(self.merging))
        workflow.add_node("check", self._wrap(self.quality_check))
        workflow.add_node("organize", self._wrap(self.stage_organization))
        workflow.add_node("retry", self._wrap(self.retry_handling))
        workflow.add_node("report", self._wrap(self.report_generation))
        workflow.add_node("summary", self._wrap(self.summary_generation))
        
        workflow.set_entry_point("extract")
        
        workflow.add_conditional_edges(
            "extract",
            self._route_after_extract,
            {"skip": END, "continue": "plan"}
        )
        
        workflow.add_conditional_edges(
            "plan",
            self._route_after_plan,
            {"skip": END, "continue": "invoke"}
        )
        
        workflow.add_edge("invoke", "merge")
        workflow.add_edge("merge", "check")
        
        workflow.add_conditional_edges(
            "check",
            self._route_after_check,
            {
                "retry": "retry",
                "organize": "organize",
                "fail": END,
            }
        )
        
        workflow.add_conditional_edges(
            "retry",
            self._route_after_retry,
            {"invoke": "invoke", "fail": END}
        )
        
        workflow.add_edge("organize", "report")
        workflow.add_edge("report", "summary")
        workflow.add_edge("summary", END)
        
        return workflow.compile()
    
    def _wrap(self, agent):
        """包装 Agent 以适配 LangGraph
        
        使用 safe_run() 确保：
        - 完整的trace支持
        - 输入验证
        - 错误处理
        - 中断支持
        """
        def wrapper(state: EvaluatorState) -> EvaluatorState:
            return agent.safe_run(state)
        return wrapper
    
    def _route_after_extract(self, state: EvaluatorState) -> Literal["skip", "continue"]:
        """提取后的路由"""
        if state.get("strategy") == "skip" or state.get("workflow_count", 0) == 0:
            return "skip"
        return "continue"
    
    def _route_after_plan(self, state: EvaluatorState) -> Literal["skip", "continue"]:
        """规划后的路由"""
        if state.get("strategy") == "skip":
            return "skip"
        return "continue"
    
    def _route_after_check(self, state: EvaluatorState) -> Literal["retry", "organize", "fail"]:
        """质量检查后的路由"""
        # 新增：检查 validation_result.needs_retry
        validation_result = state.get("validation_result", {})
        if validation_result.get("needs_retry"):
            retry_reason = validation_result.get("retry_reason", "未知原因")
            print(f"  [Orchestrator] 需要完全重试: {retry_reason}")
            return "fail"  # 直接返回fail，让上层完全重试
        
        retry_mode = state.get("retry_mode")
        retry_issues = state.get("retry_issues", [])
        errors = state.get("errors", [])
        
        if retry_mode in ("retry", "supplement") and retry_issues:
            return "retry"
        
        if errors and len(errors) > 0:
            retry_count = state.get("retry_count", 0)
            max_retries = state.get("max_retries", 3)
            if retry_count < max_retries:
                return "retry"
            return "fail"
        
        return "organize"
    
    def _route_after_retry(self, state: EvaluatorState) -> Literal["invoke", "fail"]:
        """重试处理后的路由"""
        retry_count = state.get("retry_count", 0)
        max_retries = state.get("max_retries", 3)
        
        if retry_count < max_retries:
            return "invoke"
        return "fail"
    
    def run(self, state: EvaluatorState) -> EvaluatorState:
        """执行 CI/CD 分析"""
        retry_mode = state.get("retry_mode")
        retry_issues = state.get("retry_issues", [])
        
        print(f"  [Orchestrator] retry_mode={retry_mode}, retry_issues_count={len(retry_issues)}")
        
        if retry_mode in ("supplement", "retry") and retry_issues:
            print(f"  [Orchestrator] 进入{retry_mode}模式，使用顺序执行")
            return self._run_sequential(state)
        
        if self.graph:
            print(f"  [Orchestrator] 使用 LangGraph 执行")
            return self.graph.invoke(state)
        
        print(f"  [Orchestrator] 使用顺序执行")
        return self._run_sequential(state)
    
    # TODO: 待讨论是否移除此方法
    # 当前用途：
    # 1. retry/supplement模式使用顺序执行
    # 2. LangGraph不可用时的fallback
    # 问题：
    # - 项目要求必须使用LangGraph编排
    # - retry模式是否也应该使用LangGraph？
    # 建议：评估后决定是否移除
    def _run_sequential(self, state: EvaluatorState) -> EvaluatorState:
        """顺序执行（无 LangGraph 时）
        
        TODO: 待讨论是否移除此方法
        - 如果项目强制使用LangGraph，此方法可能不需要
        - 但retry模式当前使用顺序执行，需要评估
        """
        retry_mode = state.get("retry_mode")
        retry_issues = state.get("retry_issues", [])
        
        if retry_mode == "supplement" and retry_issues:
            print("  [Retry] 补充模式：跳过数据提取和规划，直接补充缺失内容")
            state = self.retry_handling.safe_run(state)
            state = self.merging.safe_run(state)
            state = self.quality_check.safe_run(state)
            
            if not state.get("errors"):
                state = self.stage_organization.safe_run(state)
                state = self.report_generation.safe_run(state)
                state = self.summary_generation.safe_run(state)
            
            return state
        
        state = self.data_extraction.safe_run(state)
        
        if state.get("strategy") == "skip":
            return state
        
        state = self.planning.safe_run(state)
        
        if state.get("strategy") == "skip":
            return state
        
        state = self.invocation.safe_run(state)
        state = self.merging.safe_run(state)
        state = self.quality_check.safe_run(state)
        
        # 新增：检查 validation_result.needs_retry
        validation_result = state.get("validation_result", {})
        if validation_result.get("needs_retry"):
            retry_reason = validation_result.get("retry_reason", "未知原因")
            print(f"  [Orchestrator] 需要完全重试: {retry_reason}")
            # 标记失败，让上层完全重试
            state["errors"] = state.get("errors", []) + [f"需要完全重试: {retry_reason}"]
            return state
        
        if retry_mode == "retry" and retry_issues:
            state = self.retry_handling.safe_run(state)
            state = self.invocation.safe_run(state)
        
        if not state.get("errors"):
            state = self.stage_organization.safe_run(state)
            state = self.report_generation.safe_run(state)
            state = self.summary_generation.safe_run(state)
        
        return state
