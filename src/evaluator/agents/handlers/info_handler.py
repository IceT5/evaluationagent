"""InfoHandlerAgent - 处理 info/show 命令"""
from typing import Dict, Any

from evaluator.core.project import get_project
from evaluator.agents.base_agent import BaseAgent, AgentMeta


class InfoHandlerAgent(BaseAgent):
    """处理 info 命令的 Agent
    
    显示指定项目的详细信息。
    """
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="InfoHandlerAgent",
            description="显示项目详细信息",
            category="handler",
            inputs=["params"],
            outputs=["info_result"],
            dependencies=[],
        )
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行 info 命令
        
        Args:
            state: 当前状态，包含 params.project
        
        Returns:
            更新后的状态，包含 info_result
        """
        try:
            params = state.get("params", {})
            project_name = params.get("project")
            version = params.get("version")
            
            if not project_name:
                return {
                    **state,
                    "info_result": {
                        "success": False,
                        "error": "未指定项目名称",
                    },
                    "errors": state.get("errors", []) + ["未指定项目名称"],
                    "completed_steps": state.get("completed_steps", []) + ["info_handler"],
                }
            
            detail = get_project(project_name, version)
            
            if not detail:
                return {
                    **state,
                    "info_result": {
                        "success": False,
                        "error": f"项目不存在: {project_name}",
                    },
                    "errors": state.get("errors", []) + [f"项目不存在: {project_name}"],
                    "completed_steps": state.get("completed_steps", []) + ["info_handler"],
                }
            
            return {
                **state,
                "info_result": {
                    "success": True,
                    "name": detail.name,
                    "display_name": detail.display_name,
                    "version_count": len(detail.versions),
                    "versions": detail.versions,
                    "source_url": detail.source_url,
                    "source_path": detail.source_path,
                },
                "completed_steps": state.get("completed_steps", []) + ["info_handler"],
            }
        except Exception as e:
            return {
                **state,
                "info_result": {
                    "success": False,
                    "error": str(e),
                },
                "errors": state.get("errors", []) + [f"InfoHandlerAgent: {e}"],
                "completed_steps": state.get("completed_steps", []) + ["info_handler"],
            }
