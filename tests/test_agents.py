"""Agent 模块导入测试"""
import pytest


class TestAgentImports:
    """测试所有 Agent 的导入"""
    
    def test_core_agents_import(self):
        """测试核心 Agent 导入"""
        from evaluator.agents import (
            InputAgent,
            LoaderAgent,
            CICDAgent,
            ReviewerAgent,
            ReporterAgent,
            CompareAgent,
            IntentParserAgent,
        )
        assert InputAgent is not None
        assert LoaderAgent is not None
        assert CICDAgent is not None
    
    def test_orchestrator_agents_import(self):
        """测试编排 Agent 导入"""
        from evaluator.agents import (
            OrchestratorAgent,
            # ToolSelectionAgent（未启用功能，保留用于未来扩展）
            ToolSelectionAgent,
        )
        assert OrchestratorAgent is not None
        # ToolSelectionAgent（未启用，保留测试确保代码可用性）
        assert ToolSelectionAgent is not None
    
    def test_intelligent_agents_import(self):
        """测试智能 Agent 导入"""
        from evaluator.agents import (
            StorageAgent,
            ReflectionAgent,
            Reflection,
            ExecutionTurn,
            RecommendationAgent,
        )
        assert StorageAgent is not None
        assert ReflectionAgent is not None
        assert RecommendationAgent is not None
    
    def test_cicd_sub_agents_import(self):
        """测试 CI/CD 子 Agent 导入"""
        from evaluator.agents.cicd import (
            CICDState,
            DataExtractionAgent,
            AnalysisPlanningAgent,
            LLMInvocationAgent,
            ResultMergingAgent,
            QualityCheckAgent,
            CICDOrchestrator,
        )
        assert CICDState is not None
        assert DataExtractionAgent is not None
        assert AnalysisPlanningAgent is not None
        assert CICDOrchestrator is not None


class TestCoreImports:
    """测试 Core 模块导入"""
    
    def test_core_functions_import(self):
        """测试 Core 函数导入"""
        from evaluator.core import (
            analyze_project,
            compare_projects,
            list_projects,
            get_project,
            delete_project,
        )
        assert analyze_project is not None
        assert compare_projects is not None
    
    def test_graphs_import(self):
        """测试 Graph 模块导入"""
        from evaluator.core.graphs import create_main_graph
        assert create_main_graph is not None
    
    def test_routes_import(self):
        """测试路由函数导入"""
        from evaluator.core.routes import (
            route_after_input,
            route_after_loader,
            route_after_cicd,
            route_after_review,
            should_skip_review,
            evaluate_quality,
        )
        assert route_after_input is not None
        assert route_after_review is not None


class TestCLIImports:
    """测试 CLI 模块导入"""
    
    def test_app_import(self):
        """测试 CLI App 导入"""
        from evaluator.cli.app import CommandHandler
        assert CommandHandler is not None


class TestGraphImports:
    """测试 Graph 模块导入"""
    
    def test_create_main_graph_import(self):
        """测试 main_graph 导入"""
        from evaluator.core.graphs import create_main_graph
        assert create_main_graph is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
