"""Agent 定义"""
from evaluator.agents.input_agent import InputAgent
from evaluator.agents.loader_agent import LoaderAgent
from evaluator.agents.cicd_agent import CICDAgent
from evaluator.agents.reporter_agent import ReporterAgent
from evaluator.agents.reviewer_agent import ReviewerAgent
from evaluator.agents.compare_agent import CompareAgent

__all__ = ["InputAgent", "LoaderAgent", "CICDAgent", "ReporterAgent", "ReviewerAgent", "CompareAgent"]