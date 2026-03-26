"""数据提取 Agent - 提取 CI/CD 配置数据"""
from pathlib import Path
from typing import Optional, Dict, Any

from evaluator.skills import CIAnalyzer
from .state import CICDState
from evaluator.agents.base_agent import BaseAgent, AgentMeta


class DataExtractionAgent(BaseAgent):
    """数据提取 Agent
    
    职责：从项目目录提取 CI/CD 配置数据
    输入：CICDState.project_path
    输出：CICDState.ci_data, ci_data_path, workflow_count
    """
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="DataExtractionAgent",
            description="从项目目录提取 CI/CD 配置数据",
            category="analysis",
            inputs=["project_path", "storage_dir"],
            outputs=["ci_data", "ci_data_path", "workflow_count", "strategy"],
            dependencies=[],
        )
    
    def __init__(self):
        super().__init__()
        self.ci_analyzer = CIAnalyzer()
    
    def run(self, state: CICDState) -> CICDState:
        """执行数据提取"""
        project_path = state.get("project_path")
        storage_dir = state.get("storage_dir")
        
        if not project_path:
            return {
                **state,
                "errors": state.get("errors", []) + ["项目路径未设置"],
            }
        
        output_dir = Path(storage_dir) if storage_dir else Path(project_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        ci_data_path = str(output_dir / "ci_data.json")
        ci_data = self.ci_analyzer.extract_data(project_path, ci_data_path)
        
        workflows_count = len(ci_data.get("workflows", {}))
        actions_count = len(ci_data.get("actions", []))
        
        print(f"  [DataExtraction] 发现 {workflows_count} 个工作流, {actions_count} 个 Action")
        
        if workflows_count == 0:
            return {
                **state,
                "ci_data": ci_data,
                "ci_data_path": ci_data_path,
                "workflow_count": 0,
                "strategy": "skip",
                "cicd_analysis": {
                    "status": "no_cicd",
                    "message": "项目未使用 GitHub Actions",
                    "workflows_count": 0,
                    "actions_count": 0,
                },
            }
        
        return {
            **state,
            "ci_data": ci_data,
            "ci_data_path": ci_data_path,
            "workflow_count": workflows_count,
            "errors": [],
        }
