"""VersionHandlerAgent - 处理 /version 命令"""
from typing import Dict, Any

from evaluator.agents.base_agent import BaseAgent, AgentMeta


VERSION = "1.0.0"


class VersionHandlerAgent(BaseAgent):
    """处理 /version 命令的 Agent
    
    显示版本信息。
    """
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="VersionHandlerAgent",
            description="显示版本信息",
            category="handler",
            inputs=[],
            outputs=["version_result"],
            dependencies=[],
        )
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行 /version 命令
        
        Args:
            state: 当前状态
        
        Returns:
            更新后的状态，包含 version_result
        """
        try:
            return {
                **state,
                "version_result": {
                    "success": True,
                    "version": VERSION,
                },
                "completed_steps": state.get("completed_steps", []) + ["version_handler"],
            }
            
        except Exception as e:
            return {
                **state,
                "version_result": {
                    "success": False,
                    "error": str(e),
                },
                "errors": state.get("errors", []) + [f"VersionHandlerAgent: {e}"],
                "completed_steps": state.get("completed_steps", []) + ["version_handler"],
            }
