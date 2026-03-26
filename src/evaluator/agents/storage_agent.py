"""智能存储 Agent - 智能检索和推荐"""
import json
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

try:
    from evaluator.llm import LLMClient
    HAS_LLM = True
except ImportError:
    HAS_LLM = False
    LLMClient = None

from storage import StorageManager
from evaluator.agents.base_agent import BaseAgent, AgentMeta


class StorageAgent(BaseAgent):
    """智能存储 Agent
    
    职责：
    1. 智能检索相似项目
    2. 推荐可对比的项目对
    3. 分析项目历史趋势
    4. 搜索项目内容
    
    作为智能Agent，在分析完成后异步执行。
    """
    
    def __init__(
        self,
        storage: Optional[StorageManager] = None,
        llm: Optional["LLMClient"] = None,
    ):
        super().__init__()
        self.storage = storage or StorageManager()
        self.llm = llm
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="StorageAgent",
            description="智能存储、相似项目检索、趋势分析",
            category="intelligence",
            inputs=["project_name", "ci_data", "storage_dir"],
            outputs=["similar_projects", "comparison_suggestions", "project_trends"],
            dependencies=["ReporterAgent"],
        )
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行智能存储分析
        
        读取项目数据，分析相似项目并生成推荐。
        """
        project_name = state.get("project_name")
        storage_dir = state.get("storage_dir")
        
        if not project_name:
            return {**state, "errors": state.get("errors", []) + ["StorageAgent: 缺少project_name"]}
        
        print(f"  [StorageAgent] 分析相似项目...")
        
        similar = self.find_similar_projects(project_name, limit=5)
        suggestions = self.suggest_comparisons(limit=5)
        trends = self.analyze_trends(project_name)
        
        return {
            **state,
            "similar_projects": similar,
            "comparison_suggestions": suggestions,
            "project_trends": trends,
        }
    
    def find_similar_projects(
        self,
        project_name: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """找到架构相似的项目
        
        Args:
            project_name: 目标项目名称
            limit: 返回数量
        
        Returns:
            相似项目列表，按相似度排序
        """
        target_data = self.storage.load_project(project_name)
        if not target_data:
            return []
        
        target_ci = target_data.get("ci_data", {})
        target_summary = target_data.get("metadata", {})
        
        all_projects = self.storage.list_projects()
        similarities = []
        
        for other_name in all_projects:
            if other_name == project_name:
                continue
            
            other_data = self.storage.load_project(other_name)
            if not other_data:
                continue
            
            other_ci = other_data.get("ci_data", {})
            
            similarity = self._calculate_similarity(target_ci, other_ci)
            
            similarities.append({
                "name": other_name,
                "similarity": similarity,
                "target_workflows": len(target_ci.get("workflows", {})),
                "other_workflows": len(other_ci.get("workflows", {})),
            })
        
        similarities.sort(key=lambda x: x["similarity"], reverse=True)
        
        return similarities[:limit]
    
    def _calculate_similarity(
        self,
        ci_data_a: dict,
        ci_data_b: dict,
    ) -> float:
        """计算两个项目的架构相似度"""
        workflows_a = set(ci_data_a.get("workflows", {}).keys())
        workflows_b = set(ci_data_b.get("workflows", {}).keys())
        
        if not workflows_a or not workflows_b:
            return 0.0
        
        intersection = len(workflows_a & workflows_b)
        union = len(workflows_a | workflows_b)
        
        jaccard = intersection / union if union > 0 else 0
        
        triggers_a = set()
        triggers_b = set()
        
        for wf in ci_data_a.get("workflows", {}).values():
            triggers_a.update(wf.get("triggers", []))
        for wf in ci_data_b.get("workflows", {}).values():
            triggers_b.update(wf.get("triggers", []))
        
        trigger_similarity = len(triggers_a & triggers_b) / len(triggers_a | triggers_b) if triggers_a or triggers_b else 0
        
        actions_a = set(a.get("name", "") for a in ci_data_a.get("actions", []))
        actions_b = set(a.get("name", "") for a in ci_data_b.get("actions", []))
        
        common_actions = len(actions_a & actions_b)
        action_similarity = common_actions / max(len(actions_a), len(actions_b)) if actions_a or actions_b else 0
        
        return (jaccard * 0.5 + trigger_similarity * 0.3 + action_similarity * 0.2)
    
    def suggest_comparisons(
        self,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """建议值得对比的项目对
        
        Args:
            limit: 返回数量
        
        Returns:
            推荐对比的项目对列表
        """
        all_projects = self.storage.list_projects()
        suggestions = []
        
        for i, project_a in enumerate(all_projects):
            data_a = self.storage.load_project(project_a)
            if not data_a:
                continue
            
            ci_a = data_a.get("ci_data", {})
            workflows_a = len(ci_a.get("workflows", {}))
            
            for project_b in all_projects[i + 1:]:
                if project_a == project_b:
                    continue
                
                data_b = self.storage.load_project(project_b)
                if not data_b:
                    continue
                
                ci_b = data_b.get("ci_data", {})
                workflows_b = len(ci_b.get("workflows", {}))
                
                size_diff = abs(workflows_a - workflows_b)
                size_ratio = min(workflows_a, workflows_b) / max(workflows_a, workflows_b) if max(workflows_a, workflows_b) > 0 else 1
                
                similarity = self._calculate_similarity(ci_a, ci_b)
                
                if size_ratio >= 0.3 and similarity > 0.1:
                    score = similarity * 0.6 + size_ratio * 0.4
                    suggestions.append({
                        "project_a": project_a,
                        "project_b": project_b,
                        "score": score,
                        "similarity": similarity,
                        "size_ratio": size_ratio,
                        "workflows_a": workflows_a,
                        "workflows_b": workflows_b,
                    })
        
        suggestions.sort(key=lambda x: x["score"], reverse=True)
        
        return suggestions[:limit]
    
    def analyze_trends(
        self,
        project_name: str,
    ) -> Optional[Dict[str, Any]]:
        """分析项目历史趋势
        
        Args:
            project_name: 项目名称
        
        Returns:
            趋势分析结果
        """
        versions = self.storage.list_versions(project_name)
        
        if len(versions) < 2:
            return None
        
        trends = []
        
        for version_id in versions:
            data = self.storage.load_project(project_name, version_id)
            if not data:
                continue
            
            ci_data = data.get("ci_data", {})
            workflows_count = len(ci_data.get("workflows", {}))
            jobs_count = sum(len(wf.get("jobs", {})) for wf in ci_data.get("workflows", {}).values())
            actions_count = len(ci_data.get("actions", []))
            
            trends.append({
                "version": version_id,
                "workflows_count": workflows_count,
                "jobs_count": jobs_count,
                "actions_count": actions_count,
                "analyzed_at": data.get("metadata", {}).get("analyzed_at", ""),
            })
        
        if not trends:
            return None
        
        workflow_trend = "stable"
        if len(trends) >= 2:
            first = trends[0]["workflows_count"]
            last = trends[-1]["workflows_count"]
            if last > first * 1.2:
                workflow_trend = "increasing"
            elif last < first * 0.8:
                workflow_trend = "decreasing"
        
        return {
            "project_name": project_name,
            "version_count": len(trends),
            "workflow_trend": workflow_trend,
            "versions": trends,
        }
    
    def search_projects(
        self,
        query: str,
        search_in: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """搜索项目
        
        Args:
            query: 搜索关键词
            search_in: 搜索字段列表
        
        Returns:
            匹配的项目列表
        """
        if search_in is None:
            search_in = ["name", "workflow_names", "actions"]
        
        all_projects = self.storage.list_projects()
        results = []
        query_lower = query.lower()
        
        for project_name in all_projects:
            data = self.storage.load_project(project_name)
            if not data:
                continue
            
            matches = []
            
            if "name" in search_in:
                if query_lower in project_name.lower():
                    matches.append("name")
            
            ci_data = data.get("ci_data", {})
            
            if "workflow_names" in search_in:
                for wf_name in ci_data.get("workflows", {}).keys():
                    if query_lower in wf_name.lower():
                        matches.append(f"workflow: {wf_name}")
                        break
            
            if "actions" in search_in:
                for action in ci_data.get("actions", []):
                    action_name = action.get("name", "")
                    if query_lower in action_name.lower():
                        matches.append(f"action: {action_name}")
                        break
            
            if matches:
                results.append({
                    "name": project_name,
                    "matches": matches,
                    "workflows_count": len(ci_data.get("workflows", {})),
                })
        
        return results
    
    def get_project_summary(
        self,
        project_name: str,
    ) -> Optional[Dict[str, Any]]:
        """获取项目摘要
        
        Args:
            project_name: 项目名称
        
        Returns:
            项目摘要信息
        """
        data = self.storage.load_project(project_name)
        if not data:
            return None
        
        ci_data = data.get("ci_data", {})
        metadata = data.get("metadata", {})
        
        triggers = set()
        for wf in ci_data.get("workflows", {}).values():
            triggers.update(wf.get("triggers", []))
        
        jobs_total = sum(len(wf.get("jobs", {})) for wf in ci_data.get("workflows", {}).values())
        
        return {
            "name": project_name,
            "display_name": metadata.get("display_name", project_name),
            "workflows_count": len(ci_data.get("workflows", {})),
            "jobs_count": jobs_total,
            "actions_count": len(ci_data.get("actions", [])),
            "scripts_count": len(ci_data.get("scripts", [])),
            "triggers": list(triggers),
            "analyzed_at": metadata.get("analyzed_at", ""),
            "source_url": metadata.get("source_url"),
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取存储统计信息"""
        all_projects = self.storage.list_projects()
        
        total_workflows = 0
        total_actions = 0
        projects_with_cicd = 0
        
        for project_name in all_projects:
            data = self.storage.load_project(project_name)
            if data:
                ci_data = data.get("ci_data", {})
                workflows = len(ci_data.get("workflows", {}))
                if workflows > 0:
                    projects_with_cicd += 1
                    total_workflows += workflows
                    total_actions += len(ci_data.get("actions", []))
        
        return {
            "total_projects": len(all_projects),
            "projects_with_cicd": projects_with_cicd,
            "total_workflows": total_workflows,
            "total_actions": total_actions,
            "avg_workflows_per_project": total_workflows / len(all_projects) if all_projects else 0,
        }
