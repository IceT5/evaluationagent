"""顶层编排 Agent - 动态规划执行流程"""
import json
from typing import Optional, List, Dict, Any, Literal

try:
    from evaluator.llm import LLMClient
    HAS_LLM = True
except ImportError:
    HAS_LLM = False
    LLMClient = None

from evaluator.agents.base_agent import BaseAgent, AgentMeta

try:
    from evaluator.config import config
    HAS_CONFIG = True
except ImportError:
    HAS_CONFIG = False
    config = None


class OrchestratorAgent(BaseAgent):
    """顶层编排 Agent - 作为 LangGraph 的智能决策节点
    
    职责：
    1. 根据意图和状态规划执行步骤
    2. 决定是否需要重试
    3. 动态选择 Agent 执行
    4. 返回决策结果供 LangGraph 路由使用
    
    架构原则:
    - 工具选择委托给ToolSelectionAgent
    - 使用LangGraph进行状态驱动编排
    """
    
    AGENTS = {
        "input": "InputAgent",
        "loader": "LoaderAgent",
        "cicd": "CICDAgent",
        "reviewer": "ReviewerAgent",
        "reporter": "ReporterAgent",
        "compare": "CompareAgent",
    }
    
    WORKFLOW_TEMPLATES = {
        "analyze": ["input", "loader", "cicd", "reviewer", "reporter"],
        "analyze_skip_review": ["input", "loader", "cicd", "reporter"],
        "compare": ["compare"],
        "list": ["list_handler"],
        "info": ["info_handler"],
        "delete": ["delete_handler"],
        "help": ["help_handler"],
        "unknown": [],
    }
    
    def __init__(self, llm: Optional["LLMClient"] = None):
        super().__init__()
        self.llm = llm
        self.tool_selector = None
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="OrchestratorAgent",
            description="规划工作流、动态决策",
            category="orchestration",
            inputs=["intent", "current_step", "completed_steps", "errors"],
            outputs=["orchestrator_decision", "current_step"],
            dependencies=["IntentParserAgent"],
        )
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行编排决策 - 供 LangGraph 节点调用
        
        Args:
            state: 当前状态
        
        Returns:
            更新后的状态，包含 orchestrator_decision 决策结果
        """
        intent = state.get("intent", "analyze")
        current_step = state.get("current_step", "")
        
        workflow = self._get_workflow(intent, state)
        
        next_step = self._decide_next_step(current_step, workflow, state)
        
        should_retry, retry_agent = self._check_should_retry(current_step, state)
        
        if should_retry:
            next_step = retry_agent
            print(f"  [Orchestrator] 决定重试: {retry_agent}")
        else:
            print(f"  [Orchestrator] 决策: 下一步={next_step}")
        
        reasoning = self._get_reasoning(current_step, next_step, should_retry, state)
        
        return {
            **state,
            "current_step": next_step,
            "orchestrator_decision": {
                "next_step": next_step,
                "should_retry": should_retry,
                "retry_agent": retry_agent,
                "reasoning": reasoning,
                "workflow": workflow,
            },
        }
    
    def _get_workflow(self, intent: str, state: Dict[str, Any]) -> List[str]:
        """获取工作流"""
        workflow = self.WORKFLOW_TEMPLATES.get(intent, [])
        
        if self._should_skip_review(state):
            workflow = [step for step in workflow if step != "reviewer"]
        
        return workflow
    
    def _decide_next_step(
        self,
        current_step: str,
        workflow: List[str],
        state: Dict[str, Any]
    ) -> str:
        """决定下一步"""
        if not workflow:
            return "end"
        
        if not current_step:
            return workflow[0]
        
        if current_step == "end":
            return "end"
        
        completed_steps = state.get("completed_steps", [])
        
        for step in workflow:
            if step not in completed_steps and step != current_step:
                return step
        
        return "end"
    
    def _check_should_retry(
        self,
        current_step: str,
        state: Dict[str, Any]
    ) -> tuple[bool, str]:
        """检查是否需要重试"""
        if not current_step:
            return False, ""
        
        errors = state.get("errors", [])
        if not errors:
            return False, ""
        
        max_retries = config.max_retries if config else 3
        retry_count_key = f"{current_step}_retry_count"
        retry_count = state.get(retry_count_key, 0)
        
        if retry_count >= max_retries:
            return False, ""
        
        last_error = errors[-1] if errors else ""
        
        if "llm" in last_error.lower() or "timeout" in last_error.lower():
            return True, current_step
        
        if "validation" in last_error.lower():
            return True, "cicd"
        
        review_result = state.get("review_result", {})
        if review_result.get("status") in ["critical", "incomplete"]:
            return True, "cicd"
        
        return False, ""
    
    def _get_reasoning(
        self,
        current_step: str,
        next_step: str,
        should_retry: bool,
        state: Dict[str, Any]
    ) -> str:
        """获取决策理由"""
        if should_retry:
            return f"需要重试 {next_step}，因为之前的执行存在问题"
        
        if not current_step:
            return f"开始执行工作流，第一步: {next_step}"
        
        if next_step == "end":
            return "工作流已完成"
        
        return f"从 {current_step} 执行完毕，下一步: {next_step}"
    
    def plan(self, intent: str, state: Dict[str, Any]) -> List[str]:
        """规划执行步骤
        
        Args:
            intent: 用户意图
            state: 当前状态
        
        Returns:
            Agent 执行顺序列表
        """
        workflow = self.WORKFLOW_TEMPLATES.get(intent, [])
        
        if not workflow:
            return []
        
        if self._should_skip_review(state):
            workflow = [step for step in workflow if step != "reviewer"]
        
        return workflow
    
    def should_retry(
        self,
        agent_name: str,
        state: Dict[str, Any]
    ) -> tuple[bool, str, int]:
        """决定是否重试
        
        Args:
            agent_name: Agent 名称
            state: 当前状态
        
        Returns:
            (是否重试, 重试的 Agent 名称, 最大重试次数)
        """
        max_retries = config.max_retries if config else 3
        retry_count_key = f"{agent_name}_retry_count"
        retry_count = state.get(retry_count_key, 0)
        
        if retry_count >= max_retries:
            return False, "", max_retries
        
        errors = state.get("errors", [])
        if not errors:
            return False, "", max_retries
        
        last_error = errors[-1] if errors else ""
        
        if "llm" in last_error.lower() or "timeout" in last_error.lower():
            return True, agent_name, max_retries
        
        if "validation" in last_error.lower():
            return True, "cicd", max_retries
        
        return False, "", max_retries
    
    def select_tools(
        self,
        task: str,
        context: Dict[str, Any]
    ) -> List[str]:
        """选择合适的工具
        
        委托给ToolSelectionAgent执行。
        
        Args:
            task: 任务描述
            context: 上下文信息
        
        Returns:
            工具名称列表
        """
        if self.tool_selector is None:
            from evaluator.agents.tool_selection_agent import ToolSelectionAgent
            self.tool_selector = ToolSelectionAgent(llm=self.llm)
        
        return self.tool_selector.select_tools(task, context)
    
    def _should_skip_review(self, state: Dict[str, Any]) -> bool:
        """判断是否应该跳过 review"""
        skip_review = state.get("skip_review", False)
        if skip_review:
            return True
        
        workflow_count = (state.get("cicd_analysis") or {}).get("workflows_count", 0)
        if workflow_count <= 5:
            return True
        
        return False
    
    def get_next_step(
        self,
        current_step: str,
        completed_steps: List[str],
        state: Dict[str, Any]
    ) -> Optional[str]:
        """获取下一步骤
        
        Args:
            current_step: 当前步骤
            completed_steps: 已完成的步骤
            state: 当前状态
        
        Returns:
            下一个步骤，或 None 表示结束
        """
        intent = state.get("intent", "analyze")
        workflow = self.plan(intent, state)
        
        for step in workflow:
            if step not in completed_steps:
                return step
        
        return None
    
    def evaluate_quality(
        self,
        result: Dict[str, Any],
        threshold: float = 0.7
    ) -> tuple[bool, float, str]:
        """评估结果质量
        
        Args:
            result: 执行结果
            threshold: 质量阈值
        
        Returns:
            (是否达标, 质量分数, 评估说明)
        """
        if not result:
            return False, 0.0, "结果为空"
        
        errors = result.get("errors", [])
        if errors:
            return False, 0.3, f"存在 {len(errors)} 个错误"
        
        status = result.get("status") or result.get("cicd_analysis", {}).get("status")
        
        if status == "success":
            return True, 0.95, "执行成功"
        elif status == "passed":
            return True, 0.9, "验证通过"
        elif status == "no_cicd":
            return True, 0.5, "无 CI/CD 数据"
        else:
            return False, 0.4, f"状态异常: {status}"
