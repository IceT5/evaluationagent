"""DeleteHandlerAgent - 处理 delete 命令"""
from typing import Dict, Any

from evaluator.core.project import delete_project
from evaluator.agents.base_agent import BaseAgent, AgentMeta


class DeleteHandlerAgent(BaseAgent):
    """处理 delete 命令的 Agent
    
    删除指定的项目或版本。
    """
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="DeleteHandlerAgent",
            description="删除项目或版本",
            category="handler",
            inputs=["params"],
            outputs=["delete_result"],
            dependencies=[],
        )
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行 delete 命令
        
        Args:
            state: 当前状态，包含 params.project, params.version
        
        Returns:
            更新后的状态，包含 delete_result
        """
        try:
            params = state.get("params", {})
            project_name = params.get("project")
            version = params.get("version")
            
            if not project_name:
                return {
                    **state,
                    "delete_result": {
                        "success": False,
                        "error": "未指定项目名称",
                    },
                    "errors": state.get("errors", []) + ["未指定项目名称"],
                    "completed_steps": state.get("completed_steps", []) + ["delete_handler"],
                }
            
            success = delete_project(project_name, version)
            
            if success:
                msg = f"已删除项目 {project_name}"
                if version:
                    msg += f" 的版本 {version}"
                return {
                    **state,
                    "delete_result": {
                        "success": True,
                        "message": msg,
                        "project_name": project_name,
                        "version": version,
                    },
                    "completed_steps": state.get("completed_steps", []) + ["delete_handler"],
                }
            else:
                return {
                    **state,
                    "delete_result": {
                        "success": False,
                        "error": f"项目不存在: {project_name}",
                    },
                    "errors": state.get("errors", []) + [f"项目不存在: {project_name}"],
                    "completed_steps": state.get("completed_steps", []) + ["delete_handler"],
                }
        except Exception as e:
            return {
                **state,
                "delete_result": {
                    "success": False,
                    "error": str(e),
                },
                "errors": state.get("errors", []) + [f"DeleteHandlerAgent: {e}"],
                "completed_steps": state.get("completed_steps", []) + ["delete_handler"],
            }
