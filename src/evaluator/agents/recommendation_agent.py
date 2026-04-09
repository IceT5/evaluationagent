"""推荐 Agent - 基于分析结果推荐最佳实践"""
import json
from typing import Optional, List, Dict, Any

try:
    from evaluator.llm import LLMClient
    HAS_LLM = True
except ImportError:
    HAS_LLM = False
    LLMClient = None

from evaluator.agents.base_agent import BaseAgent, AgentMeta


class RecommendationAgent(BaseAgent):
    """推荐 Agent
    
    职责：
    1. 基于分析结果推荐最佳实践
    2. 推荐相关文档和资源
    3. 推荐改进优先级
    4. 生成优化建议
    
    作为智能Agent，在分析完成后异步执行。
    """
    
    def __init__(self, llm: Optional["LLMClient"] = None):
        super().__init__()
        self.llm = llm
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="RecommendationAgent",
            description="生成改进建议和最佳实践推荐",
            category="intelligence",
            inputs=["cicd_analysis", "architecture_json"],
            outputs=["recommendations", "quick_wins"],
            dependencies=[],
        )
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行推荐分析
        
        基于分析结果生成改进建议。
        """
        print(f"  [RecommendationAgent] 生成改进建议...")
        
        cicd_analysis = state.get("cicd_analysis", {})
        architecture_json = state.get("architecture_json", {})
        
        recs = self.recommend(cicd_analysis)
        prioritized = self.recommend_priority(cicd_analysis)
        quick_wins = self.get_quick_wins(cicd_analysis)
        
        return {
            **state,
            "recommendations": prioritized,
            "quick_wins": quick_wins,
            "best_practices": recs.get("best_practices", []),
        }
    
    BEST_PRACTICES = {
        "workflow_structure": [
            "使用矩阵策略并行执行多个 job",
            "将重复步骤提取为 reusable workflow",
            "使用 composite action 复用步骤",
            "避免在 workflow 中硬编码敏感信息",
        ],
        "caching": [
            "使用 actions/cache 缓存依赖",
            "使用 actions/setup-* 的内置缓存",
            "为缓存设置合理的 key",
        ],
        "security": [
            "最小权限原则配置 permissions",
            "使用 OpenID Connect 进行认证",
            "定期更新 action 版本",
            "使用 secrets 管理敏感信息",
        ],
        "performance": [
            "并行执行独立的 job",
            "使用 concurrency 控制并发",
            "避免不必要的 checkout",
            "使用 shallow clone 减少传输",
        ],
        "maintainability": [
            "使用有意义的 job 和 step 名称",
            "添加注释说明复杂逻辑",
            "将长 workflow 拆分为多个",
            "统一命名规范",
        ],
    }
    
    DOCUMENTATION = {
        "github_actions": "https://docs.github.com/en/actions",
        "workflow_syntax": "https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions",
        "reusable_workflows": "https://docs.github.com/en/actions/using-workflows/reusing-workflows",
        "caching": "https://docs.github.com/en/actions/using-workflows/caching-dependencies-to-speed-up-workflows",
        "security": "https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions",
    }
    
    def recommend(
        self,
        analysis_result: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """生成推荐
        
        Args:
            analysis_result: 分析结果
            context: 上下文信息
        
        Returns:
            推荐结果
        """
        if not analysis_result:
            return {"recommendations": [], "best_practices": [], "resources": []}
        
        recommendations = []
        best_practices = []
        resources = []
        
        scores = analysis_result.get("scores", {})
        
        if scores:
            low_score_areas = [(k, v) for k, v in scores.items() if isinstance(v, (int, float)) and v < 0.6]
            
            for area, score in low_score_areas:
                area_recs = self._get_recommendations_for_area(area, score)
                recommendations.extend(area_recs)
        
        architecture = analysis_result.get("architecture", {})
        
        if not architecture.get("has_caching"):
            recommendations.append({
                "priority": "high",
                "category": "caching",
                "title": "建议启用依赖缓存",
                "description": "未检测到缓存配置，建议为依赖添加缓存以加速 workflow 执行",
                "action": "添加 actions/cache 或使用 setup-* action 的内置缓存",
            })
        
        if not architecture.get("has_reusable_workflows"):
            workflow_count = architecture.get("stages", [])
            total_workflows = sum(len(s.get("workflows", [])) for s in workflow_count)
            if total_workflows > 10:
                recommendations.append({
                    "priority": "medium",
                    "category": "maintainability",
                    "title": "考虑抽取可复用 workflow",
                    "description": f"项目有 {total_workflows} 个工作流，建议将重复逻辑抽取为 reusable workflow",
                    "action": "创建 .github/workflows/reusable-*.yml 文件",
                })
        
        best_practices = self._get_applicable_best_practices(architecture)
        resources = self._get_relevant_resources(architecture)
        
        return {
            "recommendations": recommendations,
            "best_practices": best_practices,
            "resources": resources,
        }
    
    def _get_recommendations_for_area(
        self,
        area: str,
        score: float,
    ) -> List[Dict[str, Any]]:
        """获取特定领域的推荐"""
        recommendations = []
        
        area_map = {
            "complexity": ("complexity", "降低工作流复杂度"),
            "best_practices": ("best_practices", "改进最佳实践"),
            "maintainability": ("maintainability", "提升可维护性"),
            "performance": ("performance", "优化性能"),
            "security": ("security", "加强安全性"),
        }
        
        if area in area_map:
            category, title = area_map[area]
            
            recommendations.append({
                "priority": "high" if score < 0.4 else "medium",
                "category": category,
                "title": f"需要改进: {title}",
                "description": f"当前得分: {score:.0%}",
                "action": f"参考 {category} 相关的最佳实践",
            })
        
        return recommendations
    
    def _get_applicable_best_practices(
        self,
        architecture: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """获取适用的最佳实践"""
        practices = []
        
        if not architecture.get("has_matrix_build"):
            practices.append({
                "category": "workflow_structure",
                "title": "考虑使用矩阵策略",
                "description": "矩阵可以并行执行多个配置组合，减少重复的 job 定义",
                "example": "strategy:\\n  matrix:\\n    os: [ubuntu-latest, windows-latest]",
            })
        
        if not architecture.get("has_caching"):
            practices.append({
                "category": "caching",
                "title": "启用依赖缓存",
                "description": "缓存依赖可以显著加速 workflow 执行",
                "example": "uses: actions/cache@v4\\nwith:\\n  path: ~/.npm\\n  key: ${{ runner.os }}-npm-${{ hashFiles('**/package-lock.json') }}",
            })
        
        return practices
    
    def _get_relevant_resources(
        self,
        architecture: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """获取相关资源"""
        resources = []
        
        resources.append({
            "title": "GitHub Actions 官方文档",
            "url": self.DOCUMENTATION["github_actions"],
            "category": "documentation",
        })
        
        if not architecture.get("has_reusable_workflows"):
            resources.append({
                "title": "Reusable Workflows 指南",
                "url": self.DOCUMENTATION["reusable_workflows"],
                "category": "documentation",
            })
        
        if not architecture.get("has_caching"):
            resources.append({
                "title": "Caching 最佳实践",
                "url": self.DOCUMENTATION["caching"],
                "category": "documentation",
            })
        
        resources.append({
            "title": "安全加固指南",
            "url": self.DOCUMENTATION["security"],
            "category": "security",
        })
        
        return resources
    
    def recommend_priority(
        self,
        analysis_result: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """推荐改进优先级
        
        Args:
            analysis_result: 分析结果
        
        Returns:
            按优先级排序的改进建议
        """
        recommendations = self.recommend(analysis_result).get("recommendations", [])
        
        priority_order = {"high": 0, "medium": 1, "low": 2}
        recommendations.sort(key=lambda x: priority_order.get(x.get("priority", "low"), 2))
        
        return recommendations
    
    def generate_summary(
        self,
        recommendations: List[Dict[str, Any]],
    ) -> str:
        """生成推荐摘要
        
        Args:
            recommendations: 推荐列表
        
        Returns:
            格式化摘要
        """
        if not recommendations:
            return "恭喜！项目在所有方面都表现良好，无需特别改进。"
        
        high_priority = [r for r in recommendations if r.get("priority") == "high"]
        medium_priority = [r for r in recommendations if r.get("priority") == "medium"]
        
        summary = []
        summary.append(f"共发现 {len(recommendations)} 项改进建议：")
        
        if high_priority:
            summary.append(f"\n高优先级 ({len(high_priority)} 项)：")
            for r in high_priority:
                summary.append(f"  • {r.get('title')}: {r.get('description', '')[:50]}...")
        
        if medium_priority:
            summary.append(f"\n中优先级 ({len(medium_priority)} 项)：")
            for r in medium_priority:
                summary.append(f"  • {r.get('title')}")
        
        return "\n".join(summary)
    
    def recommend_comparable_projects(
        self,
        project_name: str,
        storage_agent,
    ) -> List[Dict[str, Any]]:
        """推荐可对比的项目
        
        Args:
            project_name: 项目名称
            storage_agent: StorageAgent 实例
        
        Returns:
            可对比的项目列表
        """
        try:
            similar = storage_agent.find_similar_projects(project_name, limit=3)
            return similar
        except:
            return []
    
    def get_quick_wins(
        self,
        analysis_result: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """获取快速改进项（低投入高回报）
        
        Args:
            analysis_result: 分析结果
        
        Returns:
            快速改进列表
        """
        quick_wins = []
        
        architecture = analysis_result.get("architecture", {})
        
        if not architecture.get("has_caching"):
            quick_wins.append({
                "title": "添加依赖缓存",
                "effort": "low",
                "impact": "high",
                "description": "只需添加 3-5 行配置即可显著加速 workflow",
                "action": "在 job 中添加 actions/cache action",
            })
        
        scores = analysis_result.get("scores", {})
        if scores.get("performance", 1.0) < 0.7:
            quick_wins.append({
                "title": "启用并发控制",
                "effort": "low",
                "impact": "medium",
                "description": "添加 concurrency 配置避免重复运行",
                "action": "添加 concurrency: ${{ github.workflow }}-${{ github.ref }}",
            })
        
        return quick_wins
