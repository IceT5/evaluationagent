"""QuitHandlerAgent - 处理 /quit 命令"""
from typing import Dict, Any

from evaluator.agents.base_agent import BaseAgent, AgentMeta


class QuitHandlerAgent(BaseAgent):
    """处理 /quit 命令的 Agent
    
    退出程序。
    """
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="QuitHandlerAgent",
            description="退出程序",
            category="handler",
            inputs=[],
            outputs=["should_quit"],
            dependencies=[],
        )
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行 /quit 命令
        
        Args:
            state: 当前状态
        
        Returns:
            更新后的状态，包含 should_quit
        """
        try:
            return {
                **state,
                "should_quit": True,
                "completed_steps": state.get("completed_steps", []) + ["quit_handler"],
            }
            
        except Exception as e:
            return {
                **state,
                "should_quit": False,
                "errors": state.get("errors", []) + [f"QuitHandlerAgent: {e}"],
                "completed_steps": state.get("completed_steps", []) + ["quit_handler"],
            }
