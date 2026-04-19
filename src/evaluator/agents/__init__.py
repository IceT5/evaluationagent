"""Agent 定义

Agent分类:
- 入口Agent: IntentParserAgent - 解析用户意图
- 编排Agent: OrchestratorAgent, IntelligencePipeline - 规划工作流、动态决策
- 功能Agent: InputAgent, LoaderAgent, CICDAgent, ReviewerAgent, ReporterAgent, CompareAgent
- 智能Agent: StorageAgent, ReflectionAgent, RecommendationAgent
- 处理Agent: ListHandlerAgent, InfoHandlerAgent, DeleteHandlerAgent, HelpHandlerAgent
- 验证Agent: ErrorHandlerAgent, StateValidationAgent
- CICD子Agent: DataExtractionAgent, AnalysisPlanningAgent, LLMInvocationAgent等
"""
from evaluator.agents.base_agent import BaseAgent, AgentMeta
from evaluator.agents.input_agent import InputAgent
from evaluator.agents.loader_agent import LoaderAgent
from evaluator.agents.cicd_agent import CICDAgent
from evaluator.agents.reporter_agent import ReporterAgent
from evaluator.agents.reviewer_agent import ReviewerAgent
from evaluator.agents.report_fix_agent import ReportFixAgent, ReportFixPlanAgent, ReportFixApplyAgent
from evaluator.agents.compare_agent import CompareAgent
from evaluator.agents.intent_parser_agent import IntentParserAgent, Intent, ParsedIntent
from evaluator.agents.orchestrator_agent import OrchestratorAgent
from evaluator.agents.tool_selection_agent import ToolSelectionAgent
from evaluator.agents.storage_agent import StorageAgent
from evaluator.agents.reflection_agent import ReflectionAgent, ExecutionTurn, Reflection
from evaluator.agents.recommendation_agent import RecommendationAgent
from evaluator.agents.intelligence_pipeline import IntelligencePipeline
from evaluator.agents.error_handler_agent import ErrorHandlerAgent
from evaluator.agents.state_validation_agent import StateValidationAgent

from evaluator.agents.cicd import (
    DataExtractionAgent,
    AnalysisPlanningAgent,
    LLMInvocationAgent,
    ResultMergingAgent,
    QualityCheckAgent,
    RetryHandlingAgent,
    StageOrganizationAgent,
    ReportGenerationAgent,
    SummaryGenerationAgent,
    CICDOrchestrator,
)

from evaluator.agents.handlers import (
    ListHandlerAgent,
    InfoHandlerAgent,
    DeleteHandlerAgent,
    HelpHandlerAgent,
)

__all__ = [
    # Base
    "BaseAgent",
    "AgentMeta",
    # Core Agents
    "InputAgent",
    "LoaderAgent",
    "CICDAgent",
    "ReporterAgent",
    "ReviewerAgent",
    "ReportFixAgent",
    "ReportFixPlanAgent",
    "ReportFixApplyAgent",
    "CompareAgent",
    "IntentParserAgent",
    "Intent",
    "ParsedIntent",
    "OrchestratorAgent",
    "ToolSelectionAgent",
    "StorageAgent",
    "ReflectionAgent",
    "ExecutionTurn",
    "Reflection",
    "RecommendationAgent",
    "IntelligencePipeline",
    "ErrorHandlerAgent",
    "StateValidationAgent",
    # CICD 子 Agent
    "DataExtractionAgent",
    "AnalysisPlanningAgent",
    "LLMInvocationAgent",
    "ResultMergingAgent",
    "QualityCheckAgent",
    "RetryHandlingAgent",
    "StageOrganizationAgent",
    "ReportGenerationAgent",
    "SummaryGenerationAgent",
    "CICDOrchestrator",
    # Handler Agent
    "ListHandlerAgent",
    "InfoHandlerAgent",
    "DeleteHandlerAgent",
    "HelpHandlerAgent",
]
