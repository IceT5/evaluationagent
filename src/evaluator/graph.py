# LangGraph 图编排 - 定义 Agent 之间的执行流程
from evaluator.state import EvaluatorState
from evaluator.agents import InputAgent, LoaderAgent, CICDAgent, ReporterAgent
from evaluator.llm import LLMClient


def create_graph(
    user_input: str | None = None,
    download_dir: str | None = None,
    llm: LLMClient | None = None,
    output_dir: str | None = None,
):
    """
    创建评估工作流图

    Args:
        user_input: 可选，直接传入项目路径或URL（跳过交互）
        download_dir: 可选，指定下载目录
        llm: 可选，LLM 客户端实例
        output_dir: 可选，报告输出目录

    流程：
    input_agent → [条件] → loader_agent → cicd_agent → reporter_agent
                  ↓ (本地路径跳过下载)
                  └──────────────────────────→ cicd_agent
    """
    from langgraph.graph import StateGraph, END

    # 创建 Agent 实例
    input_agent = InputAgent(user_input=user_input)
    loader_agent = LoaderAgent(download_dir=download_dir)
    cicd_agent = CICDAgent(llm=llm)
    reporter_agent = ReporterAgent(output_dir=output_dir)

    workflow = StateGraph(EvaluatorState)

    # === 添加 Agent 节点 ===
    workflow.add_node("input", lambda state: input_agent.run(state))
    workflow.add_node("loader", lambda state: loader_agent.run(state))
    workflow.add_node("cicd", lambda state: cicd_agent.run(state))
    workflow.add_node("reporter", lambda state: reporter_agent.run(state))

    # === 定义流程 ===
    workflow.set_entry_point("input")

    # input 之后，根据是否需要下载决定下一步
    workflow.add_conditional_edges(
        "input",
        _should_download,
        {
            "download": "loader",
            "skip": "cicd",
        },
    )

    workflow.add_edge("loader", "cicd")
    workflow.add_edge("cicd", "reporter")
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