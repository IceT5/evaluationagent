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
    @traceable()
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行Agent逻辑
        
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
    
    @traceable()
    def safe_run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """安全执行 - 带中断检查、输入验证和异常捕获
        
        如果输入验证失败，返回带有错误信息的state。
        如果执行过程中发生异常，捕获并记录错误。
        支持通过 InterruptController 中断执行。
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
            import traceback
            errors = state.get("errors", [])
            error_msg = f"{self.name}: {type(e).__name__}: {str(e)}"
            errors.append(error_msg)
            print(f"[ERROR] {self.name} 执行失败: {error_msg}")
            traceback.print_exc()
            return {**state, "errors": errors}
