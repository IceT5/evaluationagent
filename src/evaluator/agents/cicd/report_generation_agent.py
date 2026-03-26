"""报告生成Agent - 生成Markdown和HTML报告"""
from pathlib import Path
from typing import Optional, Dict, Any

from .state import CICDState
from evaluator.agents.base_agent import BaseAgent, AgentMeta


class ReportGenerationAgent(BaseAgent):
    """报告生成Agent
    
    负责生成最终的Markdown和HTML报告。
    
    输入（CICDState）:
    - ci_data_path: CI数据路径
    - merged_response: LLM响应内容
    - storage_dir: 存储目录
    
    输出（CICDState）:
    - report_md: Markdown报告路径
    - report_html: HTML报告路径
    """
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="ReportGenerationAgent",
            description="生成Markdown报告",
            category="output",
            inputs=["ci_data_path", "merged_response", "storage_dir"],
            outputs=["report_md"],
            dependencies=["StageOrganizationAgent"],
        )
    
    def __init__(self):
        super().__init__()
    
    def run(self, state):
        """执行报告生成"""
        from evaluator.skills import CIAnalyzer
        
        ci_data_path = state.get("ci_data_path", "")
        merged_response = state.get("merged_response", "")
        storage_dir = state.get("storage_dir", "")
        
        if not merged_response:
            print("  [ERROR] merged_response 为空，无法生成报告")
            return {
                **state,
                "errors": state.get("errors", []) + ["ReportGeneration: merged_response 为空"]
            }
        
        required_sections = ["项目概述", "架构图"]
        missing = [s for s in required_sections if s not in merged_response]
        if missing:
            print(f"  [WARN] merged_response 缺少章节: {missing}")
        
        print(f"\n[Report Generation] 生成最终报告...")
        print(f"  merged_response 长度: {len(merged_response)} 字符")
        print(f"  前 100 字符: {merged_response[:100]}")
        
        if storage_dir:
            output_dir = Path(storage_dir)
        else:
            output_dir = Path(state.get("project_path", "."))
        
        report_path = str(output_dir / "CI_ARCHITECTURE.md")
        
        ci_analyzer = CIAnalyzer()
        ci_analyzer.generate_report(ci_data_path, merged_response, report_path)
        
        with open(report_path, "r", encoding="utf-8") as f:
            generated_content = f.read()
        
        if len(generated_content) < 500:
            print(f"  [ERROR] 报告内容过短 ({len(generated_content)} 字符)")
        else:
            print(f"  报告已保存: {report_path} ({len(generated_content)} 字符)")
        
        return {
            **state,
            "report_md": report_path,
        }


class SummaryGenerationAgent(BaseAgent):
    """摘要生成Agent
    
    负责从LLM响应中提取并生成分析摘要JSON。
    
    输入（CICDState）:
    - merged_response: LLM响应内容
    - ci_data: 项目数据
    - architecture_json: 架构JSON
    - storage_dir: 存储目录
    
    输出（CICDState）:
    - analysis_summary: 分析摘要
    """
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="SummaryGenerationAgent",
            description="生成分析摘要JSON",
            category="output",
            inputs=["merged_response", "ci_data", "architecture_json", "storage_dir"],
            outputs=["analysis_summary"],
            dependencies=["ReportGenerationAgent"],
        )
    
    def __init__(self):
        super().__init__()
    
    def run(self, state):
        """执行摘要生成"""
        import json
        import re
        
        merged_response = state.get("merged_response", "")
        ci_data = state.get("ci_data") or {}
        architecture_json = state.get("architecture_json") or {}
        storage_dir = state.get("storage_dir", "")
        llm_responses = state.get("llm_responses", [])
        
        if storage_dir:
            output_dir = Path(storage_dir)
        else:
            output_dir = Path(state.get("project_path", "."))
        
        summary_path = str(output_dir / "analysis_summary.json")
        
        print("\n[Summary Generation] 生成分析摘要...")
        
        parsed_data = None
        for resp in llm_responses:
            if resp.get("parsed_data"):
                parsed_data = resp["parsed_data"]
                break
        
        if parsed_data:
            summary_data = {
                "scores": parsed_data.get("scores", {}),
                "score_rationale": {},
                "findings": {
                    "strengths": parsed_data.get("strengths", []),
                    "weaknesses": parsed_data.get("weaknesses", [])
                },
                "recommendations": parsed_data.get("recommendations", [])
            }
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary_data, f, ensure_ascii=False, indent=2)
            print(f"  摘要已保存: {summary_path}")
            
            return {
                **state,
                "analysis_summary": summary_data,
            }
        
        summary_data = self._generate_summary(
            merged_response, ci_data, architecture_json, summary_path  # type: ignore[arg-type]
        )
        
        print(f"  摘要已保存: {summary_path}")
        
        return {
            **state,
            "analysis_summary": summary_data,
        }
    
    def _generate_summary(
        self,
        merged_response: str,
        ci_data: Optional[dict],
        architecture_json: Optional[dict],
        output_path: str
    ) -> dict:
        """从LLM响应中提取摘要"""
        import json
        import re
        
        summary_data = {}
        
        match = re.search(
            r'<!--\s*ANALYSIS_SUMMARY\s*(.*?)\s*ANALYSIS_SUMMARY\s*-->',
            merged_response,
            re.DOTALL
        )
        
        if match:
            try:
                summary_data = json.loads(match.group(1).strip())
                print("  从报告中提取到评估评分")
            except json.JSONDecodeError:
                print("  解析摘要JSON失败，使用默认值")
                summary_data = self._generate_default_summary(ci_data)
        else:
            print("  未找到摘要标记，使用默认值")
            summary_data = self._generate_default_summary(ci_data)
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(summary_data, f, ensure_ascii=False, indent=2)
        
        return summary_data
    
    def _generate_default_summary(self, ci_data: dict) -> dict:
        """生成默认摘要"""
        workflows = ci_data.get("workflows", {})
        return {
            "scores": {},
            "score_rationale": {},
            "findings": {
                "strengths": [],
                "weaknesses": []
            },
            "recommendations": []
        }
