# Core 对比函数 - 接口层

import time
from typing import List, Optional, Dict, Any

from storage import StorageManager
from .types import ComparisonResult

try:
    from evaluator.llm import LLMClient
    HAS_LLM = True
except ImportError:
    HAS_LLM = False


def compare_projects(
    project_a: str,
    project_b: str,
    version_a: Optional[str] = None,
    version_b: Optional[str] = None,
    dimensions: Optional[List[str]] = None,
    llm_config: Optional[Dict[str, Any]] = None,
    use_graph: bool = False,
) -> ComparisonResult:
    """
    对比两个项目（接口层）

    实际业务逻辑由 CompareAgent 执行
    
    Args:
        project_a: 项目 A 名称
        project_b: 项目 B 名称
        version_a: 项目 A 版本（默认最新）
        version_b: 项目 B 版本（默认最新）
        dimensions: 对比维度列表，默认 ["complexity", "best_practices", "maintainability"]
        llm_config: LLM 配置（可选），包含 model, api_key, base_url 等
        use_graph: 是否使用 LangGraph 工作流（默认 False）

    Returns:
        ComparisonResult: 对比结果
    """
    if use_graph:
        return _compare_with_graph(
            project_a, project_b, version_a, version_b, dimensions, llm_config
        )
    return _compare_direct(
        project_a, project_b, version_a, version_b, dimensions, llm_config
    )


def _compare_direct(
    project_a: str,
    project_b: str,
    version_a: Optional[str],
    version_b: Optional[str],
    dimensions: Optional[List[str]],
    llm_config: Optional[Dict[str, Any]],
) -> ComparisonResult:
    """直接调用 CompareAgent"""
    from evaluator.agents import CompareAgent

    start_time = time.time()
    storage = StorageManager()

    llm = None
    if llm_config and HAS_LLM:
        try:
            kwargs = {}
            if llm_config.get("api_key"):
                kwargs["api_key"] = llm_config["api_key"]
            if llm_config.get("base_url"):
                kwargs["base_url"] = llm_config["base_url"]
            if llm_config.get("model"):
                kwargs["model"] = llm_config["model"]
            llm = LLMClient(**kwargs) if kwargs else None
        except Exception:
            pass

    agent = CompareAgent(storage_manager=storage, llm=llm)

    input_data = {
        "project_a": project_a,
        "project_b": project_b,
        "version_a": version_a,
        "version_b": version_b,
        "dimensions": dimensions,
    }

    try:
        result = agent.run(input_data)

        if "error" in result:
            return ComparisonResult(
                success=False,
                comparison_id="",
                project_a=project_a,
                project_b=project_b,
                summary=result["error"],
            )

        duration = time.time() - start_time

        return ComparisonResult(
            success=True,
            comparison_id=result.get("comparison_id", ""),
            project_a=result.get("project_a", project_a),
            project_b=result.get("project_b", project_b),
            version_a=result.get("version_a"),
            version_b=result.get("version_b"),
            dimensions=result.get("dimensions", []),
            semantic_diff=result.get("semantic_diff"),
            summary=result.get("summary", ""),
            recommendations=result.get("recommendations", []),
            duration_seconds=duration,
        )

    except Exception as e:
        return ComparisonResult(
            success=False,
            comparison_id="",
            project_a=project_a,
            project_b=project_b,
            summary=f"对比失败: {str(e)}",
        )


def _compare_with_graph(
    project_a: str,
    project_b: str,
    version_a: Optional[str],
    version_b: Optional[str],
    dimensions: Optional[List[str]],
    llm_config: Optional[Dict[str, Any]],
) -> ComparisonResult:
    """使用 LangGraph 工作流对比"""
    try:
        from evaluator.core.graphs import create_compare_graph
        from evaluator.state import EvaluatorState
        
        start_time = time.time()
        
        graph = create_compare_graph(llm_config=llm_config)
        
        if graph is None:
            return _compare_direct(project_a, project_b, version_a, version_b, dimensions, llm_config)
        
        initial_state: EvaluatorState = {
            "project_a": project_a,
            "project_b": project_b,
            "version_a": version_a,
            "version_b": version_b,
            "dimensions": dimensions,
            "comparison_result": None,
            "errors": [],
        }
        
        result = graph.invoke(initial_state)
        
        comparison_result = result.get("comparison_result")
        
        if comparison_result:
            duration = time.time() - start_time
            return ComparisonResult(
                success=True,
                comparison_id=comparison_result.get("comparison_id", ""),
                project_a=comparison_result.get("project_a", project_a),
                project_b=comparison_result.get("project_b", project_b),
                version_a=comparison_result.get("version_a"),
                version_b=comparison_result.get("version_b"),
                dimensions=comparison_result.get("dimensions", []),
                semantic_diff=comparison_result.get("semantic_diff"),
                summary=comparison_result.get("summary", ""),
                recommendations=comparison_result.get("recommendations", []),
                duration_seconds=duration,
            )
        else:
            return ComparisonResult(
                success=False,
                comparison_id="",
                project_a=project_a,
                project_b=project_b,
                summary="对比失败",
            )
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return _compare_direct(project_a, project_b, version_a, version_b, dimensions, llm_config)
