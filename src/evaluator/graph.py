# LangGraph 图编排 - 定义 Agent 之间的执行流程
from evaluator.state import EvaluatorState
from evaluator.agents import InputAgent, LoaderAgent, CICDAgent, ReporterAgent, ReviewerAgent
from evaluator.llm import LLMClient
from storage import StorageManager
from evaluator.ui import UIManager, init_ui_manager


def create_graph(
    user_input: str | None = None,
    download_dir: str | None = None,
    llm: LLMClient | None = None,
    storage_dir: str | None = None,
    use_rich: bool = True,
):
    """
    创建评估工作流图

    Args:
        user_input: 可选，直接传入项目路径或URL（跳过交互）
        download_dir: 可选，指定下载目录
        llm: 可选，LLM 客户端实例
        storage_dir: 可选，指定持久化存储目录
        use_rich: 是否使用 Rich 界面（默认 True）
    """
    from langgraph.graph import StateGraph, END

    storage = StorageManager(data_dir=storage_dir) if storage_dir else StorageManager()
    ui_manager = init_ui_manager(use_rich=use_rich)

    input_agent = InputAgent(user_input=user_input)
    loader_agent = LoaderAgent(download_dir=download_dir, storage_manager=storage)
    cicd_agent = CICDAgent(llm=llm)
    reporter_agent = ReporterAgent(storage_manager=storage)
    reviewer_agent = ReviewerAgent(llm=llm)

    workflow = StateGraph(EvaluatorState)

    def run_input(state):
        result = input_agent.run(state)
        ui_manager.init(
            project_name=result.get("project_name", "Unknown"),
            project_path=result.get("project_path", "")
        )
        result["ui_manager"] = ui_manager
        return result

    def run_loader(state):
        result = loader_agent.run(state)
        ui_manager.set_version(result.get("storage_version_id", ""))
        return result

    def run_cicd(state):
        return cicd_agent.run(state)

    def run_reviewer(state):
        return reviewer_agent.run(state)

    def run_reporter(state):
        ui_manager.step_start("reporter", "生成交互式 HTML 报告")
        result = reporter_agent.run(state)
        ui_manager.step_complete("reporter", "报告生成完成")
        return result

    workflow.add_node("input", run_input)
    workflow.add_node("loader", run_loader)
    workflow.add_node("cicd", run_cicd)
    workflow.add_node("reviewer", run_reviewer)
    workflow.add_node("reporter", run_reporter)

    # === 定义流程 ===
    workflow.set_entry_point("input")

    # 线性流程：input → loader → cicd → reviewer
    workflow.add_edge("input", "loader")
    workflow.add_edge("loader", "cicd")
    workflow.add_edge("cicd", "reviewer")

    # ReviewerAgent 的条件分支
    workflow.add_conditional_edges(
        "reviewer",
        _after_review,
        {
            "passed": "reporter",      # 验证通过
            "corrected": "reporter",   # 小错误已修正
            "critical": "cicd",        # 重大错误，需要重做
            "incomplete": "cicd",      # 内容不足，需要补充
            "max_retry": "reporter",   # 重试次数用尽，强制继续
        }
    )

    workflow.add_edge("reporter", END)

    return workflow.compile()


# ========== 条件判断 ==========

def _should_download(state: EvaluatorState) -> str:
    """判断是否需要下载项目"""
    # 如果有错误，直接跳过
    if state.get("errors"):
        return "skip"
    if state.get("should_download", False):
        return "download"
    return "skip"


def _after_review(state: EvaluatorState) -> str:
    """判断 Reviewer 之后的流程"""
    result = state.get("review_result", {})
    status = result.get("status")
    retry_count = state.get("review_retry_count", 0)
    ui_manager = state.get("ui_manager")
    
    if status == "passed" or status == "corrected":
        msg = "报告验证通过"
        if ui_manager:
            ui_manager.success(msg)
        else:
            print(f"  ✓ {msg}")
        return "passed" if status == "passed" else "corrected"
    
    if status == "critical":
        if retry_count >= 3:
            msg = f"重试次数已达上限 (3/3)，强制生成报告"
            if ui_manager:
                ui_manager.warn(msg)
            else:
                print(f"  ⚠️ {msg}")
            return "max_retry"
        msg = f"发现重大错误，进入重做模式 (第 {retry_count} 次)"
        if ui_manager:
            ui_manager.warn(msg)
        else:
            print(f"  ⚠️ {msg}")
        return "critical"
    
    if status == "incomplete":
        if retry_count >= 3:
            msg = f"重试次数已达上限 (3/3)，强制生成报告"
            if ui_manager:
                ui_manager.warn(msg)
            else:
                print(f"  ⚠️ {msg}")
            return "max_retry"
        msg = f"内容不完整，进入补充模式 (第 {retry_count} 次)"
        if ui_manager:
            ui_manager.info(msg)
        else:
            print(f"  📝 {msg}")
        return "incomplete"
    
    if status == "max_retry":
        return "max_retry"
    
    return "passed"