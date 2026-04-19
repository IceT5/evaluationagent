"""统一并发执行工具 - 支持LangSmith Trace关联

设计原则:
1. 所有并发执行必须通过此模块
2. 自动使用RunnableParallel关联trace
3. 分批执行限制并发数
"""
from typing import List, Callable, TypeVar, Dict, Any, Optional
from langchain_core.runnables import RunnableParallel, RunnableLambda

R = TypeVar('R')


def parallel_execute(
    tasks: List[Callable[[], R]],
    max_concurrent: int = 4,
    task_names: Optional[List[str]] = None,
) -> List[R]:
    """并发执行多个任务（统一入口）
    
    自动使用RunnableParallel关联LangSmith trace。
    
    Args:
        tasks: 任务列表，每个任务是 Callable[[], R]
        max_concurrent: 最大并发数
        task_names: 任务名称列表（用于trace标识，可选）
    
    Returns:
        结果列表，顺序与tasks对应
    
    Example:
        def task1(): return "result1"
        def task2(): return "result2"
        
        results = parallel_execute([task1, task2], max_concurrent=2)
        # results = ["result1", "result2"]
    """
    if not tasks:
        return []
    
    results = []
    total = len(tasks)
    
    # 分批执行
    for batch_start in range(0, total, max_concurrent):
        batch_end = min(batch_start + max_concurrent, total)
        batch = tasks[batch_start:batch_end]
        
        # 创建Runnable任务
        runnables = {}
        for i, task in enumerate(batch):
            key = f"task_{i}" if task_names is None else task_names[batch_start + i]
            
            # 包装任务函数
            def make_wrapper(t: Callable[[], R]):
                def wrapper(_: Any = None) -> R:
                    return t()
                return wrapper
            
            runnables[key] = RunnableLambda(make_wrapper(task))
        
        # 并发执行当前批次
        parallel = RunnableParallel(**runnables)
        batch_results = parallel.invoke({})
        
        # 收集结果（保持顺序）
        for i in range(len(batch)):
            key = f"task_{i}" if task_names is None else task_names[batch_start + i]
            results.append(batch_results[key])
    
    return results


def parallel_execute_dict(
    tasks: Dict[str, Callable[[], R]],
    max_concurrent: int = 4,
) -> Dict[str, R]:
    """并发执行多个命名任务（字典形式）
    
    Args:
        tasks: 任务字典，key为任务名，value为任务函数
        max_concurrent: 最大并发数
    
    Returns:
        结果字典，key与输入对应
    
    Example:
        results = parallel_execute_dict({
            "task1": lambda: "result1",
            "task2": lambda: "result2",
        })
        # results = {"task1": "result1", "task2": "result2"}
    """
    if not tasks:
        return {}
    
    keys = list(tasks.keys())
    task_funcs = [tasks[k] for k in keys]
    
    results = parallel_execute(task_funcs, max_concurrent, task_names=keys)
    
    return {k: v for k, v in zip(keys, results)}
