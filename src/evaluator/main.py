"""项目入口"""
import sys
import io
import os

# 设置控制台编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 加载 .env 文件
from dotenv import load_dotenv
from pathlib import Path

# 查找 .env 文件
env_path = Path(__file__).parent.parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"已加载配置: {env_path}")
else:
    load_dotenv()  # 尝试从当前目录加载

from evaluator.graph import create_graph
from evaluator.llm import LLMClient


def main():
    """主入口"""
    # 支持命令行参数
    user_input = sys.argv[1] if len(sys.argv) > 1 else None

    # 创建 LLM 客户端
    llm = None
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    model = os.getenv("DEFAULT_MODEL", "gpt-4o-mini")

    if api_key:
        print(f"\nLLM 配置:")
        print(f"  Model: {model}")
        print(f"  Base URL: {base_url}")
        llm = LLMClient(
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
    else:
        print("\n警告: 未配置 LLM API Key，CI/CD 分析将无法执行")

    # 创建工作流
    app = create_graph(user_input=user_input, llm=llm)

    # 初始状态
    initial_state = {
        "user_input": None,
        "project_url": None,
        "project_path": None,
        "project_name": None,
        "clone_status": None,
        "clone_error": None,
        "cicd_analysis": None,
        "html_report": None,
        "report_path": None,
        "should_download": False,
        "current_step": "",
        "errors": [],
    }

    # 执行工作流
    result = app.invoke(initial_state)

    # 输出结果摘要
    print("\n" + "=" * 50)
    print("  执行完成")
    print("=" * 50)
    print(f"  当前步骤: {result.get('current_step')}")
    print(f"  项目名称: {result.get('project_name')}")
    print(f"  项目路径: {result.get('project_path')}")

    if result.get("clone_status"):
        print(f"  克隆状态: {result.get('clone_status')}")

    if result.get("errors"):
        print(f"\n  错误:")
        for err in result["errors"]:
            print(f"    - {err}")

    if result.get("report_path"):
        print(f"\n  报告路径: {result.get('report_path')}")


if __name__ == "__main__":
    main()