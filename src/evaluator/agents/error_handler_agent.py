"""错误处理 Agent - 统一处理错误"""
from typing import Dict, Any, List, Literal
from evaluator.agents.base_agent import BaseAgent, AgentMeta


class ErrorHandlerAgent(BaseAgent):
    """错误处理 Agent
    
    统一处理错误，生成错误报告，支持错误恢复。
    """
    
    FATAL_PATTERNS = [
        "authentication failed",
        "permission denied",
        "invalid api key",
        "not found: project",
        "timeout: exceeded",
        "fatal",
        "critical",
    ]
    
    RECOVERABLE_PATTERNS = [
        "timeout",
        "connection",
        "network",
        "temporarily",
        "retry",
    ]
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="ErrorHandlerAgent",
            description="统一处理错误，生成错误报告，支持错误恢复",
            category="output",
            inputs=["errors"],
            outputs=["error_report", "error_recoverable"],
            dependencies=[],
        )
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        errors = state.get("errors", [])
        if not errors:
            return {**state, "error_recoverable": False}
        
        fatal_errors = [e for e in errors if self._is_fatal(e)]
        recoverable_errors = [e for e in errors if self._is_recoverable(e)]
        
        error_report = {
            "total": len(errors),
            "fatal_count": len(fatal_errors),
            "recoverable_count": len(recoverable_errors),
            "errors": errors,
            "fatal_errors": fatal_errors,
            "recoverable_errors": recoverable_errors,
            "summary": self._summarize(errors),
        }
        
        is_recoverable = len(fatal_errors) == 0 and len(recoverable_errors) > 0
        
        print(f"\n[ErrorHandler] 处理 {len(errors)} 个错误:")
        print(f"  - 致命错误: {len(fatal_errors)}")
        print(f"  - 可恢复错误: {len(recoverable_errors)}")
        
        if is_recoverable:
            print(f"  - 策略: 尝试恢复")
        elif fatal_errors:
            print(f"  - 策略: 终止流程")
        
        return {
            **state,
            "error_report": error_report,
            "error_recoverable": is_recoverable,
        }
    
    def _is_fatal(self, error: str) -> bool:
        """判断是否为致命错误"""
        error_lower = error.lower()
        return any(pattern in error_lower for pattern in self.FATAL_PATTERNS)
    
    def _is_recoverable(self, error: str) -> bool:
        """判断是否为可恢复错误"""
        error_lower = error.lower()
        return any(pattern in error_lower for pattern in self.RECOVERABLE_PATTERNS)
    
    def _summarize(self, errors: List[str]) -> str:
        if not errors:
            return "无错误"
        
        error_types = {}
        for err in errors:
            err_lower = err.lower()
            if "timeout" in err_lower:
                error_types["超时"] = error_types.get("超时", 0) + 1
            elif "llm" in err_lower:
                error_types["LLM"] = error_types.get("LLM", 0) + 1
            elif "not found" in err_lower or "不存在" in err_lower:
                error_types["未找到"] = error_types.get("未找到", 0) + 1
            else:
                error_types["其他"] = error_types.get("其他", 0) + 1
        
        parts = [f"{k}: {v}个" for k, v in error_types.items()]
        return f"共 {len(errors)} 个错误 ({', '.join(parts)})"
