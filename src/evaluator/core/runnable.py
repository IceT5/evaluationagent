"""Core Functions - 封装为 Runnable，支持 LangSmith 追踪"""
from typing import Optional, Dict, Any, List
from functools import wraps

from .analyze import analyze_project as _analyze_project
from .compare import compare_projects as _compare_projects
from .types import AnalysisResult, ComparisonResult

LANCHAIN_AVAILABLE = False
try:
    from langchain_core.runnables import RunnableLambda, RunnablePassthrough
    from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
    LANCHAIN_AVAILABLE = True
except ImportError:
    RunnableLambda = None
    RunnablePassthrough = None


def create_analyze_runnable():
    """创建分析 Runnable
    
    Returns:
        Runnable: 可追踪的分析 Runnable
    """
    if not LANCHAIN_AVAILABLE:
        return _analyze_project
    
    from evaluator.llm.tracing import traceable_agent
    from evaluator.llm import LLMClient
    
    @traceable_agent(name="analyze_project")
    def analyze_with_config(input_data: Dict[str, Any]) -> AnalysisResult:
        """带配置的分析"""
        path = input_data.get("path")
        types = input_data.get("types", ["cicd"])
        display_name = input_data.get("display_name")
        llm_config = input_data.get("llm_config")
        
        return _analyze_project(
            path=path,
            types=types,
            display_name=display_name,
            llm_config=llm_config,
        )
    
    return RunnableLambda(analyze_with_config)


def create_compare_runnable():
    """创建对比 Runnable
    
    Returns:
        Runnable: 可追踪的对比 Runnable
    """
    if not LANCHAIN_AVAILABLE:
        return _compare_projects
    
    from evaluator.llm.tracing import traceable_agent
    
    @traceable_agent(name="compare_projects")
    def compare_with_config(input_data: Dict[str, Any]) -> ComparisonResult:
        """带配置的对比"""
        project_a = input_data.get("project_a")
        project_b = input_data.get("project_b")
        dimensions = input_data.get("dimensions")
        llm_config = input_data.get("llm_config")
        
        return _compare_projects(
            project_a=project_a,
            project_b=project_b,
            dimensions=dimensions,
            llm_config=llm_config,
        )
    
    return RunnableLambda(compare_with_config)


class AnalyzeRunnable:
    """分析 Runnable 封装类"""
    
    def __init__(self):
        self._runnable = create_analyze_runnable()
    
    def invoke(self, input_data: Dict[str, Any]) -> AnalysisResult:
        """同步调用"""
        if LANCHAIN_AVAILABLE and hasattr(self._runnable, 'invoke'):
            return self._runnable.invoke(input_data)
        return self._runnable(input_data)
    
    async def ainvoke(self, input_data: Dict[str, Any]) -> AnalysisResult:
        """异步调用"""
        if LANCHAIN_AVAILABLE and hasattr(self._runnable, 'ainvoke'):
            return await self._runnable.ainvoke(input_data)
        return self.invoke(input_data)
    
    def pipe(self, next_runnable):
        """管道操作"""
        if LANCHAIN_AVAILABLE and hasattr(self._runnable, 'pipe'):
            return self._runnable.pipe(next_runnable)
        raise NotImplementedError("Pipe requires LangChain")
    
    def __call__(self, input_data: Dict[str, Any]) -> AnalysisResult:
        """直接调用"""
        return self.invoke(input_data)


class CompareRunnable:
    """对比 Runnable 封装类"""
    
    def __init__(self):
        self._runnable = create_compare_runnable()
    
    def invoke(self, input_data: Dict[str, Any]) -> ComparisonResult:
        """同步调用"""
        if LANCHAIN_AVAILABLE and hasattr(self._runnable, 'invoke'):
            return self._runnable.invoke(input_data)
        return self._runnable(input_data)
    
    async def ainvoke(self, input_data: Dict[str, Any]) -> ComparisonResult:
        """异步调用"""
        if LANCHAIN_AVAILABLE and hasattr(self._runnable, 'ainvoke'):
            return await self._runnable.ainvoke(input_data)
        return self.invoke(input_data)
    
    def __call__(self, input_data: Dict[str, Any]) -> ComparisonResult:
        """直接调用"""
        return self.invoke(input_data)


analyze_runnable = AnalyzeRunnable()
compare_runnable = CompareRunnable()
