"""项目入口"""
import sys
import io
import os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from dotenv import load_dotenv
from pathlib import Path

env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

from evaluator.core.graphs import create_main_graph
from evaluator.llm import LLMClient
from evaluator.ui import init_ui_manager


def main():
    """主入口"""
    user_input = sys.argv[1] if len(sys.argv) > 1 else None

    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    model = os.getenv("DEFAULT_MODEL", "glm-4")
    use_rich = os.getenv("USE_RICH", "true").lower() != "false"

    llm = None
    if api_key:
        llm = LLMClient(
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
    else:
        print("\n警告: 未配置 LLM API Key，CI/CD 分析将无法执行")

    app = create_main_graph(
        user_input=user_input,
        llm=llm,
        use_rich=use_rich,
    )

    initial_state = {
        "ui_manager": None,
        "user_input": None,
        "project_url": None,
        "project_path": None,
        "project_name": None,
        "display_name": None,
        "clone_status": None,
        "clone_error": None,
        "cicd_analysis": None,
        "html_report": None,
        "report_path": None,
        "should_download": False,
        "current_step": "",
        "completed_steps": [],
        "errors": [],
        "storage_version_id": None,
        "storage_dir": None,
    }

    result = app.invoke(initial_state)

    from evaluator.ui import get_ui_manager, display_result
    ui = get_ui_manager()

    stats = {}
    if result.get("cicd_analysis"):
        stats["工作流"] = result["cicd_analysis"].get("workflows_count", 0)
        stats["Actions"] = result["cicd_analysis"].get("actions_count", 0)

    display_result({
        "stats": stats,
        "report_path": result.get("report_path"),
        "errors": result.get("errors", []),
    }, ui)


if __name__ == "__main__":
    main()