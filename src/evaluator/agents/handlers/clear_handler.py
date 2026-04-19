"""ClearHandlerAgent - 处理 /clear 命令"""
from typing import Dict, Any
import os

from evaluator.agents.base_agent import BaseAgent, AgentMeta


class ClearHandlerAgent(BaseAgent):
    """处理 /clear 命令的 Agent
    
    清除屏幕。
    """
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="ClearHandlerAgent",
            description="清除屏幕",
            category="handler",
            inputs=[],
            outputs=[],
            dependencies=[],
        )
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行 /clear 命令
        
        Args:
            state: 当前状态
        
        Returns:
            更新后的状态
        """
        try:
            os.system('cls' if os.name == 'nt' else 'clear')
            
            return {
                **state,
                "completed_steps": state.get("completed_steps", []) + ["clear_handler"],
            }
            
        except Exception as e:
            return {
                **state,
                "errors": state.get("errors", []) + [f"ClearHandlerAgent: {e}"],
                "completed_steps": state.get("completed_steps", []) + ["clear_handler"],
            }
