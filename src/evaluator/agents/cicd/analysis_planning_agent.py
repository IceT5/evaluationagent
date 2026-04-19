"""分析策略规划 Agent - 决定分析策略"""
from pathlib import Path
from typing import Optional, List, Dict, Any

from evaluator.skills import CIAnalyzer
from evaluator.state import EvaluatorState
from evaluator.agents.base_agent import BaseAgent, AgentMeta

try:
    from evaluator.config import config
    HAS_CONFIG = True
except ImportError:
    HAS_CONFIG = False
    config = None


def build_default_report_contract() -> Dict[str, Any]:
    """冻结当前 CI/CD 报告的章节契约。"""
    return {
        "contract_version": "v1",
        "sections": [
            {"section_id": "overview", "title": "项目概述", "order": 10, "required": True, "owner": "multi_round", "source_type": "global_summary"},
            {"section_id": "architecture", "title": "CI/CD 整体架构图", "order": 20, "required": True, "owner": "multi_round", "source_type": "architecture_json"},
            {"section_id": "stage_details", "title": "各阶段详情", "order": 30, "required": True, "owner": "structured_remap", "source_type": "workflow_details"},
            {"section_id": "scripts", "title": "脚本目录索引", "order": 40, "required": True, "owner": "batch_script_analysis", "source_type": "script_analysis"},
            {"section_id": "findings", "title": "关键发现和建议", "order": 50, "required": True, "owner": "multi_round", "source_type": "summary"},
            {"section_id": "appendix", "title": "附录", "order": 60, "required": True, "owner": "batch_detail", "source_type": "appendix"},
        ],
        "required_markers": ["ARCHITECTURE_JSON", "ANALYSIS_SUMMARY"],
        "html_required_sections": ["overview", "findings", "appendix", "scripts"],
    }


class AnalysisPlanningAgent(BaseAgent):
    """分析策略规划 Agent
    
    职责：根据工作流数量和 prompt 大小决定分析策略
    输入：EvaluatorState.ci_data, workflow_count
    输出：EvaluatorState.strategy, prompts, prompt_strategy
    """
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="AnalysisPlanningAgent",
            description="决定分析策略（多轮对话模式）",
            category="analysis",
            inputs=["workflow_count", "ci_data", "storage_dir"],
            outputs=["strategy", "prompts", "prompt_strategy"],
            dependencies=["DataExtractionAgent"],
        )
    
    def __init__(self):
        super().__init__()
        self.ci_analyzer = CIAnalyzer()
    
    def run(self, state: dict) -> dict:
        """决定分析策略"""
        workflow_count = state.get("workflow_count", 0)
        ci_data = state.get("ci_data") or {}
        storage_dir = state.get("storage_dir")
        
        if workflow_count == 0:
            return {
                **state,
                "strategy": "skip",
                "prompts": [],
                "prompt_strategy": "none",
            }
        
        output_dir = Path(storage_dir) if storage_dir else Path(str(state.get("project_path", ".")))
        
        # 使用动态决策策略
        from evaluator.skills.ci_analyzer.ci_diagram_generator import decide_prompt_strategy
        
        if HAS_CONFIG and config:
            strategy_info = decide_prompt_strategy(ci_data, config)
        else:
            # 回退：使用默认值
            strategy_info = {
                "strategy": "multi_round",
                "round0_batch_count": 1,
                "batch_size": 10,
                "estimated_tokens": 0,
            }
        
        batch_size = strategy_info["batch_size"]
        estimated_tokens = strategy_info["estimated_tokens"]
        
        print(f"  [Planning] 使用多轮对话模式")
        print(f"  [Planning] 每批次 workflow 数: {batch_size}")
        print(f"  [Planning] 估算 token 数: {estimated_tokens}")
        
        prompts_dir = output_dir / "prompts"
        prompts_dir.mkdir(parents=True, exist_ok=True)
        
        prompt_info = self.ci_analyzer.generate_prompts(
            ci_data,
            str(prompts_dir),
            max_per_batch=batch_size,
        )
        
        main_rounds = prompt_info.get("main_rounds", [])
        main_system_prompt = prompt_info.get("main_system_prompt", "")
        batch_files = prompt_info.get("batch_files", [])
        batch_inputs = prompt_info.get("batch_inputs", [])
        all_files = prompt_info.get("all_files", [])
        
        print(f"  [Planning] 生成了 {len(all_files)} 个文件 (main: {len(main_rounds)} rounds, batch: {len(batch_files)})")
        
        return {
            **state,
            "strategy": "multi_round",
            "prompts": all_files,
            "batch_files": batch_files,
            "batch_inputs": batch_inputs,
            "main_rounds": main_rounds,
            "main_system_prompt": main_system_prompt,
            "prompt_strategy": "multi_round",
            "cicd_global_context": prompt_info.get("global_context", ""),
            "report_contract": build_default_report_contract(),
        }
