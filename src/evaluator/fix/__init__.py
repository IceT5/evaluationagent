"""修复模块 - 通用的报告修复工具库

模块组成：
- models: 数据模型（FixPosition, FixInstruction, FixResult）
- strategy: 修复策略（AnchorResolver, FixExecutor, MultiFileSync）
- method: 修复途径（DataFixMethod, LLMFixMethod）
- coordinator: 修复协调器（FixCoordinator）

使用方式：
    from evaluator.fix import FixCoordinator
    
    coordinator = FixCoordinator(ci_data, llm_client)
    result = coordinator.fix(report, issues, arch, summary)
"""
from .models import FixPosition, FixInstruction, FixResult
from .strategy import AnchorResolver, FixExecutor, MultiFileSync
from .method import FixMethod, DataFixMethod, LLMFixMethod
from .coordinator import FixCoordinator

__all__ = [
    "FixPosition",
    "FixInstruction", 
    "FixResult",
    "AnchorResolver",
    "FixExecutor",
    "MultiFileSync",
    "FixMethod",
    "DataFixMethod",
    "LLMFixMethod",
    "FixCoordinator",
]