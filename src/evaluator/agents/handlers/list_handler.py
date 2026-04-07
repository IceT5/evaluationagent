"""ListHandlerAgent - 处理 list 命令"""
from typing import Dict, Any

from evaluator.core.project import list_projects, get_storage_info
from evaluator.agents.base_agent import BaseAgent, AgentMeta


class ListHandlerAgent(BaseAgent):
    """处理 list 命令的 Agent
    
    列出所有已保存的项目及其存储信息。
    """
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="ListHandlerAgent",
            description="列出已保存的项目",
            category="handler",
            inputs=[],
            outputs=["list_result"],
            dependencies=[],
        )
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行 list 命令
        
        Args:
            state: 当前状态
        
        Returns:
            更新后的状态，包含 list_result
        """
        try:
            info = get_storage_info()
            projects = list_projects()
            
            return {
                **state,
                "list_result": {
                    "storage_info": info,
                    "projects": [
                        {
                            "name": p.name,
                            "display_name": p.display_name,
                            "latest_version": p.latest_version,
                            "version_count": p.version_count,
                        }
                        for p in projects
                    ],
                },
                "completed_steps": state.get("completed_steps", []) + ["list_handler"],
            }
        except Exception as e:
            return {
                **state,
                "list_result": {
                    "success": False,
                    "error": str(e),
                },
                "errors": state.get("errors", []) + [f"ListHandlerAgent: {e}"],
                "completed_steps": state.get("completed_steps", []) + ["list_handler"],
            }
