"""对比工作流图定义"""
from typing import Optional, Dict, Any

try:
    from langgraph.graph import StateGraph, END
    HAS_LANGGRAPH = True
except ImportError:
    HAS_LANGGRAPH = False

try:
    from evaluator.llm import LLMClient
    HAS_LLM = True
except ImportError:
    HAS_LLM = False
    LLMClient = None

from evaluator.state import EvaluatorState
from storage.manager import StorageManager


def create_compare_graph(
    llm_config: Optional[Dict[str, Any]] = None,
    storage_dir: Optional[str] = None,
) -> Optional[Any]:
    """创建对比工作流
    
    工作流定义：
    compare → end
    
    Args:
        llm_config: LLM 配置
        storage_dir: 存储目录
    
    Returns:
        编译后的图
    """
    if not HAS_LANGGRAPH:
        return None
    
    llm = None
    if llm_config and HAS_LLM:
        try:
            llm = LLMClient(**llm_config)
        except Exception:
            pass
    
    storage = StorageManager(data_dir=storage_dir) if storage_dir else StorageManager()
    
    workflow = StateGraph(EvaluatorState)
    
    workflow.add_node("compare", _CompareNode(llm, storage))
    
    workflow.set_entry_point("compare")
    workflow.add_edge("compare", END)
    
    return workflow.compile()


class _CompareNode:
    """对比节点"""
    
    def __init__(self, llm, storage):
        self.llm = llm
        self.storage = storage
    
    def __call__(self, state: EvaluatorState) -> Dict[str, Any]:
        from evaluator.agents.compare_agent import CompareAgent
        
        project_a = state.get("project_a", "")
        project_b = state.get("project_b", "")
        dimensions = state.get("dimensions")
        
        print(f"\n[Compare] 对比 {project_a} vs {project_b}")
        
        try:
            compare_agent = CompareAgent(llm=self.llm, storage_manager=self.storage)
            input_data = {
                "project_a": project_a,
                "project_b": project_b,
                "version_a": state.get("version_a"),
                "version_b": state.get("version_b"),
                "dimensions": dimensions,
            }
            result = compare_agent.run(input_data)
            
            return {
                **state,
                "comparison_result": result,
                "errors": [],
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                **state,
                "comparison_result": None,
                "errors": [f"对比失败: {e}"],
            }
