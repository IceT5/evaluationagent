"""CIC/D 子 Agent 测试"""
import pytest
from unittest.mock import MagicMock, patch


class TestCICDState:
    """测试 EvaluatorState（原CICDState已合并）"""
    
    def test_cicd_state_import(self):
        """测试 EvaluatorState 导入（CICDState已合并到EvaluatorState）"""
        from evaluator.state import EvaluatorState
        assert EvaluatorState is not None


class TestDataExtractionAgent:
    """测试 DataExtractionAgent"""
    
    def test_agent_import(self):
        """测试导入"""
        from evaluator.agents.cicd import DataExtractionAgent
        assert DataExtractionAgent is not None
    
    def test_agent_init(self):
        """测试初始化"""
        from evaluator.agents.cicd import DataExtractionAgent
        agent = DataExtractionAgent()
        assert agent is not None
        assert agent.ci_analyzer is not None
    
    def test_run_with_invalid_path(self):
        """测试无效路径"""
        from evaluator.agents.cicd import DataExtractionAgent
        agent = DataExtractionAgent()
        
        state = {"project_path": None}
        result = agent.run(state)
        
        assert "errors" in result
        assert len(result["errors"]) > 0


class TestAnalysisPlanningAgent:
    """测试 AnalysisPlanningAgent"""
    
    def test_agent_import(self):
        """测试导入"""
        from evaluator.agents.cicd import AnalysisPlanningAgent
        assert AnalysisPlanningAgent is not None
    
    def test_agent_init(self):
        """测试初始化"""
        from evaluator.agents.cicd import AnalysisPlanningAgent
        agent = AnalysisPlanningAgent()
        assert agent is not None
    
    def test_run_skip_mode(self):
        """测试跳过模式"""
        from evaluator.agents.cicd import AnalysisPlanningAgent
        agent = AnalysisPlanningAgent()
        
        state = {"workflow_count": 0, "ci_data": {}}
        result = agent.run(state)
        
        assert result["strategy"] == "skip"


class TestLLMInvocationAgent:
    """测试 LLMInvocationAgent"""
    
    def test_agent_import(self):
        """测试导入"""
        from evaluator.agents.cicd import LLMInvocationAgent
        assert LLMInvocationAgent is not None
    
    def test_agent_init_with_llm(self):
        """测试带 LLM 初始化"""
        from evaluator.agents.cicd import LLMInvocationAgent
        mock_llm = MagicMock()
        agent = LLMInvocationAgent(llm=mock_llm)
        assert agent.llm is mock_llm
    
    def test_agent_init_without_llm(self):
        """测试不带 LLM 初始化"""
        from evaluator.agents.cicd import LLMInvocationAgent
        agent = LLMInvocationAgent()
        assert agent.llm is None


class TestResultMergingAgent:
    """测试 ResultMergingAgent"""
    
    def test_agent_import(self):
        """测试导入"""
        from evaluator.agents.cicd import ResultMergingAgent
        assert ResultMergingAgent is not None
    
    def test_merge_single_response(self):
        """测试单个响应合并"""
        from evaluator.agents.cicd import ResultMergingAgent
        agent = ResultMergingAgent()
        
        responses = [
            {"success": True, "response": "Test response", "index": 0}
        ]
        
        result = agent.merge(responses, {}, "")
        assert result == "Test response"
    
    def test_merge_all_failed(self):
        """测试全部失败"""
        from evaluator.agents.cicd import ResultMergingAgent
        agent = ResultMergingAgent()
        
        responses = [
            {"success": False, "error": "Failed"},
        ]
        
        with pytest.raises(RuntimeError):
            agent.merge(responses, {}, "")


class TestQualityCheckAgent:
    """测试 QualityCheckAgent"""
    
    def test_agent_import(self):
        """测试导入"""
        from evaluator.agents.cicd import QualityCheckAgent
        assert QualityCheckAgent is not None
    
    def test_agent_init(self):
        """测试初始化"""
        from evaluator.agents.cicd import QualityCheckAgent
        agent = QualityCheckAgent()
        assert agent is not None


class TestCICDOrchestrator:
    """测试 CICDOrchestrator"""
    
    def test_orchestrator_import(self):
        """测试导入"""
        from evaluator.agents.cicd import CICDOrchestrator
        assert CICDOrchestrator is not None
    
    def test_orchestrator_init(self):
        """测试初始化"""
        from evaluator.agents.cicd import CICDOrchestrator
        orchestrator = CICDOrchestrator()
        assert orchestrator is not None
        assert orchestrator.data_extraction is not None
        assert orchestrator.planning is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
