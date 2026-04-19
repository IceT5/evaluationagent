"""智能分析流水线 Agent - 编排后台智能 Agent 链

执行流程：
StorageAgent → RecommendationAgent → ReflectionAgent

将结果保存到 storage_dir/insights.json
"""
from typing import Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from langgraph.graph import StateGraph, END
    from evaluator.llm import LLMClient

try:
    from langgraph.graph import StateGraph, END
    HAS_LANGGRAPH = True
except ImportError:
    HAS_LANGGRAPH = False
    StateGraph = None  # type: ignore
    END = None

try:
    from evaluator.llm import LLMClient
    HAS_LLM = True
except ImportError:
    HAS_LLM = False
    LLMClient = None  # type: ignore

from evaluator.agents.base_agent import BaseAgent, AgentMeta


class IntelligencePipeline(BaseAgent):
    """智能分析流水线 Agent
    
    编排以下 Agent 执行智能分析：
    - StorageAgent: 存储当前分析结果
    - RecommendationAgent: 生成改进建议
    - ReflectionAgent: 执行反思和性能分析
    
    执行流程：
    StorageAgent → RecommendationAgent → ReflectionAgent
    
    可选支持并行执行（如果 Agent 之间无依赖）。
    """
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="IntelligencePipeline",
            description="执行智能分析流水线：存储→推荐→反思",
            category="orchestration",
            inputs=["project_name", "storage_dir", "cicd_analysis"],
            outputs=["similar_projects", "recommendations", "reflection_result"],
            dependencies=["RecommendationAgent", "ReflectionAgent"],
        )
    
    def __init__(self, llm: Optional["LLMClient"] = None):  # type: ignore[type-arg, valid-type]
        super().__init__()
        self.llm = llm
        self._graph = None
    
    def _create_graph(self):
        """创建 LangGraph 工作流
        
        当前流程（顺序执行）:
        storage → recommendation → reflection → END
        
        未来可扩展为并行执行:
        ┌─────────────┐
        │   storage   │
        └──────┬──────┘
               │
        ┌──────▼──────┐
        │recommendation│
        └──────┬──────┘
               │
        ┌──────▼──────┐
        │ reflection  │
        └──────┬──────┘
               │
              END
        """
        if not HAS_LANGGRAPH:
            return None
        
        from evaluator.agents import StorageAgent, RecommendationAgent, ReflectionAgent
        
        storage_agent = StorageAgent()
        recommendation_agent = RecommendationAgent(llm=self.llm)
        reflection_agent = ReflectionAgent(llm=self.llm)
        
        workflow = StateGraph(Dict[str, Any])  # type: ignore[arg-type, call-arg]
        
        def storage_node(state: Dict[str, Any]) -> Dict[str, Any]:
            return storage_agent.safe_run(state)
        
        def recommendation_node(state: Dict[str, Any]) -> Dict[str, Any]:
            return recommendation_agent.safe_run(state)
        
        def reflection_node(state: Dict[str, Any]) -> Dict[str, Any]:
            return reflection_agent.safe_run(state)
        
        workflow.add_node("storage", storage_node)  # type: ignore[misc]
        workflow.add_node("recommendation", recommendation_node)  # type: ignore[misc]
        workflow.add_node("reflection", reflection_node)  # type: ignore[misc]
        
        workflow.set_entry_point("storage")
        workflow.add_edge("storage", "recommendation")
        workflow.add_edge("recommendation", "reflection")
        workflow.add_edge("reflection", END)  # type: ignore[arg-type]
        
        return workflow.compile()
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行智能分析流水线
        
        Args:
            state: 当前状态，包含 project_name, storage_dir, cicd_analysis 等
        
        Returns:
            更新后的状态，包含 similar_projects, recommendations, reflection_result
        """
        if HAS_LANGGRAPH and self._graph is None:
            self._graph = self._create_graph()
        
        if self._graph is not None:
            return self._graph.invoke(state)
        else:
            return self._run_sequential(state)
    
    # TODO: 待讨论是否移除此方法（同orchestrator._run_sequential）
    def _run_sequential(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """顺序执行（无 LangGraph 时回退）
        
        TODO: 待讨论是否移除此方法
        - 如果项目强制使用LangGraph，此方法可能不需要
        """
        from evaluator.agents import StorageAgent, RecommendationAgent, ReflectionAgent
        
        current_state = state.copy()
        
        storage_agent = StorageAgent()
        current_state = storage_agent.safe_run(current_state)
        
        recommendation_agent = RecommendationAgent(llm=self.llm)
        current_state = recommendation_agent.safe_run(current_state)
        
        reflection_agent = ReflectionAgent(llm=self.llm)
        current_state = reflection_agent.safe_run(current_state)
        
        return current_state
