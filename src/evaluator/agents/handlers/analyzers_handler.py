"""AnalyzersHandlerAgent - 处理 /analyzers 命令"""
from typing import Dict, Any, List

from evaluator.agents.base_agent import BaseAgent, AgentMeta


class AnalyzersHandlerAgent(BaseAgent):
    """处理 /analyzers 命令的 Agent
    
    列出可用的分析器。
    """
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="AnalyzersHandlerAgent",
            description="列出可用的分析器",
            category="handler",
            inputs=[],
            outputs=["analyzers_result"],
            dependencies=[],
        )
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行 /analyzers 命令
        
        Args:
            state: 当前状态
        
        Returns:
            更新后的状态，包含 analyzers_result
        """
        try:
            analyzers = self._list_analyzers()
            
            return {
                **state,
                "analyzers_result": {
                    "success": True,
                    "analyzers": analyzers,
                },
                "completed_steps": state.get("completed_steps", []) + ["analyzers_handler"],
            }
            
        except Exception as e:
            return {
                **state,
                "analyzers_result": {
                    "success": False,
                    "error": str(e),
                },
                "errors": state.get("errors", []) + [f"AnalyzersHandlerAgent: {e}"],
                "completed_steps": state.get("completed_steps", []) + ["analyzers_handler"],
            }
    
    def _list_analyzers(self) -> List[Dict[str, Any]]:
        """列出可用的分析器"""
        from evaluator.core import list_analyzers
        
        analyzers = list_analyzers()
        
        return [
            {
                "name": a.name,
                "description": a.description,
                "enabled": a.enabled,
            }
            for a in analyzers
        ]
