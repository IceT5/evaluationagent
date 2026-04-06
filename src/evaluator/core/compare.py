# Core 对比函数 - 接口层

import time
from typing import List, Optional, Dict, Any

from storage import StorageManager
from .types import ComparisonResult


def compare_projects(
    project_a: str,
    project_b: str,
    version_a: Optional[str] = None,
    version_b: Optional[str] = None,
    dimensions: Optional[List[str]] = None,
    llm_config: Optional[Dict[str, Any]] = None,
    known_projects: Optional[List[str]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> ComparisonResult:
    """对比两个项目（统一使用main_graph）
    
    所有对比通过 LangGraph 工作流执行。
    LangGraph是必需依赖，不可用时会抛出ImportError。
    与CLI使用相同的initial_state结构，便于后续统一runnable。
    
    Args:
        project_a: 项目 A 名称
        project_b: 项目 B 名称
        version_a: 项目 A 版本（默认最新）
        version_b: 项目 B 版本（默认最新）
        dimensions: 对比维度列表，默认 ["complexity", "best_practices", "maintainability"]
        llm_config: LLM 配置（可选）
        known_projects: 已知项目列表（可选，用于补全）
        context: 上下文信息（可选，包含last_project等）
    
    Returns:
        ComparisonResult: 对比结果
    
    Raises:
        ImportError: LangGraph不可用
        Exception: 对比过程中的其他错误
    
    Example:
        # 基本用法
        result = compare_projects("proj1", "proj2")
        
        # 带版本
        result = compare_projects("proj1", "proj2", version_a="v1", version_b="v2")
        
        # 带维度
        result = compare_projects("proj1", "proj2", dimensions=["complexity"])
        
        # 带上下文（用于runnable）
        result = compare_projects(
            "proj1", "proj2",
            known_projects=["proj1", "proj2", "proj3"],
            context={"last_project": "proj1"}
        )
    """
    from evaluator.core.graphs import create_main_graph
    from evaluator.state import EvaluatorState
    
    start_time = time.time()
    
    # 创建main_graph（LangGraph是必需依赖）
    graph = create_main_graph(llm_config=llm_config)
    
    # 构造统一的initial_state（与CLI完全一致）
    initial_state: EvaluatorState = {
        # === 用户输入层 ===
        "user_input": f"/compare {project_a} {project_b}",
        "intent": "compare",
        "params": {
            "project_a": project_a,
            "project_b": project_b,
            "version_a": version_a,
            "version_b": version_b,
            "dimensions": dimensions,
        },
        
        # === 编排层 ===
        "orchestrator_decision": {
            "intent": "compare",
            "params": {
                "project_a": project_a,
                "project_b": project_b,
                "version_a": version_a,
                "version_b": version_b,
                "dimensions": dimensions,
            },
            "confidence": 1.0,
            "needs_clarification": False,
            "next_step": "compare",
        },
        
        # === 配置层 ===
        "llm_config": llm_config or {},
        
        # === 上下文层 ===
        "known_projects": known_projects or [],
        "context": context or {},
        
        # === 业务数据层 ===
        "project_a": project_a,
        "project_b": project_b,
        "version_a": version_a,
        "version_b": version_b,
        "dimensions": dimensions,
        
        # === 控制层 ===
        "completed_steps": [],
        "errors": [],
        "warnings": [],
    }
    
    # 执行工作流
    result = graph.invoke(initial_state)
    
    # 提取结果
    comparison_result = result.get("comparison_result")
    errors = result.get("errors", [])
    
    duration = time.time() - start_time
    
    if comparison_result:
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
            version_a=version_a,
            version_b=version_b,
            summary=f"对比失败: {errors[0] if errors else '未知错误'}",
            duration_seconds=duration,
        )
