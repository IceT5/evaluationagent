"""LangGraph Studio 入口 — 仅 langgraph dev 使用

此文件导出编译后的 StateGraph 供 LangGraph Studio 可视化。
不被 CLI 或任何现有代码引用。

注意：langgraph dev / Studio 自带 checkpointer（服务端内置），
此处无需显式传入 checkpointer。interrupt/resume 在 Studio 端
由服务端 checkpoint 机制自动支持。
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

_model = os.getenv("DEFAULT_MODEL")
if not _model:
    raise ValueError("必须设置 DEFAULT_MODEL 环境变量")

from evaluator.core.graphs import create_main_graph

graph = create_main_graph(
    llm_config={
        "api_key": os.getenv("OPENAI_API_KEY"),
        "base_url": os.getenv("OPENAI_BASE_URL"),
        "model": _model,
    },
    storage_dir=os.getenv("EVAL_DATA_DIR"),
    studio_mode=True,
    # checkpointer 不需要传：langgraph dev server 自带内置 checkpointer
    # Studio 通过服务端 checkpoint 机制支持 interrupt/resume
)
