"""结果合并 Agent - 合并多个 LLM 响应"""
import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict

from .state import CICDState
from evaluator.agents.base_agent import BaseAgent, AgentMeta


class ResultMergingAgent(BaseAgent):
    """结果合并 Agent
    
    职责：合并多个 LLM 响应为一个完整的报告
    输入：CICDState.llm_responses, ci_data
    输出：CICDState.merged_response
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
    
    def run(self, state: CICDState) -> CICDState:
        """执行合并（LangGraph 节点接口）"""
        responses = state.get("llm_responses", [])
        ci_data = state.get("ci_data") or {}
        ci_data_path = state.get("ci_data_path") or ""
        key_configs = state.get("key_configs", [])
        
        merged = self.merge(responses, ci_data, ci_data_path, key_configs)
        
        return {
            **state,
            "merged_response": merged,
        }
    
    def merge(
        self,
        responses: List[Dict[str, Any]],
        ci_data: Optional[Dict[str, Any]] = None,
        ci_data_path: str = "",
        key_configs: List[Dict[str, str]] = None,
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
        
        for r in successful:
            prompt_name = Path(r['prompt_path']).name
            if 'main' in prompt_name:
                overview_response = r['response']
            else:
                detail_responses.append(r['response'])
        
        if overview_response and detail_responses:
            return self._merge_overview_and_details(overview_response, detail_responses, ci_data_path, key_configs)
        elif len(successful) == 1:
            return successful[0]['response']
        else:
            return self._merge_detail_responses(detail_responses)
    
    def _merge_overview_and_details(
        self,
        overview: str,
        details: List[str],
        ci_data_path: str = "",
        key_configs: List[Dict[str, str]] = None,
    ) -> str:
        """合并概览和详细响应"""
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
        
        if stage_matches:
            for match in stage_matches:
                stage_content = match.group(1).strip()
                if stage_content:
                    merged.append(stage_content)
        else:
            all_stages = self._extract_and_organize_stages(details)
            for stage_content in all_stages:
                merged.append(stage_content)
        
        if overview_sections.get('findings'):
            merged.append(overview_sections['findings'])
        else:
            findings = self._extract_findings_section(details)
            if findings:
                merged.append(findings)
        
        appendix_content = ""
        if overview_sections.get('appendix'):
            appendix_content = overview_sections['appendix']
            appendix_content = self._wrap_call_tree(appendix_content)
        else:
            appendix = self._extract_appendix_section(details)
            if appendix:
                appendix_content = appendix
        
        key_config_section = ""
        if key_configs:
            key_config_section = self._generate_key_config_section(key_configs)
        else:
            for detail in details:
                scripts_section_text = self._extract_section_by_lines(detail, "脚本目录索引")
                if scripts_section_text:
                    key_config_section = self._extract_key_config_section(scripts_section_text)
                    if key_config_section:
                        break
        
        if appendix_content:
            appendix_content = re.sub(r'^##\s+脚本目录索引.*?(?=^##|\Z)', '', appendix_content, flags=re.MULTILINE | re.DOTALL)
            appendix_content = appendix_content.strip()
            if appendix_content:
                merged.append(appendix_content)
        
        if overview_sections.get('json'):
            merged.append(overview_sections['json'])
        
        scripts_section = self._generate_scripts_section(ci_data_path, key_config_section)
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
    
    def _extract_and_organize_stages(self, details: List[str]) -> List[str]:
        """从详细响应中提取并按阶段组织"""
        stages = {}
        stage_order = []
        
        for detail in details:
            pattern = r'^##\s+(阶段[^：:\n]+[：:]\s*[^\n]+)'
            for match in re.finditer(pattern, detail, re.MULTILINE):
                stage_title = match.group(1).strip()
                if stage_title not in stages:
                    stages[stage_title] = []
                    stage_order.append(stage_title)
                
                start = match.end()
                next_match = re.search(r'^##\s+', detail[start:], re.MULTILINE)
                if next_match:
                    end = start + next_match.start()
                else:
                    end = len(detail)
                
                stage_content = detail[start:end].strip()
                if stage_content and stage_content not in stages[stage_title]:
                    stages[stage_title].append(stage_content)
        
        result = []
        for stage_title in stage_order:
            combined = self._merge_stage_content(stages[stage_title])
            if combined:
                result.append(f"## {stage_title}\n\n{combined}")
        
        return result
    
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
