"""Agent 定义"""
from evaluator.agents.input_agent import InputAgent
from evaluator.agents.loader_agent import LoaderAgent
from evaluator.agents.cicd_agent import CICDAgent
from evaluator.agents.reporter_agent import ReporterAgent

__all__ = ["InputAgent", "LoaderAgent", "CICDAgent", "ReporterAgent"]