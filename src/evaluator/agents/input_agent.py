"""Input Agent - 交互式获取用户输入"""
from pathlib import Path
from typing import Any, Dict, List
from evaluator.skills import UrlParser
from .base_agent import BaseAgent, AgentMeta


class InputAgent(BaseAgent):
    """输入处理 Agent"""

    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="InputAgent",
            description="解析用户输入（路径或URL），判断输入类型",
            category="entry",
            inputs=["user_input", "params"],
            outputs=["project_name", "project_path", "project_url", "should_download"],
            dependencies=[],
        )

    def __init__(self):
        super().__init__()

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        user_input = state.get("user_input") or state.get("params", {}).get("project") or ""

        user_input = user_input.strip("\"'").strip()

        if not user_input:
            return {
                **state,
                "current_step": "input",
                "errors": state.get("errors", []) + ["输入不能为空"],
            }

        if UrlParser.is_url(user_input):
            return self._handle_url(user_input, state)
        else:
            return self._handle_local_path(user_input, state)

    def _handle_url(self, url: str, state: Dict[str, Any]) -> Dict[str, Any]:
        parsed = UrlParser.parse(url)
        project_name = UrlParser.get_project_name(parsed)

        return {
            **state,
            "user_input": url,
            "project_url": url,
            "project_name": project_name,
            "should_download": True,
            "current_step": "input",
        }

    def _handle_local_path(self, path: str, state: Dict[str, Any]) -> Dict[str, Any]:
        project_path = Path(path).resolve()
        errors = []

        if not project_path.exists():
            errors.append(f"路径不存在: {project_path}")
            return {
                **state,
                "user_input": path,
                "project_path": None,
                "project_url": None,
                "should_download": False,
                "current_step": "input",
                "errors": state.get("errors", []) + errors,
            }

        if not project_path.is_dir():
            errors.append(f"路径不是目录: {project_path}")
            return {
                **state,
                "user_input": path,
                "project_path": None,
                "project_url": None,
                "should_download": False,
                "current_step": "input",
                "errors": state.get("errors", []) + errors,
            }

        project_name = project_path.name

        return {
            **state,
            "user_input": path,
            "project_path": str(project_path),
            "project_name": project_name,
            "project_url": None,
            "should_download": False,
            "current_step": "input",
        }