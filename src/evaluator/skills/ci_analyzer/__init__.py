"""CI/CD 分析 Skill

基于 ci_architecture 的能力，提供 CI/CD 架构分析功能。

工作流程（参考 SKILL.md）：
1. extract_data() - 提取 CI/CD 原始数据
2. generate_prompt() - 生成 LLM 分析 Prompt
3. generate_report() - 从 LLM 响应生成最终报告
"""
from evaluator.skills.ci_analyzer.ci_data_extractor import (
    CIDataExtractor,
    extract_to_json,
)
from evaluator.skills.ci_analyzer.ci_diagram_generator import (
    generate_architecture_diagram,
    generate_multi_round_prompts,
)

__all__ = [
    "CIDataExtractor",
    "extract_to_json",
    "generate_architecture_diagram",
    "generate_multi_round_prompts",
    "CIAnalyzer",
]


class CIAnalyzer:
    """
    CI/CD 分析能力
    
    封装 CI/CD 架构分析的完整流程。
    """
    
    def extract_data(
        self,
        project_path: str,
        output_file: str | None = None,
    ) -> dict:
        """
        提取项目的 CI/CD 数据
        
        Args:
            project_path: 项目路径
            output_file: 输出 JSON 文件路径（可选）
        
        Returns:
            提取的 CI/CD 数据 (dict)
        """
        print(f"\n正在提取 CI/CD 数据...")
        print(f"  项目路径: {project_path}")
        
        if output_file:
            json_str = extract_to_json(project_path, output_file)
            print(f"  输出文件: {output_file}")
        else:
            json_str = extract_to_json(project_path)
        
        import json
        data = json.loads(json_str)
        
        workflows_count = len(data.get("workflows", {}))
        actions_count = len(data.get("actions", []))
        print(f"  提取完成: {workflows_count} 个工作流, {actions_count} 个 Action")
        
        return data
    
    def generate_prompts(
        self,
        ci_data: dict | str,
        output_dir: str,
        max_per_batch: int = 10,
    ) -> dict:
        """
        生成 Prompt 文件（多轮对话模式）
        
        Args:
            ci_data: CI 数据
            output_dir: 输出目录
            max_per_batch: 每批次最大工作流数
        
        Returns:
            Dict 包含:
            - main_rounds: 多轮对话的 rounds 列表
            - main_system_prompt: 系统提示
            - batch_files: 批次 prompt 文件列表
            - all_files: 所有文件列表
            - prompt_strategy: "multi_round"
            - global_context: 全局上下文字符串
        """
        import json
        
        print(f"\n正在生成 Prompt...")
        
        if isinstance(ci_data, str):
            with open(ci_data, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
        else:
            raw_data = ci_data
        
        result = generate_multi_round_prompts(raw_data, output_dir, max_per_batch)
        total_files = len(result.get("all_files", []))
        print(f"  生成了 {total_files} 个文件 (多轮对话模式)")
        return result
    
    def generate_report(
        self,
        ci_data: dict | str,
        llm_response: str,
        output_file: str,
    ) -> str:
        """
        从 LLM 响应生成最终报告
        
        Args:
            ci_data: CI 数据 (dict 或 JSON 文件路径)
            llm_response: LLM 的响应内容
            output_file: 输出报告文件路径
        
        Returns:
            生成的报告内容
        """
        import json
        
        print(f"\n正在生成最终报告...")
        
        if isinstance(ci_data, str):
            with open(ci_data, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
        else:
            raw_data = ci_data
        
        report = generate_architecture_diagram(raw_data, llm_response, output_file)
        
        print(f"  报告已保存: {output_file}")
        
        return report