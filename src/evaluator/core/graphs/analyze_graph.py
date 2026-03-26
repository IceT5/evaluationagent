"""分析工作流图定义"""
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

from evaluator.state import EvaluatorState
from storage.manager import StorageManager
from evaluator.core.routes import route_by_orchestrator, prepare_cicd_retry


def _get_agents():
    """延迟导入 Agent 避免循环依赖"""
    from evaluator.agents import (
        InputAgent,
        LoaderAgent,
        CICDAgent,
        ReviewerAgent,
        ReporterAgent,
        OrchestratorAgent,
    )
    return InputAgent, LoaderAgent, CICDAgent, ReviewerAgent, ReporterAgent, OrchestratorAgent


def create_analyze_graph(
    llm_config: Optional[Dict[str, Any]] = None,
    storage_dir: Optional[str] = None,
    ui_manager: Optional[Any] = None,
    use_orchestrator: bool = True,
    user_input: Optional[str] = None,
    download_dir: Optional[str] = None,
    use_cicd_facade: bool = False,
) -> Any:
    """创建分析工作流 - 支持使用 OrchestratorAgent
    
    工作流定义（使用 OrchestratorAgent）：
    orchestrator → input → orchestrator → loader → orchestrator → 
    cicd → orchestrator → reviewer → orchestrator → reporter → END
    
    工作流定义（不使用 OrchestratorAgent）：
    input → loader → cicd → reviewer → reporter
    
    Args:
        llm_config: LLM 配置
        storage_dir: 存储目录
        ui_manager: UI 管理器（未使用，保留接口）
        use_orchestrator: 是否使用 OrchestratorAgent（默认 True）
        user_input: 可选，直接传入用户输入
        download_dir: 可选，指定下载目录
        use_cicd_facade: 是否使用 CICD 门面模式（默认 False）
    
    Returns:
        编译后的图
    """
    if not HAS_LANGGRAPH:
        return None
    
    InputAgent, LoaderAgent, CICDAgent, ReviewerAgent, ReporterAgent, OrchestratorAgent = _get_agents()
    
    llm = None
    if llm_config and HAS_LLM:
        try:
            llm = LLMClient(**llm_config)
        except Exception:
            pass
    
    storage = StorageManager(data_dir=storage_dir) if storage_dir else StorageManager()
    orchestrator = OrchestratorAgent(llm=llm)
    
    input_agent = InputAgent(user_input=user_input)
    loader_agent = LoaderAgent(download_dir=download_dir, storage_manager=storage)
    cicd_agent = CICDAgent(llm=llm, use_facade=use_cicd_facade)
    reviewer_agent = ReviewerAgent(llm=llm)
    reporter_agent = ReporterAgent(storage_manager=storage)

    workflow = StateGraph(EvaluatorState)

    workflow.add_node("orchestrator", _create_orchestrator_node(orchestrator))
    workflow.add_node("input", lambda state: input_agent.run(state))
    workflow.add_node("loader", lambda state: loader_agent.run(state))
    workflow.add_node("cicd", _create_cicd_node(cicd_agent))
    workflow.add_node("reviewer", lambda state: reviewer_agent.run(state))
    workflow.add_node("reporter", lambda state: reporter_agent.run(state))

    if use_orchestrator:
        return _create_orchestrated_graph(workflow)
    else:
        return _create_simple_graph(workflow)


def _create_orchestrator_node(orchestrator):
    """创建 OrchestratorAgent 节点"""
    def node(state: EvaluatorState) -> EvaluatorState:
        result = orchestrator.run(state)
        
        completed = state.get("completed_steps", [])
        current = state.get("current_step")
        if current:
            completed.append(current)
            result["completed_steps"] = completed
        
        return result
    return node


def _create_cicd_node(cicd_agent):
    """创建 CICD 节点，处理重试状态更新"""
    def node(state: EvaluatorState) -> EvaluatorState:
        retry_mode = state.get("cicd_retry_mode")
        if retry_mode and state.get("review_result"):
            retry_updates = prepare_cicd_retry(state)
            state = {**state, **retry_updates}
        
        result = cicd_agent.run(state)
        return result
    return node


def _create_orchestrated_graph(workflow):
    """创建使用 OrchestratorAgent 的工作流"""
    workflow.set_entry_point("orchestrator")
    
    workflow.add_conditional_edges(
        "orchestrator",
        route_by_orchestrator,
        {
            "input": "input",
            "loader": "loader",
            "cicd": "cicd",
            "reviewer": "reviewer",
            "reporter": "reporter",
            "end": END,
        }
    )
    
    workflow.add_edge("input", "orchestrator")
    workflow.add_edge("loader", "orchestrator")
    workflow.add_edge("cicd", "orchestrator")
    workflow.add_edge("reviewer", "orchestrator")
    workflow.add_edge("reporter", END)
    
    return workflow.compile()


def _create_simple_graph(workflow):
    """创建简单工作流（不使用 OrchestratorAgent）"""
    workflow.add_node("error_handler", _create_error_handler())
    workflow.add_node("skip", _create_skip_node())

    workflow.set_entry_point("input")
    
    workflow.add_conditional_edges("input", _route_after_input, {
        "loader": "loader",
        "error_handler": "error_handler",
    })
    
    workflow.add_conditional_edges("loader", _route_after_loader, {
        "cicd": "cicd",
        "error_handler": "error_handler",
    })
    
    workflow.add_conditional_edges("cicd", _route_after_cicd, {
        "reviewer": "reviewer",
        "error_handler": "error_handler",
        "skip": "skip",
    })
    
    workflow.add_conditional_edges("reviewer", _route_after_review, {
        "reporter": "reporter",
        "cicd": "cicd",
        "error_handler": "error_handler",
    })
    
    workflow.add_edge("reporter", END)
    workflow.add_edge("skip", END)
    workflow.add_edge("error_handler", END)
    
    return workflow.compile()


def _route_after_input(state: EvaluatorState) -> Literal["loader", "error_handler"]:
    if state.get("errors"):
        return "error_handler"
    return "loader"


def _route_after_loader(state: EvaluatorState) -> Literal["cicd", "error_handler"]:
    if state.get("errors"):
        return "error_handler"
    return "cicd"


def _route_after_cicd(state: EvaluatorState) -> Literal["reviewer", "error_handler", "skip", "cicd"]:
    cicd_analysis = state.get("cicd_analysis", {})
    
    if cicd_analysis.get("status") == "no_cicd":
        return "skip"
    
    if cicd_analysis.get("status") == "failed":
        retry_count = state.get("cicd_retry_count", 0)
        if retry_count < 3:
            return "cicd"
        return "error_handler"
    
    return "reviewer"


def _route_after_review(state: EvaluatorState) -> Literal["reporter", "cicd", "error_handler"]:
    """验证后的路由 - 纯函数，不修改状态"""
    review_result = state.get("review_result", {})
    status = review_result.get("status", "unknown")
    
    if status in ["passed", "corrected"]:
        return "reporter"
    
    if status == "critical" or status == "incomplete":
        retry_count = state.get("cicd_retry_count", 0)
        if retry_count < 3:
            return "cicd"
        return "reporter"
    
    return "reporter"


def _create_error_handler():
    def error_handler(state: EvaluatorState) -> EvaluatorState:
        errors = state.get("errors", [])
        print("\n[ERROR] 工作流执行出错:")
        for err in errors:
            print(f"  - {err}")
        return state
    return error_handler


def _create_skip_node():
    def skip_node(state: EvaluatorState) -> EvaluatorState:
        cicd_analysis = state.get("cicd_analysis", {})
        print(f"\n[INFO] 跳过报告生成: {cicd_analysis.get('message', '无 CI/CD 数据')}")
        return state
    return skip_node
