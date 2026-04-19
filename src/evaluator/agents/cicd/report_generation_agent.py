"""报告生成Agent - 生成Markdown和HTML报告"""
from pathlib import Path
from typing import Optional, Dict, Any

from evaluator.state import EvaluatorState
from evaluator.agents.base_agent import BaseAgent, AgentMeta


class ReportGenerationAgent(BaseAgent):
    """报告生成Agent
    
    负责生成最终的Markdown和HTML报告。
    
    输入（EvaluatorState）:
    - ci_data_path: CI数据路径
    - merged_response: LLM响应内容
    - storage_dir: 存储目录
    
    输出（EvaluatorState）:
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

    def _render_markdown_from_report_artifacts(self, report_artifacts: Dict[str, Any]) -> str:
        import re as _re
        lines = []
        for section in sorted(report_artifacts.get("sections", []), key=lambda s: s.get("order", 0)):
            title = section.get("title", "")
            section_id = section.get("section_id", "")
            if section_id == "architecture":
                lines.append(f"## {title}\n")
                diagram = ""
                for block in section.get("content_blocks", []):
                    if block.get("slot") == "architecture_diagram":
                        diagram = block.get("value", "")
                        break
                if diagram:
                    normalized = diagram.replace(f"## {title}", "").strip()
                    lines.append((normalized or diagram).strip() + "\n")
                else:
                    lines.append("未生成架构图内容。\n")
                continue
            if section_id == "stage_details":
                for stage_idx, stage in enumerate(
                    section.get("content_blocks", [{}])[0].get("value", []), start=1
                ):
                    lines.append(f"## {stage.get('stage_name', '')}\n")
                    if stage.get("description"):
                        lines.append(f"{stage.get('description')}\n")
                    for wf_idx, wf in enumerate(stage.get("workflows", []), start=1):
                        detail = wf.get("detail_markdown", "")
                        if detail:
                            new_num = f"{stage_idx}.{wf_idx}"
                            # 先尝试有数字的标题（正常路径）
                            new_detail, n = _re.subn(
                                r'^#{3,4}\s+\d+(?:\.\d+)*\.?\s+',
                                f'### {new_num} ',
                                detail,
                                count=1,
                                flags=_re.MULTILINE,
                            )
                            if n == 0:
                                # 占位符路径：标题无数字，直接替换第一个 ###/#### 标题
                                new_detail = _re.sub(
                                    r'^#{3,4}\s+',
                                    f'### {new_num} ',
                                    detail,
                                    count=1,
                                    flags=_re.MULTILINE,
                                )
                            lines.append(new_detail)
                    lines.append("")
                continue

            lines.append(f"## {title}\n")
            for block in section.get("content_blocks", []):
                value = block.get("value")
                if isinstance(value, str) and value:
                    # 去掉 value 开头的 ## 标题行，避免与上面已写入的 ## {title} 重复
                    if value.startswith("## "):
                        first_newline = value.find('\n')
                        value = value[first_newline + 1:].lstrip('\n') if first_newline != -1 else ""
                    if value:
                        lines.append(value + "\n")
                elif isinstance(value, list) and block.get("slot") == "findings_entries":
                    for item in value:
                        if isinstance(item, dict):
                            title_text = item.get("title", "")
                            description = item.get("description", "")
                            impact = item.get("impact", "")
                            suggestion = item.get("suggestion", "")
                            evidence = item.get("evidence", "")
                            priority = item.get("priority", "")
                            content = item.get("content", "")
                            expected_benefit = item.get("expected_benefit", "")
                            if title_text:
                                lines.append(f"#### {title_text}\n")
                            if description:
                                lines.append(f"{description}\n")
                            if evidence:
                                lines.append(f"- 证据：{evidence}\n")
                            if impact:
                                lines.append(f"- 影响：{impact}\n")
                            if suggestion:
                                lines.append(f"- 建议：{suggestion}\n")
                            if priority or content:
                                lines.append(f"- 优先级：{priority or '未定义'}\n")
                                if content:
                                    lines.append(f"- 内容：{content}\n")
                            if expected_benefit:
                                lines.append(f"- 预期收益：{expected_benefit}\n")
                            lines.append("\n")
                elif isinstance(value, list) and block.get("slot") == "key_config_entries":
                    if value:
                        lines.append("### 关键配置\n")
                        lines.append("| 配置文件 | 作用 | 规模 |\n|---------|------|------|")
                        for item in value:
                            lines.append(f"| {item.get('name', '')} | {item.get('description', '')} | {item.get('scale', '')} |")
                        lines.append("\n")
            lines.append("\n")

        return "\n".join(lines).strip() + "\n"
    
    def _fix_trigger_section(self, content: str, architecture_json: dict) -> str:
        """用 architecture.json 的触发入口层数据修正 markdown 中的触发入口章节"""
        import re
        if not architecture_json:
            return content
        trigger_labels = []
        for layer in architecture_json.get("layers", []):
            layer_name = layer.get("name", "")
            layer_id = layer.get("id", "")
            is_trigger = (
                "触发" in layer_name or "入口" in layer_name or "trigger" in layer_name.lower()
                or "trigger" in layer_id.lower()
            )
            if is_trigger:
                trigger_labels = [n["label"] for n in layer.get("nodes", []) if n.get("label")]
                break
        if not trigger_labels:
            return content
        trigger_str = ", ".join(sorted(trigger_labels))
        content = re.sub(
            r'(\|\s*阶段[一1][:：]触发入口\s*\|)[^\|]+(\|)',
            rf'\1 {trigger_str} \2',
            content
        )
        return content

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行报告生成"""
        from evaluator.skills import CIAnalyzer
        
        ci_data_path = state.get("ci_data_path", "")
        assembled_data = state.get("cicd_assembled_data") or {}
        report_input_data = assembled_data.get("artifacts", {}).get("report_input_data", {})
        merged_response = report_input_data.get("merged_response") or state.get("merged_response", "")
        report_artifacts = state.get("report_artifacts") or {}
        storage_dir = state.get("storage_dir", "")

        print(f"\n[Report Generation] 生成最终报告...")
        if merged_response:
            print(f"  merged_response 长度: {len(merged_response)} 字符")
            print(f"  前 100 字符: {merged_response[:100]}")
        else:
            print("  merged_response 为空，将优先依赖 report_artifacts 生成报告")
        
        if storage_dir:
            output_dir = Path(storage_dir)
        else:
            output_dir = Path(state.get("project_path", "."))
        
        report_path = str(output_dir / "CI_ARCHITECTURE.md")

        if report_artifacts.get("sections"):
            rendered_markdown = self._render_markdown_from_report_artifacts(report_artifacts)
            Path(report_path).write_text(rendered_markdown, encoding="utf-8")
        else:
            if not merged_response:
                print("  [ERROR] 缺少 report_artifacts 和 merged_response，无法生成报告")
                return {
                    **state,
                    "errors": state.get("errors", []) + ["ReportGeneration: 缺少 report_artifacts 和 merged_response"]
                }

            required_sections = ["项目概述", "架构图"]
            missing = [s for s in required_sections if s not in merged_response]
            if missing:
                print(f"  [WARN] merged_response 缺少章节: {missing}")

            ci_analyzer = CIAnalyzer()
            ci_analyzer.generate_report(ci_data_path, merged_response, report_path)
        
        with open(report_path, "r", encoding="utf-8") as f:
            generated_content = f.read()

        # 用 architecture.json 的触发入口数据修正 markdown，保证单一真相源
        architecture_json = state.get("architecture_json") or {}
        generated_content = self._fix_trigger_section(generated_content, architecture_json)
        Path(report_path).write_text(generated_content, encoding="utf-8")

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
    
    输入（EvaluatorState）:
    - merged_response: LLM响应内容
    - ci_data: 项目数据
    - architecture_json: 架构JSON
    - storage_dir: 存储目录
    
    输出（EvaluatorState）:
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
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行摘要生成"""
        import json
        import re
        
        merged_response = state.get("merged_response", "")
        ci_data = state.get("ci_data") or {}
        assembled_data = state.get("cicd_assembled_data") or {}
        architecture_json = assembled_data.get("artifacts", {}).get("architecture_json") or state.get("architecture_json") or {}
        summary_input_data = assembled_data.get("artifacts", {}).get("summary_input_data", {})
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
        
        if summary_input_data:
            summary_data = {
                "scores": summary_input_data.get("scores", {}),
                "score_rationale": {},
                "findings": {
                    "strengths": summary_input_data.get("strengths", []),
                    "weaknesses": summary_input_data.get("weaknesses", []),
                },
                "recommendations": summary_input_data.get("recommendations", []),
            }
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary_data, f, ensure_ascii=False, indent=2)
            print(f"  摘要已保存: {summary_path}")

            # 构建 cicd_analysis 字段供后续节点使用
            workflow_count = state.get("workflow_count", 0)
            actions_count = len(ci_data.get("actions", []))

            return {
                **state,
                "analysis_summary": summary_data,
                "cicd_analysis": {
                    "status": "success",
                    "workflows_count": workflow_count,
                    "actions_count": actions_count,
                    "ci_data_path": state.get("ci_data_path"),
                    "report_path": state.get("report_md"),
                    "architecture_json_path": state.get("architecture_json_path"),
                    "analysis_summary_path": summary_path,
                },
            }

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

            # 构建 cicd_analysis 字段供后续节点使用
            workflow_count = state.get("workflow_count", 0)
            actions_count = len(ci_data.get("actions", []))

            return {
                **state,
                "analysis_summary": summary_data,
                "cicd_analysis": {
                    "status": "success",
                    "workflows_count": workflow_count,
                    "actions_count": actions_count,
                    "ci_data_path": state.get("ci_data_path"),
                    "report_path": state.get("report_md"),
                    "architecture_json_path": state.get("architecture_json_path"),
                    "analysis_summary_path": summary_path,
                },
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
                summary_data = self._generate_default_summary(ci_data or {})
        else:
            print("  未找到摘要标记，使用默认值")
            summary_data = self._generate_default_summary(ci_data or {})
        
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
