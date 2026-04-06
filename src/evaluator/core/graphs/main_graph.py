"""主工作流图 - 统一入口

所有用户输入都通过此图处理：
1. IntentParserAgent 解析用户意图
2. OrchestratorAgent 根据意图规划工作流
3. 执行对应的 Agent 序列
"""
from typing import Optional, Dict, Any, Literal, List

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
from evaluator.core.routes import (
    route_intent,
    route_error,
    route_after_input,
    route_after_loader,
    route_after_cicd,
    route_after_review,
    route_after_validate,
    route_after_reviewer,
    route_after_report_fix,
)


def _create_node(agent) -> callable:
    """通用节点工厂函数
    
    包装 Agent 为 LangGraph 节点。
    使用 safe_run 捕获异常。
    
    Args:
        agent: 继承 BaseAgent 的 Agent 实例
    
    Returns:
        LangGraph 节点函数
    """
    def node(state: EvaluatorState) -> EvaluatorState:
        return agent.safe_run(state)
    return node


def validate_agent_dependencies(agents: Dict[str, Any]) -> List[str]:
    """验证 Agent 依赖关系
    
    Args:
        agents: Agent 名称到实例的映射
    
    Returns:
        缺失依赖列表
    """
    from evaluator.agents.base_agent import BaseAgent
    
    missing = []
    agent_names = set(agents.keys())
    
    def normalize(name: str) -> str:
        return name.lower().replace("_", "").replace("agent", "")
    
    for name, agent in agents.items():
        if not isinstance(agent, BaseAgent):
            continue
        meta = agent.describe()
        for dep in meta.dependencies:
            dep_normalized = normalize(dep)
            name_normalized = normalize(name)
            if dep_normalized != name_normalized and dep not in agent_names and dep_normalized not in {normalize(a) for a in agent_names}:
                missing.append(f"{name} 依赖 {dep}，但 {dep} 未注册")
    
    return missing


def create_main_graph(
    llm_config: Optional[Dict[str, Any]] = None,
    storage_dir: Optional[str] = None,
) -> Any:
    """创建主工作流图 - 统一入口
    
    工作流:
    intent_parser → orchestrator → [功能节点] → END
    
    Args:
        llm_config: LLM 配置
        storage_dir: 存储目录
    
    Returns:
        编译后的 StateGraph
    """
    if not HAS_LANGGRAPH:
        return None
    
    from storage.manager import StorageManager
    from evaluator.agents import (
        IntentParserAgent,
        OrchestratorAgent,
        InputAgent,
        LoaderAgent,
        CICDAgent,
        ReviewerAgent,
        ReportFixAgent,
        ReporterAgent,
        CompareAgent,
        ErrorHandlerAgent,
        StateValidationAgent,
    )
    from evaluator.agents.handlers import (
        ListHandlerAgent,
        InfoHandlerAgent,
        DeleteHandlerAgent,
        HelpHandlerAgent,
    )
    
    llm = None
    if llm_config and HAS_LLM:
        try:
            llm = LLMClient(**llm_config)
        except Exception:
            pass
    
    storage = StorageManager(data_dir=storage_dir) if storage_dir else StorageManager()
    
    agents = {
        "intent_parser": IntentParserAgent(llm=llm),
        "orchestrator": OrchestratorAgent(llm=llm),
        "validate": StateValidationAgent(),
        "input": InputAgent(),
        "loader": LoaderAgent(storage_manager=storage),
        "cicd": CICDAgent(llm=llm),
        "reviewer": ReviewerAgent(llm=llm),
        "report_fix": ReportFixAgent(llm=llm),
        "reporter": ReporterAgent(storage_manager=storage),
        "compare": CompareAgent(llm=llm, storage_manager=storage),
        "error_handler": ErrorHandlerAgent(),
        "list_handler": ListHandlerAgent(),
        "info_handler": InfoHandlerAgent(),
        "delete_handler": DeleteHandlerAgent(),
        "help_handler": HelpHandlerAgent(),
    }
    
    missing_deps = validate_agent_dependencies(agents)
    if missing_deps:
        print("[WARN] Agent 依赖验证失败:")
        for m in missing_deps:
            print(f"  - {m}")
    
    workflow = StateGraph(EvaluatorState)
    
    workflow.add_node("intent_parser", _create_node(agents["intent_parser"]))
    workflow.add_node("orchestrator", _create_orchestrator_node(agents["orchestrator"]))
    workflow.add_node("validate", _create_validate_node(agents["validate"]))
    workflow.add_node("input", _create_node(agents["input"]))
    workflow.add_node("loader", _create_node(agents["loader"]))
    workflow.add_node("cicd", _create_cicd_node(agents["cicd"]))
    workflow.add_node("reviewer", _create_node(agents["reviewer"]))
    workflow.add_node("report_fix", _create_node(agents["report_fix"]))
    workflow.add_node("reporter", _create_reporter_node(agents["reporter"]))
    workflow.add_node("compare", _create_node(agents["compare"]))
    workflow.add_node("error_handler", _create_node(agents["error_handler"]))
    workflow.add_node("list_handler", _create_node(agents["list_handler"]))
    workflow.add_node("info_handler", _create_node(agents["info_handler"]))
    workflow.add_node("delete_handler", _create_node(agents["delete_handler"]))
    workflow.add_node("help_handler", _create_node(agents["help_handler"]))
    
    workflow.set_entry_point("intent_parser")
    workflow.add_edge("intent_parser", "orchestrator")
    
    all_steps = {"input", "loader", "cicd", "reviewer", "report_fix", "reporter", "compare",
                 "error_handler", "list_handler", "info_handler", "delete_handler", 
                 "help_handler", "validate", "end"}
    route_targets = {step: step for step in all_steps}
    route_targets["end"] = END
    
    workflow.add_conditional_edges(
        "orchestrator",
        route_intent,
        route_targets
    )
    
    workflow.add_conditional_edges(
        "input",
        route_after_input,
        {"loader": "loader", "skip": "validate", "error_handler": "error_handler", "orchestrator": "orchestrator"}
    )
    
    workflow.add_conditional_edges(
        "loader",
        route_after_loader,
        {"cicd": "cicd", "skip": "validate", "error_handler": "error_handler", "orchestrator": "orchestrator"}
    )
    
    workflow.add_conditional_edges(
        "cicd",
        route_after_cicd,
        {"reviewer": "reviewer", "skip": "validate", "error_handler": "error_handler", "cicd": "cicd", "orchestrator": "orchestrator"}
    )
    
    workflow.add_conditional_edges(
        "reviewer",
        route_after_reviewer,
        {"report_fix": "report_fix", "reporter": "reporter", "orchestrator": "orchestrator"}
    )
    
    workflow.add_conditional_edges(
        "report_fix",
        route_after_report_fix,
        {"reviewer": "reviewer", "reporter": "reporter", "cicd": "cicd", "orchestrator": "orchestrator"}
    )
    
    workflow.add_conditional_edges(
        "validate",
        route_after_validate,
        {"input": "input", "orchestrator": "orchestrator", "end": END}
    )
    
    workflow.add_conditional_edges(
        "error_handler",
        route_error,
        {"retry": "orchestrator", "recover": "orchestrator", "end": END}
    )
    
    workflow.add_edge("reporter", END)
    workflow.add_edge("compare", END)
    workflow.add_edge("list_handler", END)
    workflow.add_edge("info_handler", END)
    workflow.add_edge("delete_handler", END)
    workflow.add_edge("help_handler", END)
    
    return workflow.compile()


def _create_orchestrator_node(agent):
    """创建 OrchestratorAgent 节点"""
    def node(state: EvaluatorState) -> EvaluatorState:
        result = agent.safe_run(state)
        
        completed = state.get("completed_steps", [])
        current = state.get("current_step")
        if current and current not in completed:
            completed.append(current)
            result["completed_steps"] = completed
        
        return result
    return node


def _create_validate_node(agent):
    """创建 StateValidationAgent 节点
    
    验证状态完整性，添加验证结果到状态。
    """
    def node(state: EvaluatorState) -> EvaluatorState:
        result = agent.safe_run(state)
        
        validation_result = result.get("validation_result", {})
        if not validation_result.get("valid", True):
            issues = validation_result.get("issues", [])
            for issue in issues:
                result.setdefault("errors", []).append(f"Validation: {issue}")
        
        return result
    return node


def _create_cicd_node(agent):
    """创建 CICDAgent 节点"""
    def node(state: EvaluatorState) -> EvaluatorState:
        from evaluator.core.routes import prepare_cicd_retry
        
        retry_mode = state.get("cicd_retry_mode")
        print(f"  [CICD Node] cicd_retry_mode={retry_mode}, has_review_result={bool(state.get('review_result'))}")
        
        if retry_mode and state.get("review_result"):
            retry_updates = prepare_cicd_retry(state)
            print(f"  [CICD Node] prepare_cicd_retry: retry_mode={retry_updates.get('retry_mode')}, issues={len(retry_updates.get('retry_issues', []))}")
            state = {**state, **retry_updates}
        
        result = agent.safe_run(state)
        return result
    return node


def _create_reporter_node(agent):
    """创建 ReporterAgent 节点
    
    分析完成后自动触发后台智能Agent任务。
    """
    def node(state: EvaluatorState) -> EvaluatorState:
        result = agent.safe_run(state)
        
        if not result.get("errors"):
            _trigger_intelligence_background(result)
        
        return result
    return node


def _trigger_intelligence_background(state: EvaluatorState):
    """触发后台智能Agent任务
    
    在reporter完成后异步执行智能Agent链：
    storage → recommendation → reflection
    """
    try:
        from evaluator.core.background import background
        
        state_copy = state.copy()
        
        if state_copy.get("llm"):
            pass
        elif state_copy.get("llm_config"):
            from evaluator.llm import LLMClient
            try:
                state_copy["llm"] = LLMClient(**state_copy.get("llm_config", {}))
            except Exception:
                pass
        
        parent_run_id = None
        try:
            import os
            if os.getenv("LANGCHAIN_TRACING_V2", "").lower() == "true":
                try:
                    from langsmith import client as ls_client
                    run_tree = ls_client.get_current_run_tree()
                    if run_tree:
                        parent_run_id = run_tree.id
                except Exception:
                    pass
        except Exception:
            pass
        
        print(f"  [Background] 提交智能分析任务...")
        background.submit_intelligence(state_copy, parent_run_id=parent_run_id)
        print(f"  [Background] 智能分析将在后台执行，完成后可使用 /insights 查看结果")
    except Exception as e:
        print(f"  [Background] 提交智能任务失败: {e}")
