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
    generate_llm_prompt,
    generate_architecture_diagram,
    generate_split_prompts,
    generate_multi_round_prompts,
)

__all__ = [
    "CIDataExtractor",
    "extract_to_json",
    "generate_llm_prompt",
    "generate_architecture_diagram",
    "generate_split_prompts",
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
    
    def generate_prompt(
        self,
        ci_data: dict | str,
        output_file: str | None = None,
    ) -> str:
        """
        生成 LLM 分析 Prompt
        
        Args:
            ci_data: CI 数据 (dict 或 JSON 文件路径)
            output_file: 输出 prompt 文件路径（可选）
        
        Returns:
            生成的 prompt 内容
        """
        import json
        
        print(f"\n正在生成分析 Prompt...")
        
        # 支持传入文件路径或 dict
        if isinstance(ci_data, str):
            with open(ci_data, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
        else:
            raw_data = ci_data
        
        prompt = generate_llm_prompt(raw_data)
        
        if output_file:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(prompt)
            print(f"  Prompt 已保存: {output_file}")
        else:
            print(f"  Prompt 生成完成 ({len(prompt)} 字符)")
        
        return prompt
    
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
        
        # 支持传入文件路径或 dict
        if isinstance(ci_data, str):
            with open(ci_data, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
        else:
            raw_data = ci_data
        
        report = generate_architecture_diagram(raw_data, llm_response, output_file)
        
        print(f"  报告已保存: {output_file}")
        
        return report
    
    def check_workflow_count(self, ci_data: dict | str) -> int:
        """
        检查工作流数量，用于决定是否需要分割 Prompt
        
        Args:
            ci_data: CI 数据
        
        Returns:
            工作流数量
        """
        import json
        
        if isinstance(ci_data, str):
            with open(ci_data, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
        else:
            raw_data = ci_data
        
        return len(raw_data.get("workflows", {}))
    
    def generate_split_prompts(
        self,
        ci_data: dict | str,
        output_dir: str,
        max_per_batch: int = 10,
        use_multi_round: bool = True,
    ) -> dict:
        """
        为大型项目生成多个 Prompt 文件
        
        Args:
            ci_data: CI 数据
            output_dir: 输出目录
            max_per_batch: 每批次最大工作流数
            use_multi_round: 是否使用多轮对话模式（默认 True）
        
        Returns:
            Dict 包含:
            - main_rounds: 多轮对话的 rounds 列表（use_multi_round=True 时）
            - main_system_prompt: 系统提示（use_multi_round=True 时）
            - batch_files: 批次 prompt 文件列表
            - all_files: 所有文件列表
            - prompt_strategy: "multi_round" 或 "parallel"
            - global_context: 全局上下文字符串
        """
        import json
        
        print(f"\n正在生成分批 Prompt...")
        
        if isinstance(ci_data, str):
            with open(ci_data, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
        else:
            raw_data = ci_data
        
        if use_multi_round:
            result = generate_multi_round_prompts(raw_data, output_dir, max_per_batch)
            total_files = len(result.get("all_files", []))
            print(f"  生成了 {total_files} 个文件 (多轮对话模式)")
            return result
        else:
            files = generate_split_prompts(raw_data, output_dir, max_per_batch)
            print(f"  生成了 {len(files)} 个文件")
            return {
                "main_rounds": [],
                "main_system_prompt": "",
                "batch_files": files,
                "all_files": files,
                "prompt_strategy": "parallel",
                "global_context": "",
            }