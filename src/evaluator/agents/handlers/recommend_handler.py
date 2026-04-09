"""RecommendHandlerAgent - 处理 /recommend 命令"""
from typing import Dict, Any
from pathlib import Path

from evaluator.agents.base_agent import BaseAgent, AgentMeta


class RecommendHandlerAgent(BaseAgent):
    """处理 /recommend 命令的 Agent
    
    显示项目的改进建议。
    """
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="RecommendHandlerAgent",
            description="显示改进建议",
            category="handler",
            inputs=["project_name", "storage_dir"],
            outputs=["recommend_result"],
            dependencies=[],
        )
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行 /recommend 命令
        
        Args:
            state: 当前状态，包含 project_name, storage_dir
        
        Returns:
            更新后的状态，包含 recommend_result
        """
        try:
            project_name = state.get("project_name")
            storage_dir = state.get("storage_dir")
            
            if not project_name:
                return {
                    **state,
                    "recommend_result": {
                        "success": False,
                        "error": "未指定项目名称",
                    },
                    "errors": state.get("errors", []) + ["未指定项目名称"],
                    "completed_steps": state.get("completed_steps", []) + ["recommend_handler"],
                }
            
            insights_data = self._load_insights(project_name, storage_dir)
            
            if not insights_data:
                return {
                    **state,
                    "recommend_result": {
                        "success": False,
                        "error": f"未找到项目的智能分析结果: {project_name}",
                    },
                    "completed_steps": state.get("completed_steps", []) + ["recommend_handler"],
                }
            
            recommendations = insights_data.get("recommendations", [])
            
            return {
                **state,
                "recommend_result": {
                    "success": True,
                    "project_name": project_name,
                    "recommendations": recommendations,
                },
                "completed_steps": state.get("completed_steps", []) + ["recommend_handler"],
            }
            
        except Exception as e:
            return {
                **state,
                "recommend_result": {
                    "success": False,
                    "error": str(e),
                },
                "errors": state.get("errors", []) + [f"RecommendHandlerAgent: {e}"],
                "completed_steps": state.get("completed_steps", []) + ["recommend_handler"],
            }
    
    def _load_insights(self, project_name: str, storage_dir: str) -> Dict[str, Any]:
        """加载 insights.json"""
        import json
        
        if not storage_dir:
            from storage import StorageManager
            storage = StorageManager()
            version_dir = storage.get_latest_version_dir(project_name)
            if not version_dir:
                return {}
            insights_path = version_dir / "insights.json"
        else:
            insights_path = Path(storage_dir) / "insights.json"
        
        if not insights_path.exists():
            return {}
        
        with open(insights_path, "r", encoding="utf-8") as f:
            return json.load(f)
