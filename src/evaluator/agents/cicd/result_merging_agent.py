"""结果合并 Agent - 合并多个 LLM 响应"""
import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict

from evaluator.state import EvaluatorState
from evaluator.agents.base_agent import BaseAgent, AgentMeta


def _extract_subsection(text: str, title: str) -> str:
    """提取 ### 级别子章节（包含标题行）"""
    lines = text.split('\n')
    result = []
    in_section = False
    for line in lines:
        if re.match(r'^###\s+' + re.escape(title), line):
            in_section = True
            result.append(line)
            continue
        if in_section and (line.startswith('## ') or line.startswith('### ')):
            break
        if in_section:
            result.append(line)
    return '\n'.join(result).strip()


def _format_finding_item(item) -> str:
    """格式化 strengths/weaknesses 条目（str 或 dict）"""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        parts = []
        if item.get("title"):
            parts.append(f"**{item['title']}**")
        if item.get("description"):
            parts.append(item["description"])
        sub = []
        if item.get("evidence"):
            sub.append(f"证据：{item['evidence']}")
        if item.get("impact"):
            sub.append(f"影响：{item['impact']}")
        if item.get("suggestion"):
            sub.append(f"建议：{item['suggestion']}")
        result = "；".join(parts) if parts else str(item)
        if sub:
            result += "（" + "；".join(sub) + "）"
        return result
    return str(item)


def _format_recommendation_item(item) -> str:
    """格式化 recommendations 条目（str 或 dict）"""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        priority = item.get("priority", "")
        content = item.get("content", "")
        benefit = item.get("expected_benefit", "")
        parts = []
        if priority:
            parts.append(f"[{priority}]")
        if content:
            parts.append(content)
        result = " ".join(parts) if parts else str(item)
        if benefit:
            result += f"（预期收益：{benefit}）"
        return result
    return str(item)


class ResultMergingAgent(BaseAgent):
    """结果合并 Agent
    
    职责：合并多个 LLM 响应为一个完整的报告
    输入：EvaluatorState.llm_responses, ci_data
    输出：EvaluatorState.merged_response
    """
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="ResultMergingAgent",
            description="合并多个 LLM 响应为一个完整报告",
            category="analysis",
            inputs=["llm_responses", "ci_data", "ci_data_path"],
            outputs=["merged_response"],
            dependencies=["LLMInvocationAgent"],
        )
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行合并（LangGraph 节点接口）"""
        responses = state.get("llm_responses", [])
        ci_data = state.get("ci_data") or {}
        ci_data_path = state.get("ci_data_path") or ""
        key_configs = state.get("key_configs", [])
        rounds_data = state.get("cicd_rounds_data") or {}
        batch_outputs = state.get("cicd_batch_outputs_data") or {}
        
        merged = self.merge(responses, ci_data, ci_data_path, key_configs)
        assembled = self._assemble_structured_data(
            ci_data=ci_data,
            rounds_data=rounds_data,
            batch_outputs=batch_outputs,
            merged_response=merged,
            key_configs=key_configs,
        )
        
        return {
            **state,
            "merged_response": merged,
            "cicd_assembled_data": assembled,
            "architecture_json": assembled.get("artifacts", {}).get("architecture_json", {}),
        }

    def _assemble_structured_data(
        self,
        ci_data: Dict[str, Any],
        rounds_data: Dict[str, Any],
        batch_outputs: Dict[str, Any],
        merged_response: str,
        key_configs: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        rounds = rounds_data.get("rounds", [])
        architecture_json = {}
        overview = ""
        stage_division = ""
        architecture_diagram = ""
        call_tree = ""
        scores = {}
        strengths = []
        weaknesses = []
        recommendations = []

        for round_item in rounds:
            parsed_artifacts = round_item.get("parsed_artifacts", {}) or {}
            overview = overview or parsed_artifacts.get("overview", "")
            stage_division = stage_division or parsed_artifacts.get("stage_division", "")
            architecture_diagram = architecture_diagram or parsed_artifacts.get("architecture_diagram", "")
            call_tree = call_tree or parsed_artifacts.get("call_tree", "")
            if parsed_artifacts.get("architecture_json"):
                architecture_json = parsed_artifacts.get("architecture_json", {})
            if parsed_artifacts.get("scores"):
                scores = parsed_artifacts.get("scores", {})
            if parsed_artifacts.get("strengths"):
                strengths = parsed_artifacts.get("strengths", [])
            if parsed_artifacts.get("weaknesses"):
                weaknesses = parsed_artifacts.get("weaknesses", [])
            if parsed_artifacts.get("recommendations"):
                recommendations = parsed_artifacts.get("recommendations", [])

        report_input_data = {
            "overview": overview,
            "stage_division": stage_division,
            "architecture_diagram": architecture_diagram,
            "call_tree": call_tree,
            "merged_response": merged_response,
            "key_configs": key_configs,
        }

        # 从 merged_response 提取 ### 子章节
        arch_summary_section = _extract_subsection(merged_response, "架构特点总结")

        summary_input_data = {
            "scores": scores,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "recommendations": recommendations,
        }

        findings_markdown = "## 关键发现和建议\n\n"
        if arch_summary_section:
            findings_markdown += arch_summary_section + "\n\n"
        if strengths:
            findings_markdown += "### 优势\n"
            for item in strengths:
                findings_markdown += f"- {_format_finding_item(item)}\n"
            findings_markdown += "\n"
        if weaknesses:
            findings_markdown += "### 问题\n"
            for item in weaknesses:
                findings_markdown += f"- {_format_finding_item(item)}\n"
            findings_markdown += "\n"
        if recommendations:
            findings_markdown += "### 建议\n"
            for item in recommendations:
                findings_markdown += f"- {_format_recommendation_item(item)}\n"
            findings_markdown += "\n"

        missing_fields = []
        if not overview:
            missing_fields.append("overview")
        if not stage_division:
            missing_fields.append("stage_division")
        if not architecture_json:
            missing_fields.append("architecture_json")

        diagnostics = list(rounds_data.get("diagnostics", []))
        diagnostics.extend(batch_outputs.get("diagnostics", []))
        if missing_fields:
            diagnostics.append(f"assembly 缺少关键字段: {', '.join(missing_fields)}")

        return {
            "assembly_status": "complete" if not missing_fields else "incomplete",
            "schema_version": "v1",
            "artifacts": {
                "architecture_json": architecture_json,
                "report_input_data": report_input_data,
                "summary_input_data": summary_input_data,
                "findings_markdown": findings_markdown.strip(),
            },
            "sources": {
                "round_outputs": rounds,
                "batch_outputs": batch_outputs.get("batches", []),
                "source_ids": [r.get("round_id") for r in rounds] + [b.get("batch_id") for b in batch_outputs.get("batches", [])],
            },
            "missing_fields": missing_fields,
            "diagnostics": diagnostics,
            "workflow_count": len((ci_data or {}).get("workflows", {})),
        }
    
    def _strip_batch_summary_sections(self, content: str) -> str:
        """过滤 LLM 自发输出的本批次总结章节（## 本批次...）"""
        return re.sub(r'^##\s+本批次[^\n]*\n.*?(?=^##\s+|\Z)', '', content, flags=re.MULTILINE | re.DOTALL).strip()

    def merge(
        self,
        responses: List[Dict[str, Any]],
        ci_data: Optional[Dict[str, Any]] = None,
        ci_data_path: str = "",
        key_configs: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """合并多个 LLM 响应"""
        successful = [r for r in responses if r.get('success')]
        failed = [r for r in responses if not r.get('success')]
        
        if failed:
            print(f"  [Merge] {len(failed)} 个任务失败")
            for f in failed:
                name = Path(f.get('prompt_path', 'unknown')).name
                print(f"    - {name}: {f.get('error', 'unknown')}")
        
        if not successful:
            raise RuntimeError(f"所有 {len(failed)} 个 LLM 调用都失败")
        
        successful.sort(key=lambda x: x.get('index', 0))
        
        if len(successful) == 1:
            return successful[0]['response']
        
        overview_response = None
        detail_responses = []
        script_responses = []

        for r in successful:
            prompt_name = Path(r['prompt_path']).name
            if 'main' in prompt_name:
                overview_response = r['response']
            elif 'script' in prompt_name:
                script_responses.append(r['response'])
            else:
                detail_responses.append(self._strip_batch_summary_sections(r['response']))

        if overview_response and (detail_responses or script_responses):
            return self._merge_overview_and_details(
                overview_response, detail_responses, ci_data_path, key_configs, script_responses
            )
        elif len(successful) == 1:
            return successful[0]['response']
        else:
            return self._merge_detail_responses(detail_responses)
    
    def _merge_overview_and_details(
        self,
        overview: str,
        details: List[str],
        ci_data_path: str = "",
        key_configs: Optional[List[Dict[str, str]]] = None,
        script_responses: Optional[List[str]] = None,
    ) -> str:
        """合并概览和详细响应"""
        script_responses = script_responses or []
        merged = []
        overview_sections = self._extract_main_sections(overview)

        if overview_sections.get('overview'):
            merged.append(overview_sections['overview'])

        if overview_sections.get('architecture'):
            merged.append(overview_sections['architecture'])

        stage_info_match = re.search(r'^##\s+阶段划分说明\s*\n(.*?)(?=^##\s+)', overview, re.MULTILINE | re.DOTALL)
        if stage_info_match:
            merged.append(f"## 阶段划分说明{stage_info_match.group(1)}")

        stage_pattern = r'(^##\s+阶段[^：:\n]+[：:]\s*[^\n]+\n.*?)(?=^##\s+关键发现|^##\s+附录|^<!-- ARCHITECTURE_JSON|## 附录|$)'
        stage_matches = list(re.finditer(stage_pattern, overview, re.MULTILINE | re.DOTALL))

        for match in stage_matches:
            stage_content = match.group(1).strip()
            if stage_content:
                merged.append(stage_content)

        # 关键发现：overview 优先，否则从 workflow detail 提取，再追加 script 优化建议
        findings_content = ""
        if overview_sections.get('findings'):
            findings_content = overview_sections['findings']
        else:
            findings = self._extract_findings_section(details)
            if findings:
                findings_content = findings

        script_optimization = self._extract_script_optimization(script_responses)
        if script_optimization:
            if findings_content:
                findings_content = findings_content.rstrip() + "\n\n" + script_optimization
            else:
                findings_content = script_optimization

        if findings_content:
            merged.append(findings_content)

        appendix_content = ""
        if overview_sections.get('appendix'):
            appendix_content = overview_sections['appendix']
            appendix_content = self._wrap_call_tree(appendix_content)
        else:
            appendix = self._extract_appendix_section(details)
            if appendix:
                appendix_content = appendix

        # key_config：遍历所有 script 响应，提取完整的关键配置详细分析章节，去重合并
        key_config_section = ""
        if key_configs:
            key_config_section = self._generate_key_config_section(key_configs)
        else:
            key_config_section = self._merge_key_config_from_scripts(script_responses, details)

        if appendix_content:
            appendix_content = re.sub(r'^##\s+脚本目录索引.*?(?=^##|\Z)', '', appendix_content, flags=re.MULTILINE | re.DOTALL)
            appendix_content = appendix_content.strip()
            if appendix_content:
                merged.append(appendix_content)

        if overview_sections.get('json'):
            merged.append(overview_sections['json'])

        # 脚本目录索引：从 ci_data.json 生成基础内容，追加 script 响应的调用关系
        scripts_section = self._generate_scripts_section(ci_data_path, key_config_section)
        script_call_relations = self._extract_script_call_relations(script_responses)
        if script_call_relations:
            if scripts_section:
                scripts_section = scripts_section.rstrip() + "\n\n" + script_call_relations
            else:
                scripts_section = script_call_relations
        if scripts_section:
            merged.append(scripts_section)

        return '\n\n'.join(merged)
    
    def _extract_section_by_lines(self, content: str, title_pattern: str) -> str:
        """使用行解析提取章节，不依赖正则
        
        Args:
            content: Markdown 内容
            title_pattern: 标题模式，如 "项目概述" 或 "架构图"
        
        Returns:
            提取的章节内容（包含标题）
        """
        lines = content.split('\n')
        result = []
        in_section = False
        
        for i, line in enumerate(lines):
            if line.startswith('## ') and title_pattern in line:
                in_section = True
                result.append(line)
                continue
            
            if in_section and line.startswith('## '):
                break
            
            if in_section:
                result.append(line)
        
        return '\n'.join(result)
    
    def _extract_main_sections(self, content: str) -> Dict[str, str]:
        """提取主要章节（使用行解析替代正则）"""
        sections = {}
        
        overview = self._extract_section_by_lines(content, "项目概述")
        if overview:
            sections["overview"] = overview
        
        architecture = self._extract_section_by_lines(content, "架构图")
        if architecture:
            sections["architecture"] = architecture
        
        stage_division = self._extract_section_by_lines(content, "阶段划分")
        if stage_division:
            sections["stage_division"] = stage_division
        
        findings = self._extract_section_by_lines(content, "关键发现")
        if findings:
            sections["findings"] = findings
        
        scripts = self._extract_section_by_lines(content, "脚本目录索引")
        if scripts:
            sections["scripts"] = scripts
        
        appendix = self._extract_section_by_lines(content, "附录")
        if appendix:
            sections["appendix"] = appendix
        
        json_match = re.search(r'(<!--\s*ARCHITECTURE_JSON.*?ARCHITECTURE_JSON\s*-->)', content, re.DOTALL)
        if json_match:
            sections["json"] = json_match.group(1)
        
        return sections
    
    def _merge_stage_content(self, contents: List[str]) -> str:
        """合并相同阶段的内容"""
        if not contents:
            return ""
        
        seen_workflows = set()
        merged_lines = []
        
        for content in contents:
            lines = content.split('\n')
            for line in lines:
                wf_match = re.search(r'[-*]\s+\[.github/workflows/([^\]]+)\]', line)
                if wf_match:
                    wf_name = wf_match.group(1)
                    if wf_name not in seen_workflows:
                        seen_workflows.add(wf_name)
                        merged_lines.append(line)
                elif line.strip():
                    merged_lines.append(line)
        
        return '\n'.join(merged_lines)
    
    def _extract_findings_section(self, details: List[str]) -> Optional[str]:
        """提取关键发现章节"""
        for detail in details:
            match = re.search(
                r'(^##\s+关键发现.*?)(?=^##\s+附录|^<!--.*?ARCHITECTURE|^##\s+|$)',
                detail,
                re.MULTILINE | re.DOTALL
            )
            if match:
                return match.group(1).strip()
        return None
    
    def _extract_appendix_section(self, details: List[str]) -> Optional[str]:
        """提取附录章节"""
        for detail in details:
            match = re.search(
                r'(^##\s+附录.*?)(?=<!--.*?ARCHITECTURE|^##\s+|$)',
                detail,
                re.MULTILINE | re.DOTALL
            )
            if match:
                content = match.group(1).strip()
                content = self._wrap_call_tree(content)
                return content
        return None
    
    def _wrap_call_tree(self, content: str) -> str:
        """将调用关系树用代码块包裹
        
        检测以"项目CI/CD调用关系树"开头的 ASCII 树形结构，
        用 ``` 代码块包裹，确保在 HTML 中正确显示。
        
        如果调用关系树已被代码块包裹，则跳过处理。
        """
        lines = content.split('\n')
        result = []
        in_call_tree = False
        call_tree_buffer = []
        in_code_block = False
        
        for line in lines:
            if line.strip().startswith('```'):
                in_code_block = not in_code_block
                result.append(line)
                continue
            
            if in_code_block:
                result.append(line)
                continue
            
            if '项目CI/CD调用关系树' in line:
                in_call_tree = True
                call_tree_buffer = [line]
                continue
            
            if in_call_tree:
                if line.strip().startswith('---'):
                    result.append('```')
                    result.extend(call_tree_buffer)
                    result.append('```')
                    result.append(line)
                    in_call_tree = False
                    call_tree_buffer = []
                elif line.strip() and not any(c in line for c in ['├', '│', '└', '─']):
                    result.append('```')
                    result.extend(call_tree_buffer)
                    result.append('```')
                    result.append('')
                    result.append(line)
                    in_call_tree = False
                    call_tree_buffer = []
                else:
                    call_tree_buffer.append(line)
            else:
                result.append(line)
        
        if in_call_tree and call_tree_buffer:
            result.append('```')
            result.extend(call_tree_buffer)
            result.append('```')
        
        return '\n'.join(result)
    
    def _extract_key_config_section(self, content: str) -> str:
        """从 LLM 输出中提取"关键配置"小节
        
        Args:
            content: 包含脚本目录索引的内容
            
        Returns:
            提取的"关键配置"小节，如果不存在则返回空字符串
        """
        match = re.search(
            r'### 关键配置\s*\n.*?(?=###|##|$)',
            content,
            re.DOTALL
        )
        if match:
            return match.group(0).strip()
        return ""
    
    def _merge_detail_responses(self, details: List[str]) -> str:
        """合并多个详细响应"""
        all_sections = []
        
        for detail in details:
            sections = self._extract_main_sections(detail)
            
            for name, content in sections.items():
                if name != 'overview':
                    all_sections.append(content)
        
        return '\n\n'.join(all_sections) if all_sections else details[0]
    
    def _merge_key_config_from_scripts(self, script_responses: List[str], details: List[str]) -> str:
        """从 script 响应中提取并合并关键配置详细分析，按配置文件名去重"""
        seen_configs = set()
        table_rows = []
        extra_content_parts = []

        for resp in script_responses:
            section = self._extract_section_by_lines(resp, "关键配置详细分析")
            if not section:
                continue
            # 提取表格行（| 开头，排除表头和分隔行），遇到 ### 子节停止
            in_subsection = False
            for line in section.splitlines():
                stripped = line.strip()
                if stripped.startswith('### '):
                    in_subsection = True  # 进入子节，停止收集主表格行
                if in_subsection:
                    continue
                if stripped.startswith('|') and not re.match(r'^\|\s*[-:]+', stripped):
                    # 跳过表头行（含"配置文件"字样）
                    if '配置文件' in stripped:
                        continue
                    # 用第一列（配置文件名）去重
                    cells = [c.strip() for c in stripped.split('|') if c.strip()]
                    if cells:
                        key = cells[0]
                        if key not in seen_configs:
                            seen_configs.add(key)
                            table_rows.append(stripped)
            # 提取表格之后的深度解析内容（### 级别小节）
            in_extra = False
            for line in section.splitlines():
                if line.startswith('### ') and '关键配置' not in line and '脚本目录' not in line:
                    in_extra = True
                if in_extra:
                    extra_content_parts.append(line)

        if not table_rows and not extra_content_parts:
            # 兜底：从 workflow details 里提取旧格式的 ### 关键配置 小节
            for detail in details:
                scripts_section_text = self._extract_section_by_lines(detail, "脚本目录索引")
                if scripts_section_text:
                    part = self._extract_key_config_section(scripts_section_text)
                    if part:
                        return part
            return ""

        parts = []
        if table_rows:
            parts.append("### 关键配置\n\n| 配置文件 | 作用 | 规模 |\n|---------|------|------|")
            parts.extend(table_rows)
        if extra_content_parts:
            parts.append("\n" + "\n".join(extra_content_parts))
        return "\n".join(parts)

    def _extract_script_call_relations(self, script_responses: List[str]) -> str:
        """从所有 script 响应中提取脚本调用关系章节，合并去重"""
        all_parts = []
        seen_lines = set()
        for resp in script_responses:
            section = self._extract_section_by_lines(resp, "脚本调用关系")
            if not section:
                continue
            for line in section.splitlines():
                stripped = line.strip()
                if stripped and stripped not in seen_lines:
                    seen_lines.add(stripped)
                    all_parts.append(line)
        if not all_parts:
            return ""
        return "### 脚本调用关系\n\n" + "\n".join(all_parts)

    def _extract_script_optimization(self, script_responses: List[str]) -> str:
        """从所有 script 响应中提取配置优化建议章节，合并"""
        all_parts = []
        for resp in script_responses:
            section = self._extract_section_by_lines(resp, "配置优化建议")
            if section:
                # 去掉章节标题，只保留内容
                lines = section.splitlines()
                content_lines = [l for l in lines if not re.match(r'^##\s+配置优化建议', l)]
                content = "\n".join(content_lines).strip()
                # 将 ### N. 子项降级为 #### N.，避免 _extract_subsection 提前终止
                content = re.sub(r'^###\s+(\d+)', r'#### \1', content, flags=re.MULTILINE)
                if content:
                    all_parts.append(content)
        if not all_parts:
            return ""
        return "### 脚本配置优化建议\n\n" + "\n\n".join(all_parts)

    def _generate_scripts_section(self, ci_data_path: str, key_config_section: str = "") -> str:
        """生成脚本目录索引
        
        Args:
            ci_data_path: ci_data.json 路径
            key_config_section: LLM 输出的"关键配置"小节
        """
        try:
            with open(ci_data_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except:
            return ""
        
        scripts = data.get('scripts', [])
        if not scripts:
            return ""
        
        scripts_by_dir = defaultdict(list)
        for script in scripts:
            path = script.get('path', '')
            if path:
                dir_name = str(Path(path).parent)
                scripts_by_dir[dir_name].append({
                    'name': script.get('name', ''),
                    'type': script.get('type', ''),
                    'called_by': script.get('called_by', [])
                })
        
        lines = ["## 脚本目录索引\n"]
        
        # 添加 LLM 输出的"关键配置"小节
        if key_config_section:
            lines.append(key_config_section)
            lines.append("")
        
        ci_dirs = ['.github/scripts', 'scripts']
        sorted_dirs = []
        seen_dirs = set()
        for ci_dir in ci_dirs:
            for dir_name in scripts_by_dir.keys():
                normalized = dir_name.replace('\\', '/')
                if ci_dir in normalized and dir_name not in seen_dirs:
                    sorted_dirs.append(dir_name)
                    seen_dirs.add(dir_name)
        
        for dir_name in scripts_by_dir.keys():
            if dir_name not in seen_dirs:
                sorted_dirs.append(dir_name)
                seen_dirs.add(dir_name)
        
        lines.append("### CI 相关脚本\n")
        ci_scripts_found = False
        for dir_name in sorted_dirs:
            if '.github/scripts' in dir_name.replace('\\', '/'):
                ci_scripts_found = True
                dir_scripts = scripts_by_dir[dir_name]
                lines.append(f"**{dir_name}/** ({len(dir_scripts)} 个脚本)\n")
                for s in dir_scripts:
                    called = s.get('called_by', [])
                    called_str = ', '.join(called[:3]) if called else '无'
                    if len(called) > 3:
                        called_str += f' ...(+{len(called)-3})'
                    lines.append(f"- `{s['name']}` - 被调用: {called_str}")
                lines.append("")
        
        if not ci_scripts_found:
            lines.append("未检测到 `.github/scripts/` 目录下的 CI 脚本。\n")
        
        lines.append("### 其他脚本目录\n")
        other_dirs = [d for d in sorted_dirs if '.github/scripts' not in d.replace('\\', '/')]
        for dir_name in other_dirs:
            dir_scripts = scripts_by_dir[dir_name]
            lines.append(f"- **{dir_name}/** ({len(dir_scripts)} 个脚本)")
        
        lines.append(f"\n**总计**: {len(scripts)} 个脚本文件")
        
        return '\n'.join(lines)
    
    def _generate_key_config_section(self, key_configs: List[Dict[str, str]]) -> str:
        """从 key_configs 生成关键配置章节
        
        Args:
            key_configs: 关键配置列表，每个元素包含 name, description, scale
        
        Returns:
            Markdown 格式的关键配置章节
        """
        if not key_configs:
            return ""
        
        lines = ["### 关键配置\n"]
        lines.append("| 配置文件 | 说明 | 规模 |")
        lines.append("|----------|------|------|")
        
        for config in key_configs:
            name = config.get("name", "")
            desc = config.get("description", "")
            scale = config.get("scale", "")
            lines.append(f"| `{name}` | {desc} | {scale} |")
        
        return "\n".join(lines)
