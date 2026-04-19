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


class BatchInputBuildAgent(BaseAgent):
    """分批输入构建节点：当前实现直接透传 batch_input_context。"""

    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="BatchInputBuildAgent",
            description="构建分批输入契约对象",
            category="analysis",
            inputs=["batch_input_context"],
            outputs=["batch_input_context"],
            dependencies=["LLMInvocationAgent"],
        )

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        return state


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
    
    def __init__(self, llm: Optional[Any] = None):
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
        self.batch_input_build = BatchInputBuildAgent()
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
        workflow.add_node("build_batch_input", self._wrap(self.batch_input_build))
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
        
        workflow.add_edge("invoke", "build_batch_input")

        workflow.add_conditional_edges(
            "build_batch_input",
            self._route_after_batch_input,
            {
                "retry": "retry",
                "merge": "merge",
            }
        )

        workflow.add_edge("merge", "check")
        
        workflow.add_conditional_edges(
            "check",
            self._route_after_check,
            {
                "retry": "retry",
                "organize": "organize",
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
        def wrapper(state):
            return agent.safe_run(state)
        return wrapper
    
    def _route_after_extract(self, state: Dict[str, Any]) -> Literal["skip", "continue"]:
        """提取后的路由"""
        if state.get("strategy") == "skip" or state.get("workflow_count", 0) == 0:
            return "skip"
        return "continue"
    
    def _route_after_plan(self, state: Dict[str, Any]) -> Literal["skip", "continue"]:
        """规划后的路由"""
        if state.get("strategy") == "skip":
            return "skip"
        return "continue"
    
    def _route_after_check(self, state: Dict[str, Any]) -> Literal["retry", "organize"]:
        """质量检查后的路由：只依赖 contract_check_result 和 validation_result"""
        contract_check_result = state.get("contract_check_result", {})
        if contract_check_result.get("status") == "failed":
            return "retry"

        validation_result = state.get("validation_result", {})
        if validation_result.get("needs_retry"):
            return "retry"

        return "organize"

    def _route_after_batch_input(self, state: Dict[str, Any]) -> Literal["retry", "merge"]:
        batch_input_context = state.get("batch_input_context", {})
        if batch_input_context.get("context_status") == "ready":
            return "merge"
        return "retry"
    
    def _route_after_retry(self, state: Dict[str, Any]) -> Literal["invoke", "fail"]:
        """重试处理后的路由"""
        retry_result = state.get("cicd_retry_result", {})
        if not retry_result.get("requested"):
            return "fail"
        if retry_result.get("exhausted"):
            return "fail"
        return "invoke"
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行 CI/CD 分析"""
        if self.graph:
            print(f"  [Orchestrator] 使用 LangGraph 执行")
            return self.graph.invoke(state)

        print(f"  [Orchestrator] LangGraph 不可用，返回失败")
        return {
            **state,
            "errors": state.get("errors", []) + ["CICDOrchestrator: LangGraph 不可用，禁止回退到 run_sequential"],
        }
