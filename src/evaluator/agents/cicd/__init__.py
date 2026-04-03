"""CI/CD Agent 子模块

包含以下Agent：
- DataExtractionAgent: 提取CI/CD配置数据
- AnalysisPlanningAgent: 决定分析策略（单次/并发）
- LLMInvocationAgent: 执行LLM调用
- ResultMergingAgent: 合并多个LLM响应
- QualityCheckAgent: 验证报告质量
- RetryHandlingAgent: 处理重试和补充模式
- StageOrganizationAgent: 根据架构图组织报告阶段
- ReportGenerationAgent: 生成最终报告
- SummaryGenerationAgent: 生成分析摘要
- CICDOrchestrator: CI/CD分析编排器
"""
from evaluator.agents.cicd.state import CICDState, to_cicd_state, from_cicd_state
from evaluator.agents.cicd.data_extraction_agent import DataExtractionAgent
from evaluator.agents.cicd.analysis_planning_agent import AnalysisPlanningAgent
from evaluator.agents.cicd.llm_invocation_agent import LLMInvocationAgent
from evaluator.agents.cicd.result_merging_agent import ResultMergingAgent
from evaluator.agents.cicd.quality_check_agent import QualityCheckAgent
from evaluator.agents.cicd.retry_handling_agent import RetryHandlingAgent
from evaluator.agents.cicd.stage_organization_agent import StageOrganizationAgent
from evaluator.agents.cicd.report_generation_agent import ReportGenerationAgent, SummaryGenerationAgent
from evaluator.agents.cicd.orchestrator import CICDOrchestrator

__all__ = [
    # 状态
    "CICDState",
    "to_cicd_state",
    "from_cicd_state",
    # 原有子Agent
    "DataExtractionAgent",
    "AnalysisPlanningAgent",
    "LLMInvocationAgent",
    "ResultMergingAgent",
    "QualityCheckAgent",
    # 新增子Agent
    "RetryHandlingAgent",
    "StageOrganizationAgent",
    "ReportGenerationAgent",
    "SummaryGenerationAgent",
    # 编排器
    "CICDOrchestrator",
]
