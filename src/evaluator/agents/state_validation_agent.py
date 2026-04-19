"""状态验证 Agent - 验证状态完整性"""
from typing import Dict, Any, List
from evaluator.agents.base_agent import BaseAgent, AgentMeta


class StateValidationAgent(BaseAgent):
    """状态验证 Agent
    
    验证状态完整性，检查必要字段和步骤顺序。
    """
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="StateValidationAgent",
            description="验证状态完整性",
            category="validation",
            inputs=["current_step", "completed_steps"],
            outputs=["validation_result"],
            dependencies=[],
        )
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        issues: List[str] = []
        
        required_fields = ["project_name", "project_path"]
        for field in required_fields:
            if not state.get(field):
                issues.append(f"缺失必要字段: {field}")
        
        completed = state.get("completed_steps", [])
        current = state.get("current_step")
        if current and current in completed:
            issues.append(f"当前步骤 {current} 已完成（重复执行）")
        
        intent = state.get("intent")
        if not intent:
            issues.append("缺失字段: intent")
        
        return {
            **state,
            "validation_result": {
                "valid": len(issues) == 0,
                "issues": issues,
            },
        }
