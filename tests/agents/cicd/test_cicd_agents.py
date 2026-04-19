"""CIC/D 子 Agent 测试"""
import json
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

    def test_fix_trigger_layer_supplements_missing_trigger_types(self):
        from evaluator.agents.cicd import QualityCheckAgent

        agent = QualityCheckAgent()
        ci_data = {
            "workflows": {
                "osv-scanner.yml": {
                    "triggers": ["pull_request", "merge_group", "schedule", "push"]
                }
            }
        }
        architecture_data = {
            "layers": [
                {
                    "id": "layer-trigger",
                    "name": "触发入口",
                    "nodes": [
                        {"id": "trigger-push", "label": "push", "description": "代码推送触发"},
                        {"id": "trigger-pr", "label": "pull_request", "description": "PR事件触发"},
                    ],
                }
            ]
        }

        fixed = agent._fix_trigger_layer(architecture_data, ci_data)
        trigger_layer = fixed["layers"][0]
        labels = {node["label"] for node in trigger_layer["nodes"]}

        assert labels == {"push", "pull_request", "merge_group", "schedule"}

    def test_validate_architecture_accepts_legacy_yml_trigger_labels(self):
        from evaluator.agents.cicd import QualityCheckAgent

        agent = QualityCheckAgent()
        ci_data = {
            "workflows": {
                "osv-scanner.yml": {
                    "triggers": ["push", "merge_group"]
                }
            }
        }
        architecture_data = {
            "layers": [
                {
                    "id": "layer-trigger",
                    "name": "触发入口",
                    "nodes": [
                        {"id": "trigger-push", "label": "push.yml", "description": ""},
                        {"id": "trigger-merge-group", "label": "merge_group", "description": ""},
                    ],
                },
                {
                    "id": "layer-security",
                    "name": "安全扫描",
                    "nodes": [
                        {"id": "wf-osv-scanner", "label": "osv-scanner.yml", "description": "", "jobs": 2}
                    ],
                },
            ]
        }

        validation = agent._validate_architecture(ci_data, architecture_data)

        assert validation["is_complete"] is True
        assert validation["missing_trigger_types"] == []

    def test_run_persists_repaired_trigger_layer_to_architecture_json(self, tmp_path):
        from evaluator.agents.cicd import QualityCheckAgent

        agent = QualityCheckAgent()
        state = {
            "storage_dir": str(tmp_path),
            "project_path": str(tmp_path),
            "ci_data": {
                "workflows": {
                    "osv-scanner.yml": {
                        "triggers": ["pull_request", "merge_group", "schedule", "push"]
                    }
                }
            },
            "batch_input_context": {
                "context_status": "ready",
                "constraints": {
                    "allow_implicit_conversation_state": False,
                },
                "input_artifacts": {
                    "architecture_json": {
                        "layers": [
                            {
                                "id": "layer-trigger",
                                "name": "触发入口",
                                "nodes": [
                                    {"id": "trigger-push", "label": "push", "description": "代码推送触发"},
                                    {"id": "trigger-pr", "label": "pull_request", "description": "PR事件触发"},
                                ],
                            },
                            {
                                "id": "layer-security",
                                "name": "安全扫描",
                                "nodes": [
                                    {"id": "wf-osv-scanner", "label": "osv-scanner.yml", "description": "", "jobs": 2}
                                ],
                            },
                        ],
                        "connections": [],
                    }
                },
                "diagnostics": [],
            },
            "cicd_assembled_data": {
                "artifacts": {
                    "architecture_json": {
                        "layers": [
                            {
                                "id": "layer-trigger",
                                "name": "触发入口",
                                "nodes": [
                                    {"id": "trigger-push", "label": "push", "description": "代码推送触发"},
                                    {"id": "trigger-pr", "label": "pull_request", "description": "PR事件触发"},
                                ],
                            },
                            {
                                "id": "layer-security",
                                "name": "安全扫描",
                                "nodes": [
                                    {"id": "wf-osv-scanner", "label": "osv-scanner.yml", "description": "", "jobs": 2}
                                ],
                            },
                        ],
                        "connections": [],
                    }
                }
            },
            "report_contract": {"sections": []},
            "report_artifacts": {"sections": []},
            "organized_stage_details": {
                "stages": [
                    {
                        "workflows": [
                            {"workflow_id": "osv-scanner.yml"}
                        ]
                    }
                ]
            },
            "script_analysis_data": {},
        }

        result = agent.run(state)

        assert result["validation_result"]["valid"] is True

        persisted_path = tmp_path / "architecture.json"
        persisted = json.loads(persisted_path.read_text(encoding="utf-8"))
        persisted_labels = {node["label"] for node in persisted["layers"][0]["nodes"]}

        assert persisted_labels == {"push", "pull_request", "merge_group", "schedule"}


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
