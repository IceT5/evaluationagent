"""反思 Agent - 从执行历史中学习"""
import json
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime

try:
    from evaluator.llm import LLMClient
    HAS_LLM = True
except ImportError:
    HAS_LLM = False
    LLMClient = None

from evaluator.agents.base_agent import BaseAgent, AgentMeta


@dataclass
class ExecutionTurn:
    """单次执行记录"""
    timestamp: str
    intent: str
    user_input: str
    result_status: str
    duration_seconds: float
    errors: List[str] = field(default_factory=list)
    workflow_count: int = 0
    steps_completed: List[str] = field(default_factory=list)


@dataclass
class Reflection:
    """反思结果"""
    total_executions: int
    success_rate: float
    avg_duration: float
    common_errors: List[str]
    bottlenecks: List[str]
    suggestions: List[str]
    insights: List[str]
    timestamp: str = field(default_factory=datetime.now().isoformat)


class ReflectionAgent(BaseAgent):
    """反思 Agent
    
    职责：
    1. 记录执行历史
    2. 分析执行模式
    3. 生成改进建议
    4. 提供洞察
    
    作为智能Agent，在分析完成后异步执行。
    """
    
    def __init__(
        self,
        llm: Optional["LLMClient"] = None,
        max_history: int = 100,
    ):
        super().__init__()
        self.llm = llm
        self.max_history = max_history
        self.history: List[ExecutionTurn] = []
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="ReflectionAgent",
            description="记录执行历史、分析性能瓶颈",
            category="intelligence",
            inputs=["intent", "cicd_analysis", "errors", "current_step"],
            outputs=["reflection_result"],
            dependencies=["RecommendationAgent"],
        )
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行反思分析
        
        记录本次执行并分析历史模式。
        """
        print(f"  [ReflectionAgent] 执行反思分析...")
        
        intent = state.get("intent", "analyze")
        errors = state.get("errors", [])
        workflow_count = state.get("workflow_count", 0)
        
        duration = state.get("duration_seconds", 0)
        result_status = "success" if not errors else "failed"
        
        self.record(
            intent=intent,
            user_input=state.get("user_input", ""),
            result_status=result_status,
            duration_seconds=duration,
            errors=errors,
            workflow_count=workflow_count,
            steps_completed=state.get("completed_steps", []),
        )
        
        reflection = self.reflect()
        
        if self.llm:
            try:
                reflection = self.reflect_with_llm()
            except Exception as e:
                print(f"  [ReflectionAgent] LLM反思失败: {e}")
        
        return {
            **state,
            "reflection_result": {
                "success_rate": reflection.success_rate,
                "avg_duration": reflection.avg_duration,
                "common_errors": reflection.common_errors,
                "bottlenecks": reflection.bottlenecks,
                "suggestions": reflection.suggestions,
                "insights": reflection.insights,
                "total_executions": reflection.total_executions,
            },
        }
    
    def record(
        self,
        intent: str,
        user_input: str,
        result_status: str,
        duration_seconds: float,
        errors: Optional[List[str]] = None,
        workflow_count: int = 0,
        steps_completed: Optional[List[str]] = None,
    ) -> None:
        """记录一次执行
        
        Args:
            intent: 执行意图
            user_input: 用户输入
            result_status: 结果状态 (success/failed/partial)
            duration_seconds: 执行耗时
            errors: 错误列表
            workflow_count: 工作流数量
            steps_completed: 完成的步骤
        """
        turn = ExecutionTurn(
            timestamp=datetime.now().isoformat(),
            intent=intent,
            user_input=user_input,
            result_status=result_status,
            duration_seconds=duration_seconds,
            errors=errors or [],
            workflow_count=workflow_count,
            steps_completed=steps_completed or [],
        )
        
        self.history.append(turn)
        
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
    
    def reflect(self) -> Reflection:
        """执行反思分析
        
        Returns:
            反思结果
        """
        if not self.history:
            return Reflection(
                total_executions=0,
                success_rate=0.0,
                avg_duration=0.0,
                common_errors=[],
                bottlenecks=[],
                suggestions=[],
                insights=["暂无执行历史"],
            )
        
        total = len(self.history)
        successes = sum(1 for t in self.history if t.result_status == "success")
        success_rate = successes / total
        
        durations = [t.duration_seconds for t in self.history]
        avg_duration = sum(durations) / len(durations)
        
        error_counts: Dict[str, int] = {}
        for turn in self.history:
            for error in turn.errors:
                error_counts[error] = error_counts.get(error, 0) + 1
        
        common_errors = sorted(error_counts.items(), key=lambda x: x[1], reverse=True)
        common_errors = [e[0] for e in common_errors[:5]]
        
        slow_steps = self._analyze_bottlenecks()
        
        suggestions = self._generate_suggestions()
        insights = self._generate_insights()
        
        return Reflection(
            total_executions=total,
            success_rate=success_rate,
            avg_duration=avg_duration,
            common_errors=common_errors,
            bottlenecks=slow_steps,
            suggestions=suggestions,
            insights=insights,
        )
    
    def _analyze_bottlenecks(self) -> List[str]:
        """分析性能瓶颈"""
        bottlenecks = []
        
        workflow_counts = [t.workflow_count for t in self.history if t.workflow_count > 0]
        if workflow_counts:
            avg_workflows = sum(workflow_counts) / len(workflow_counts)
            if avg_workflows > 20:
                bottlenecks.append(f"大型项目平均工作流数: {avg_workflows:.0f}，建议启用并行处理")
        
        durations = [t.duration_seconds for t in self.history]
        if durations:
            max_duration = max(durations)
            if max_duration > 300:
                bottlenecks.append(f"最长执行时间: {max_duration:.0f}s，需优化处理效率")
        
        total = len(self.history)
        failed_count = sum(1 for t in self.history if t.result_status == "failed")
        if failed_count > total * 0.2:
            bottlenecks.append(f"失败率较高 ({failed_count}/{total})，需检查错误处理")
        
        return bottlenecks[:3]
    
    def _generate_suggestions(self) -> List[str]:
        """生成改进建议"""
        suggestions = []
        
        if not self.history:
            return suggestions
        
        total = len(self.history)
        errors = [e for t in self.history for e in t.errors]
        
        if any("timeout" in e.lower() for e in errors):
            suggestions.append("考虑增加 LLM 调用超时时间")
        
        if any("memory" in e.lower() for e in errors):
            suggestions.append("考虑分批处理大型工作流，减少内存占用")
        
        if any("llm" in e.lower() for e in errors):
            suggestions.append("检查 LLM API 可用性和配置")
        
        workflow_counts = [t.workflow_count for t in self.history if t.workflow_count > 0]
        if workflow_counts and sum(workflow_counts) / len(workflow_counts) > 30:
            suggestions.append("对于超大型项目（30+ 工作流），建议启用分割并行模式")
        
        return suggestions[:5]
    
    def _generate_insights(self) -> List[str]:
        """生成洞察"""
        insights = []
        
        if not self.history:
            return insights
        
        success_rate = sum(1 for t in self.history if t.result_status == "success") / len(self.history)
        if success_rate > 0.9:
            insights.append("系统运行稳定，成功率 > 90%")
        
        avg_duration = sum(t.duration_seconds for t in self.history) / len(self.history)
        if avg_duration < 60:
            insights.append("平均执行速度快 (< 1分钟)")
        elif avg_duration > 180:
            insights.append("平均执行时间较长 (> 3分钟)，可能需要优化")
        
        intents = [t.intent for t in self.history]
        most_common = max(set(intents), key=intents.count) if intents else None
        if most_common:
            insights.append(f"最常用的命令是: {most_common}")
        
        return insights[:5]
    
    def reflect_with_llm(self) -> Reflection:
        """使用 LLM 进行深度反思
        
        Returns:
            反思结果
        """
        if not self.llm or not self.history:
            return self.reflect()
        
        history_json = json.dumps([asdict(t) for t in self.history[-20:]], ensure_ascii=False, indent=2)
        
        prompt = f"""请分析以下执行历史，生成反思报告：

执行历史：
{history_json}

请分析：
1. 成功率统计
2. 常见错误模式
3. 性能瓶颈
4. 改进建议
5. 有价值的洞察

输出 JSON 格式：
{{
  "success_rate": 0.0-1.0,
  "avg_duration": 秒数,
  "common_errors": ["错误1", "错误2"],
  "bottlenecks": ["瓶颈1", "瓶颈2"],
  "suggestions": ["建议1", "建议2"],
  "insights": ["洞察1", "洞察2"]
}}

只输出 JSON。"""
        
        try:
            response = self.llm.chat(prompt)
            data = json.loads(response)
            
            return Reflection(
                total_executions=len(self.history),
                success_rate=data.get("success_rate", 0.0),
                avg_duration=data.get("avg_duration", 0.0),
                common_errors=data.get("common_errors", []),
                bottlenecks=data.get("bottlenecks", []),
                suggestions=data.get("suggestions", []),
                insights=data.get("insights", []),
            )
        except:
            return self.reflect()
    
    def get_recent_errors(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的错误
        
        Args:
            limit: 返回数量
        
        Returns:
            错误列表
        """
        errors = []
        for turn in reversed(self.history):
            if turn.errors:
                errors.append({
                    "timestamp": turn.timestamp,
                    "intent": turn.intent,
                    "errors": turn.errors,
                })
                if len(errors) >= limit:
                    break
        return errors
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """获取性能统计
        
        Returns:
            性能统计信息
        """
        if not self.history:
            return {"total": 0, "avg_duration": 0}
        
        durations = [t.duration_seconds for t in self.history]
        
        return {
            "total": len(self.history),
            "avg_duration": sum(durations) / len(durations),
            "min_duration": min(durations),
            "max_duration": max(durations),
            "success_count": sum(1 for t in self.history if t.result_status == "success"),
            "failed_count": sum(1 for t in self.history if t.result_status == "failed"),
        }
    
    def clear_history(self) -> None:
        """清空历史记录"""
        self.history.clear()
