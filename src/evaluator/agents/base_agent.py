"""Agent基类定义 - 所有Agent必须继承

设计原则:
1. 单一职责: 每个Agent只做一件事
2. 状态驱动: 输入输出都通过state
3. 无副作用: 不修改全局状态，不直接I/O
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field
from langsmith import traceable

try:
    from langgraph.errors import GraphInterrupt as _GraphInterrupt
except ImportError:
    _GraphInterrupt = None


def _get_interrupt_controller():
    """延迟导入中断控制器，避免循环依赖"""
    try:
        from evaluator.core.interrupt import interrupt_controller, InterruptException
        return interrupt_controller, InterruptException
    except ImportError:
        return None, Exception


def validate_state(required_fields: List[str]) -> Callable:
    """状态验证装饰器
    
    在 Agent run 方法执行前验证必需字段。
    
    Args:
        required_fields: 必需的字段列表
    
    Example:
        @validate_state(["project_path", "storage_dir"])
        def run(self, state):
            ...
    """
    def decorator(func: Callable) -> Callable:
        def wrapper(self, state: Dict[str, Any]) -> Dict[str, Any]:
            missing = [f for f in required_fields if not state.get(f)]
            if missing:
                print(f"[WARN] {self.name}: 缺失字段 {missing}，但继续执行")
            return func(self, state)
        return wrapper
    return decorator


@dataclass
class AgentMeta:
    """Agent元信息"""
    name: str
    description: str
    category: str  # entry/orchestration/analysis/output/intelligence
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)


class BaseAgent(ABC):
    """Agent基类 - 所有Agent必须继承
    
    使用方式:
        class MyAgent(BaseAgent):
            @classmethod
            def describe(cls) -> AgentMeta:
                return AgentMeta(
                    name="MyAgent",
                    description="我的Agent",
                    category="analysis",
                    inputs=["input_field"],
                    outputs=["output_field"],
                )
            
            def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
                # 读取输入
                value = state["input_field"]
                # 处理
                result = self._process(value)
                # 返回更新 (必须包含所有原字段)
                return {**state, "output_field": result}
    """
    
    @classmethod
    @abstractmethod
    def describe(cls) -> AgentMeta:
        """返回Agent元信息
        
        用于:
        - 自动生成文档
        - 运行时验证
        - 依赖检查
        """
        pass
    
    @abstractmethod
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行Agent逻辑 - 内部方法，不独立trace
        
        通过 safe_run() 调用以获得完整的trace支持。
        
        Args:
            state: 当前状态 (EvaluatorState的子集)
        
        Returns:
            更新后的状态 (必须是state的超集)
        
        约束:
            1. 不能删除state中的字段
            2. 不能修改其他Agent的输出 (除非明确需要)
            3. 必须返回Dict，不能返回其他类型
            4. 使用 {**state, "new": value} 模式更新
        
        Example:
            def run(self, state):
                # 读取输入
                project_path = state["project_path"]
                
                # 执行逻辑
                result = self._analyze(project_path)
                
                # 返回更新 (包含所有原字段)
                return {**state, "analysis_result": result}
        """
        pass
    
    @property
    def name(self) -> str:
        """Agent名称"""
        return self.describe().name
    
    @property
    def description(self) -> str:
        """Agent描述"""
        return self.describe().description
    
    def validate_input(self, state: Dict[str, Any]) -> tuple[bool, List[str]]:
        """验证输入状态
        
        Returns:
            (是否有效, 缺失字段列表)
        """
        meta = self.describe()
        missing = [f for f in meta.inputs if f not in state]
        return len(missing) == 0, missing
    
    def validate_output(self, state: Dict[str, Any]) -> tuple[bool, List[str]]:
        """验证输出状态"""
        meta = self.describe()
        missing = [f for f in meta.outputs if f not in state]
        return len(missing) == 0, missing
    
    def safe_run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """安全执行 - 统一trace入口
        
        提供：
        - LangSmith trace支持（带扩展版metadata）
        - 输入验证
        - 错误处理
        - 中断支持
        """
        import os
        from evaluator.llm.tracing import traceable
        from functools import wraps
        
        # 收集扩展版metadata
        metadata = self._collect_metadata(state)
        
        # 创建带trace的执行函数
        @traceable(
            name=self.describe().name,
            run_type="chain",
            tags=["agent", self.describe().category],
            metadata=metadata,
        )
        @wraps(self._safe_run_impl)
        def _run_with_trace(inner_state):
            return self._safe_run_impl(inner_state)
        
        return _run_with_trace(state)
    
    def _collect_metadata(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """收集metadata - 扩展版（19个字段）
        
        包含：
        - 基础信息：agent_name, category, project信息
        - 执行上下文：intent, current_step, completed_steps
        - CI/CD信息：workflow_count, actions_count, strategy
        - 重试信息：retry_mode, retry_count, retry_issues
        - 错误和警告：errors, warnings
        - 存储信息：storage_dir, storage_version
        """
        import os
        
        metadata = {
            # === 基础信息 ===
            "agent_name": self.describe().name,
            "agent_category": self.describe().category,
            "project_path": state.get("project_path"),
            "project_name": state.get("project_name"),
            "project_url": state.get("project_url"),
            "display_name": state.get("display_name"),
            
            # === 执行上下文 ===
            "intent": state.get("intent"),
            "current_step": state.get("current_step"),
            "completed_steps_count": len(state.get("completed_steps", [])),
            
            # === CI/CD信息 ===
            "workflow_count": state.get("workflow_count", 0),
            "actions_count": state.get("actions_count", 0),
            "strategy": state.get("strategy"),
            
            # === 重试信息 ===
            "retry_mode": state.get("retry_mode"),
            "retry_count": state.get("retry_count", 0),
            "retry_issues_count": len(state.get("retry_issues", [])),
            
            # === 错误和警告 ===
            "has_errors": bool(state.get("errors")),
            "error_count": len(state.get("errors", [])),
            "has_warnings": bool(state.get("warnings")),
            "warning_count": len(state.get("warnings", [])),
            
            # === 存储信息 ===
            "storage_dir": state.get("storage_dir"),
            "has_storage_version": bool(state.get("storage_version_id")),
        }
        
        # 调试模式 - 详细metadata
        if os.getenv("EVAL_TRACE_DEBUG") == "true":
            metadata.update({
                "inputs": self.describe().inputs,
                "outputs": self.describe().outputs,
                "dependencies": self.describe().dependencies,
                "state_keys": list(state.keys()),
            })
        
        return metadata
    
    def _safe_run_impl(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """safe_run的实际实现（无装饰器）
        
        提供：
        - 中断检查
        - 输入验证
        - 错误处理
        """
        interrupt_controller, InterruptException = _get_interrupt_controller()
        
        if interrupt_controller:
            try:
                interrupt_controller.set_current_node(self.name)
            except Exception:
                pass
        
        if interrupt_controller:
            try:
                interrupt_controller.check()
            except InterruptException:
                raise
        
        valid, missing = self.validate_input(state)
        if not valid:
            errors = state.get("errors", [])
            errors.append(f"{self.name}: 缺失输入字段 {missing}")
            return {**state, "errors": errors}
        
        try:
            result = self.run(state)
            if interrupt_controller:
                try:
                    interrupt_controller.mark_node_completed(self.name)
                except Exception:
                    pass
            return result
        except InterruptException:
            raise
        except Exception as e:
            if _GraphInterrupt is not None and isinstance(e, _GraphInterrupt):
                raise
            import traceback
            errors = state.get("errors", [])
            error_msg = f"{self.name}: {type(e).__name__}: {str(e)}"
            errors.append(error_msg)
            print(f"[ERROR] {self.name} 执行失败: {error_msg}")
            traceback.print_exc()
            return {**state, "errors": errors}
