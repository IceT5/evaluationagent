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
from evaluator.config import resolve_interactive_mode
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
    route_after_handler,
)


def _create_node(agent, studio_mode: bool = False) -> callable:
    """通用节点工厂函数
    
    包装 Agent 为 LangGraph 节点。
    使用 safe_run 捕获异常。
    
    Args:
        agent: 继承 BaseAgent 的 Agent 实例
    
    Returns:
        LangGraph 节点函数
    """
    def node(state: EvaluatorState) -> EvaluatorState:
        state = _ensure_interactive_mode(state, studio_mode=studio_mode)
        return agent.safe_run(state)
    return node


def _ensure_interactive_mode(state: EvaluatorState, studio_mode: bool = False) -> EvaluatorState:
    """为 state 注入 interactive_mode 默认值。

    仅在调用侧未显式提供 interactive_mode 时注入，避免覆盖用户/入口决定。
    """
    if state.get("interactive_mode") is not None:
        return state
    return {
        **state,
        "interactive_mode": resolve_interactive_mode(studio_mode=studio_mode),
    }


def _route_after_report_fix_plan(state: EvaluatorState) -> Literal["report_fix_apply", "reporter", "orchestrator"]:
    fix_result = state.get("fix_result", {}) or {}
    if fix_result.get("status") in {"no_issues", "retry"}:
        return "orchestrator"
    if state.get("user_fix_choice"):
        return "report_fix_apply"
    return "reporter"


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
    checkpointer: Any = None,
    studio_mode: bool = False,
) -> Any:
    """创建主工作流图 - 统一入口
    
    工作流:
    intent_parser → orchestrator → [功能节点] → END
    
    Args:
        llm_config: LLM 配置
        storage_dir: 存储目录
        checkpointer: LangGraph checkpointer（支持 interrupt/resume 必需）
        studio_mode: 是否为 LangGraph Studio 图预览模式。为 True 时使用
            Studio 兼容的 CICD 包装子图，避免 aget_graph(xray=true)
            在嵌套 safe_run 边界上触发 __root__ 并发更新错误。
    
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
        ReportFixPlanAgent,
        ReportFixApplyAgent,
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
        InsightsHandlerAgent,
        RecommendHandlerAgent,
        SimilarHandlerAgent,
        AnalyzersHandlerAgent,
        VersionHandlerAgent,
        ClearHandlerAgent,
        QuitHandlerAgent,
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
        "report_fix_plan": ReportFixPlanAgent(),
        "report_fix_apply": ReportFixApplyAgent(llm=llm),
        "reporter": ReporterAgent(storage_manager=storage),
        "compare": CompareAgent(llm=llm, storage_manager=storage),
        "error_handler": ErrorHandlerAgent(),
        "list_handler": ListHandlerAgent(),
        "info_handler": InfoHandlerAgent(),
        "delete_handler": DeleteHandlerAgent(),
        "help_handler": HelpHandlerAgent(),
        "insights_handler": InsightsHandlerAgent(),
        "recommend_handler": RecommendHandlerAgent(),
        "similar_handler": SimilarHandlerAgent(),
        "analyzers_handler": AnalyzersHandlerAgent(),
        "version_handler": VersionHandlerAgent(),
        "clear_handler": ClearHandlerAgent(),
        "quit_handler": QuitHandlerAgent(),
    }
    
    missing_deps = validate_agent_dependencies(agents)
    if missing_deps:
        print("[WARN] Agent 依赖验证失败:")
        for m in missing_deps:
            print(f"  - {m}")
    
    workflow = StateGraph(EvaluatorState)
    
    workflow.add_node("intent_parser", _create_node(agents["intent_parser"], studio_mode=studio_mode))
    workflow.add_node("orchestrator", _create_orchestrator_node(agents["orchestrator"], studio_mode=studio_mode))
    workflow.add_node("validate", _create_validate_node(agents["validate"], studio_mode=studio_mode))
    workflow.add_node("input", _create_node(agents["input"], studio_mode=studio_mode))
    workflow.add_node("loader", _create_node(agents["loader"], studio_mode=studio_mode))
    # CICD 节点：直接嵌入子图（Studio 可展开查看内部 9 个子 agent）
    cicd_agent = agents["cicd"]
    cicd_orchestrator = cicd_agent._get_orchestrator()
    if cicd_orchestrator and cicd_orchestrator.graph:
        # Studio 模式：直接暴露子图，避免 xray 展开包装层时的 __root__ 并发更新冲突
        workflow.add_node("cicd", cicd_orchestrator.graph)
    else:
        workflow.add_node("cicd", _create_cicd_node(cicd_agent, studio_mode=studio_mode))
    workflow.add_node("reviewer", _create_node(agents["reviewer"], studio_mode=studio_mode))
    workflow.add_node("report_fix_plan", _create_node(agents["report_fix_plan"], studio_mode=studio_mode))
    workflow.add_node("report_fix_apply", _create_node(agents["report_fix_apply"], studio_mode=studio_mode))
    workflow.add_node("reporter", _create_reporter_node(agents["reporter"], studio_mode=studio_mode))
    workflow.add_node("compare", _create_node(agents["compare"], studio_mode=studio_mode))
    workflow.add_node("error_handler", _create_node(agents["error_handler"], studio_mode=studio_mode))
    workflow.add_node("list_handler", _create_node(agents["list_handler"], studio_mode=studio_mode))
    workflow.add_node("info_handler", _create_node(agents["info_handler"], studio_mode=studio_mode))
    workflow.add_node("delete_handler", _create_node(agents["delete_handler"], studio_mode=studio_mode))
    workflow.add_node("help_handler", _create_node(agents["help_handler"], studio_mode=studio_mode))
    workflow.add_node("insights_handler", _create_node(agents["insights_handler"], studio_mode=studio_mode))
    workflow.add_node("recommend_handler", _create_node(agents["recommend_handler"], studio_mode=studio_mode))
    workflow.add_node("similar_handler", _create_node(agents["similar_handler"], studio_mode=studio_mode))
    workflow.add_node("analyzers_handler", _create_node(agents["analyzers_handler"], studio_mode=studio_mode))
    workflow.add_node("version_handler", _create_node(agents["version_handler"], studio_mode=studio_mode))
    workflow.add_node("clear_handler", _create_node(agents["clear_handler"], studio_mode=studio_mode))
    workflow.add_node("quit_handler", _create_node(agents["quit_handler"], studio_mode=studio_mode))
    
    workflow.set_entry_point("intent_parser")
    workflow.add_edge("intent_parser", "orchestrator")
    
    all_steps = {"input", "loader", "cicd", "reviewer", "report_fix_plan", "report_fix_apply", "reporter", "compare",
                 "error_handler", "list_handler", "info_handler", "delete_handler", 
                 "help_handler", "insights_handler", "recommend_handler", "similar_handler",
                 "analyzers_handler", "version_handler", "clear_handler", "quit_handler",
                 "validate", "end"}
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
        {"report_fix_plan": "report_fix_plan", "reporter": "reporter", "orchestrator": "orchestrator"}
    )
    
    workflow.add_conditional_edges(
        "report_fix_plan",
        _route_after_report_fix_plan,
        {"report_fix_apply": "report_fix_apply", "reporter": "reporter", "orchestrator": "orchestrator"}
    )
    
    workflow.add_conditional_edges(
        "report_fix_apply",
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
    
    workflow.add_conditional_edges(
        "list_handler",
        route_after_handler,
        {"error_handler": "error_handler", "end": END}
    )
    workflow.add_conditional_edges(
        "info_handler",
        route_after_handler,
        {"error_handler": "error_handler", "end": END}
    )
    workflow.add_conditional_edges(
        "delete_handler",
        route_after_handler,
        {"error_handler": "error_handler", "end": END}
    )
    workflow.add_conditional_edges(
        "help_handler",
        route_after_handler,
        {"error_handler": "error_handler", "end": END}
    )
    workflow.add_conditional_edges(
        "insights_handler",
        route_after_handler,
        {"error_handler": "error_handler", "end": END}
    )
    workflow.add_conditional_edges(
        "recommend_handler",
        route_after_handler,
        {"error_handler": "error_handler", "end": END}
    )
    workflow.add_conditional_edges(
        "similar_handler",
        route_after_handler,
        {"error_handler": "error_handler", "end": END}
    )
    workflow.add_conditional_edges(
        "analyzers_handler",
        route_after_handler,
        {"error_handler": "error_handler", "end": END}
    )
    workflow.add_conditional_edges(
        "version_handler",
        route_after_handler,
        {"error_handler": "error_handler", "end": END}
    )
    workflow.add_conditional_edges(
        "clear_handler",
        route_after_handler,
        {"error_handler": "error_handler", "end": END}
    )
    workflow.add_conditional_edges(
        "quit_handler",
        route_after_handler,
        {"error_handler": "error_handler", "end": END}
    )
    
    return workflow.compile(checkpointer=checkpointer)


def _create_orchestrator_node(agent, studio_mode: bool = False):
    """创建 OrchestratorAgent 节点"""
    def node(state: EvaluatorState) -> EvaluatorState:
        state = _ensure_interactive_mode(state, studio_mode=studio_mode)
        result = agent.safe_run(state)
        
        completed = state.get("completed_steps", [])
        current = state.get("current_step")
        if current and current not in completed:
            completed.append(current)
            result["completed_steps"] = completed
        
        return result
    return node


def _create_validate_node(agent, studio_mode: bool = False):
    """创建 StateValidationAgent 节点
    
    验证状态完整性，添加验证结果到状态。
    """
    def node(state: EvaluatorState) -> EvaluatorState:
        state = _ensure_interactive_mode(state, studio_mode=studio_mode)
        result = agent.safe_run(state)
        
        validation_result = result.get("validation_result", {})
        if not validation_result.get("valid", True):
            issues = validation_result.get("issues", [])
            for issue in issues:
                result.setdefault("errors", []).append(f"Validation: {issue}")
        
        return result
    return node


def _create_cicd_node(agent, studio_mode: bool = False):
    """创建 CICDAgent 节点"""
    def node(state: EvaluatorState) -> EvaluatorState:
        from evaluator.core.routes import prepare_cicd_retry
        state = _ensure_interactive_mode(state, studio_mode=studio_mode)
        
        retry_mode = state.get("cicd_retry_mode")
        retry_result = state.get("cicd_retry_result") or {}
        print(f"  [CICD Node] cicd_retry_mode={retry_mode}, retry_requested={retry_result.get('requested', False)}")
        
        if retry_mode or retry_result.get("requested"):
            retry_updates = prepare_cicd_retry(state)
            print(f"  [CICD Node] prepare_cicd_retry: retry_mode={retry_updates.get('retry_mode')}, issues={len(retry_updates.get('retry_issues', []))}")
            state = {**state, **retry_updates}
        
        result = agent.safe_run(state)
        return result
    return node


def _cicd_prep(state: EvaluatorState) -> EvaluatorState:
    """CICD 预处理节点 — retry 预处理 + architecture_json_path + project_path 检查
    
    作为包装子图的第一个节点，在 CICD 子图执行前完成：
    1. project_path 前置检查（缺失时设置 failed 状态，跳过子图）
    2. retry 预处理（prepare_cicd_retry）
    3. architecture_json_path 设置
    """
    from evaluator.core.routes import prepare_cicd_retry
    
    # project_path 前置检查
    project_path = state.get("project_path")
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
    
    # retry 预处理
    retry_mode = state.get("cicd_retry_mode")
    retry_result = state.get("cicd_retry_result") or {}
    print(f"  [CICD Node] cicd_retry_mode={retry_mode}, retry_requested={retry_result.get('requested', False)}")
    
    if retry_mode or retry_result.get("requested"):
        retry_updates = prepare_cicd_retry(state)
        print(f"  [CICD Node] prepare_cicd_retry: retry_mode={retry_updates.get('retry_mode')}, issues={len(retry_updates.get('retry_issues', []))}")
        state = {**state, **retry_updates}
    
    # architecture_json_path 设置
    storage_dir = state.get("storage_dir")
    architecture_json_path = f"{storage_dir}/architecture.json" if storage_dir else None
    
    return {**state, "architecture_json_path": architecture_json_path}


def _route_after_cicd_prep(state: EvaluatorState) -> Literal["cicd_core", "finalize"]:
    """CICD 预处理后的路由 — project_path 缺失时跳过子图直接进入后处理"""
    if state.get("cicd_analysis", {}).get("status") == "failed":
        return "finalize"
    return "cicd_core"


def _cicd_finalize(state: EvaluatorState) -> EvaluatorState:
    """CICD 后处理节点 — 设置 cicd_analysis、current_step 等
    
    作为包装子图的最后一个节点，在 CICD 子图执行后完成：
    1. 如果 prep 已设置 failed（project_path 缺失），直接返回
    2. 检查 validation_result.needs_retry，设置 failed 状态触发主图重试路由
    3. 检查 errors，设置 failed 状态
    4. 成功时设置 cicd_analysis 完整信息
    """
    # 如果 prep 已设置失败状态（project_path 缺失），直接返回
    if state.get("cicd_analysis", {}).get("status") == "failed":
        return state
    
    retry_result = state.get("cicd_retry_result") or {}
    if retry_result.get("requested"):
        if retry_result.get("retry_mode") in {"reassemble", "revalidate_only", "rerun_batch"}:
            return {
                **state,
                "current_step": "cicd",
                "cicd_analysis": {"status": "success", "note": "局部重试由子图或上游调用侧继续收敛"},
            }
        retry_reason = retry_result.get("retry_reason", "未知原因")
        print(f"  [CICDAgent] 检测到需要重试: {retry_reason}")
        return {
            **state,
            "current_step": "cicd",
            "cicd_analysis": {"status": "retry_requested", "error": retry_reason},
        }
    
    # 检查错误
    if state.get("errors"):
        return {
            **state,
            "current_step": "cicd",
            "cicd_analysis": {"status": "failed", "error": str(state.get("errors"))},
            "ci_data": state.get("ci_data"),
            "workflow_count": state.get("workflow_count", 0),
        }
    
    # 成功
    storage_dir = state.get("storage_dir")
    project_path = state.get("project_path")
    output_dir = storage_dir or project_path
    
    workflow_count = state.get("workflow_count", 0)
    ci_data = state.get("ci_data", {})
    actions_count = len(ci_data.get("actions", []))
    jobs_count = sum(len(wf.get("jobs", {})) for wf in ci_data.get("workflows", {}).values())

    print(f"\n{'='*50}")
    print("  CI/CD 分析完成!")
    print(f"{'='*50}")

    return {
        **state,
        "current_step": "cicd",
        "cicd_analysis": {
            "status": "success",
            "workflows_count": workflow_count,
            "jobs_count": jobs_count,
            "actions_count": actions_count,
            "ci_data_path": state.get("ci_data_path"),
            "report_path": state.get("report_md"),
            "architecture_json_path": state.get("architecture_json_path"),
            "analysis_summary_path": f"{output_dir}/analysis_summary.json",
        },
    }


def _create_cicd_subgraph(cicd_orchestrator):
    """创建 CICD 包装子图 — Studio 可展开查看内部节点
    
    结构：prep → cicd_core → finalize
    
    - prep:      重试预处理 + architecture_json_path + project_path 检查
    - cicd_core: 原始 CICD 子图（9 个子 agent，Studio 可进一步展开）
    - finalize:  后处理（cicd_analysis、current_step、needs_retry 检查）
    
    关键：cicd_core 是直接嵌入的编译后子图（add_node("cicd_core", compiled_graph)），
    LangGraph Studio 可以静态发现并展开显示其内部 9 个子 agent 节点。
    这与之前的 _create_cicd_subgraph_node（wrapper 函数）不同 — 
    wrapper 函数对 Studio 是不透明的，而编译后的图是可展开的。
    """
    try:
        from langgraph.graph import StateGraph as SG, END as E
    except ImportError:
        return None
    
    wrapper = SG(EvaluatorState)
    
    wrapper.add_node("prep", _cicd_prep)
    wrapper.add_node("finalize", _cicd_finalize)
    wrapper.add_node("cicd_core", cicd_orchestrator.graph)  # 直接嵌入编译后的子图！Studio 可展开
    
    # prep 后条件路由：project_path 缺失时跳过 cicd_core，直接进入 finalize
    wrapper.add_conditional_edges(
        "prep",
        _route_after_cicd_prep,
        {"cicd_core": "cicd_core", "finalize": "finalize"}
    )
    
    wrapper.add_edge("cicd_core", "finalize")
    wrapper.add_edge("finalize", E)
    wrapper.set_entry_point("prep")
    
    return wrapper.compile()


def _create_reporter_node(agent, studio_mode: bool = False):
    """创建 ReporterAgent 节点"""
    def node(state: EvaluatorState) -> EvaluatorState:
        state = _ensure_interactive_mode(state, studio_mode=studio_mode)
        return agent.safe_run(state)
    return node
