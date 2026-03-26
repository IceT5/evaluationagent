"""分析策略规划 Agent - 决定分析策略"""
from pathlib import Path
from typing import Optional, List

from evaluator.skills import CIAnalyzer
from .state import CICDState
from evaluator.agents.base_agent import BaseAgent, AgentMeta

try:
    from evaluator.config import config
    HAS_CONFIG = True
except ImportError:
    HAS_CONFIG = False
    config = None

def _get_max_workflows_single() -> int:
    return config.max_workflows_single if config and HAS_CONFIG else 10

def _get_max_workflows_batch() -> int:
    return config.max_workflows_batch if config and HAS_CONFIG else 10


class AnalysisPlanningAgent(BaseAgent):
    """分析策略规划 Agent
    
    职责：根据工作流数量决定分析策略（single/batch/parallel/skip）
    输入：CICDState.ci_data, workflow_count
    输出：CICDState.strategy, prompts, prompt_strategy
    """
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="AnalysisPlanningAgent",
            description="决定分析策略（单次/批量/并发/跳过）",
            category="analysis",
            inputs=["workflow_count", "ci_data", "storage_dir"],
            outputs=["strategy", "prompts", "prompt_strategy"],
            dependencies=["DataExtractionAgent"],
        )
    
    def __init__(self):
        super().__init__()
        self.ci_analyzer = CIAnalyzer()
    
    def run(self, state: CICDState) -> CICDState:
        """决定分析策略"""
        workflow_count = state.get("workflow_count", 0)
        ci_data = state.get("ci_data", {})
        storage_dir = state.get("storage_dir")
        
        if workflow_count == 0:
            return {
                **state,
                "strategy": "skip",
                "prompts": [],
                "prompt_strategy": "none",
            }
        
        output_dir = Path(storage_dir) if storage_dir else Path(state.get("project_path", "."))
        
        max_single = _get_max_workflows_single()
        max_batch = _get_max_workflows_batch()
        
        if workflow_count <= max_single:
            strategy = "single"
            prompts_dir = None
            prompt_strategy = "single"
            print(f"  [Planning] 工作流数量 ≤ {max_single}，使用单次调用模式")
        else:
            strategy = "parallel"
            prompts_dir = output_dir / "prompts"
            prompt_strategy = "multi_round"
            print(f"  [Planning] 工作流数量 > {max_single}，使用多轮对话模式")
        
        if prompts_dir:
            prompts_dir.mkdir(parents=True, exist_ok=True)
            prompt_info = self.ci_analyzer.generate_split_prompts(
                ci_data,
                str(prompts_dir),
                max_per_batch=max_batch,
                use_multi_round=True
            )
            
            main_rounds = prompt_info.get("main_rounds", [])
            main_system_prompt = prompt_info.get("main_system_prompt", "")
            batch_files = prompt_info.get("batch_files", [])
            all_files = prompt_info.get("all_files", [])
            
            print(f"  [Planning] 生成了 {len(all_files)} 个文件 (main: {len(main_rounds)} rounds, batch: {len(batch_files)})")
            
            return {
                **state,
                "strategy": strategy,
                "prompts": all_files,
                "batch_files": batch_files,
                "main_rounds": main_rounds,
                "main_system_prompt": main_system_prompt,
                "prompt_strategy": prompt_strategy,
            }
        else:
            prompt_path = str(output_dir / "prompt.txt")
            self.ci_analyzer.generate_prompt(ci_data, prompt_path)
            prompt_files = [prompt_path] if Path(prompt_path).exists() else []
            
            return {
                **state,
                "strategy": strategy,
                "prompts": prompt_files,
                "batch_files": [],
                "main_rounds": [],
                "main_system_prompt": "",
                "prompt_strategy": prompt_strategy,
            }
