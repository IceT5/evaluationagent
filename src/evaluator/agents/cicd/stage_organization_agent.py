"""阶段组织Agent - 根据架构图重新组织报告阶段"""
import json
import re
from pathlib import Path
from typing import Optional, Dict, Any

from evaluator.state import EvaluatorState
from evaluator.agents.base_agent import BaseAgent, AgentMeta


class StageOrganizationAgent(BaseAgent):
    """阶段组织Agent
    
    负责验证和组织报告的阶段结构：
    1. 验证阶段组织是否正确
    2. 根据架构图重新组织阶段内容
    
    输入（EvaluatorState）:
    - merged_response: LLM响应
    - architecture_json: 架构JSON
    - ci_data: 项目数据
    
    输出（EvaluatorState）:
    - merged_response: 组织后的响应
    """
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="StageOrganizationAgent",
            description="根据架构图重新组织报告阶段",
            category="analysis",
            inputs=["merged_response", "architecture_json", "ci_data"],
            outputs=["merged_response"],
            dependencies=["QualityCheckAgent"],
        )
    
    def run(self, state: EvaluatorState) -> EvaluatorState:
        """执行阶段组织"""
        merged_response = state.get("merged_response", "")
        architecture_json = state.get("architecture_json", {})
        ci_data = state.get("ci_data") or {}
        
        if not merged_response or not architecture_json:
            return state
        
        print("\n[Stage Organization] 验证并组织阶段...")
        
        _ci_data: dict = ci_data if ci_data else {}
        organized = self._organize_stages(merged_response, architecture_json, _ci_data)  # type: ignore[arg-type]
        
        return {
            **state,
            "merged_response": organized,
        }
    
    def _organize_stages(
        self,
        llm_response: str,
        architecture_data: dict,
        ci_data: Optional[dict]
    ) -> str:
        """验证并重新组织阶段"""
        try:
            validation = self._validate_stage_organization(llm_response, architecture_data)
            
            if validation["valid"]:
                print("  [OK] 阶段划分检视通过")
                return llm_response
            
            print("  [WARN] 阶段划分检视发现问题:")
            if validation.get("missing_stages"):
                print(f"    - 缺失阶段: {validation['missing_stages']}")
            print(f"    - 工作流覆盖率: {validation.get('workflow_coverage', 0):.1%}")
            
            if validation.get("workflow_coverage", 0) < 0.5:
                print("  [WARN] 工作流覆盖率过低，跳过自动重新组织")
                return llm_response
            
            try:
                reorganized = self._reorganize_by_architecture(llm_response, architecture_data, ci_data)
                
                re_validation = self._validate_stage_organization(reorganized, architecture_data)
                if re_validation["valid"] or re_validation.get("workflow_coverage", 0) > validation.get("workflow_coverage", 0):
                    print("  [OK] 阶段重新组织成功")
                    return reorganized
                else:
                    print("  [WARN] 代码重新组织效果不佳，保持原报告")
                    return llm_response
            except Exception as e:
                print(f"  [WARN] 阶段重新组织失败: {e}，保持原报告")
                return llm_response
        except Exception as e:
            print(f"  [WARN] 阶段组织异常: {e}")
            return llm_response
    
    def _validate_stage_organization(
        self,
        llm_response: str,
        architecture_data: dict
    ) -> Dict[str, Any]:
        """验证阶段划分是否与架构图匹配
        
        Args:
            llm_response: LLM 响应内容
            architecture_data: 架构图 JSON 数据
        
        Returns:
            {
                "valid": bool,
                "expected_stages": List[str],
                "found_stages": List[str],
                "missing_stages": List[str],
                "workflow_coverage": float
            }
        """
        layers = architecture_data.get("layers", [])
        expected_stages = [layer.get("name", "") for layer in layers]
        
        found_stages = re.findall(r'^##\s+(.+?)\s*$', llm_response, re.MULTILINE)
        
        missing_stages = []
        for stage in expected_stages:
            if not any(stage in found for found in found_stages):
                missing_stages.append(stage)
        
        expected_workflows = set()
        for layer in layers:
            for node in layer.get("nodes", []):
                label = node.get("label", "")
                if label.endswith(".yml"):
                    expected_workflows.add(label)
        
        found_workflows = set(re.findall(r'####\s+\d+\.\d+\s+([\w-]+\.yml)', llm_response))
        coverage = len(found_workflows & expected_workflows) / len(expected_workflows) if expected_workflows else 0
        
        return {
            "valid": len(missing_stages) == 0 and coverage >= 0.8,
            "expected_stages": expected_stages,
            "found_stages": list(found_stages),
            "missing_stages": missing_stages,
            "workflow_coverage": coverage
        }
    
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
    
    def _is_workflow_short_name(self, label: str, ci_data: dict) -> bool:
        """判断是否是 workflow 简短名称
        
        如 'two-stage-linux' 是 'workflow-dispatch-two-stage-linux.yml' 的简短名称
        """
        return self._get_full_workflow_name(label, ci_data) is not None
    
    def _get_full_workflow_name(self, short_name: str, ci_data: dict) -> Optional[str]:
        """获取完整 workflow 名称
        
        支持多种简短名称格式：
        1. 直接匹配: 'build-rapids' -> 'build-rapids.yml'
        2. 去掉前缀: 'two-stage-linux' -> 'workflow-dispatch-two-stage-linux.yml'
        3. 带 .yml: 'build-rapids.yml' -> 'build-rapids.yml'
        """
        workflows = ci_data.get("workflows", {})
        
        # 如果已经是完整名称
        if short_name in workflows:
            return short_name
        
        # 尝试添加 .yml
        if short_name.endswith(".yml") or short_name.endswith(".yaml"):
            pass
        else:
            yml_name = f"{short_name}.yml"
            if yml_name in workflows:
                return yml_name
        
        # 尝试去掉常见前缀
        prefixes_to_try = [
            "workflow-dispatch-",
            "ci-workflow-",
            "workflow-",
        ]
        for prefix in prefixes_to_try:
            full_name = f"{prefix}{short_name}.yml"
            if full_name in workflows:
                return full_name
        
        # 尝试从完整名称去掉后缀来匹配
        for wf_name in workflows:
            # 去掉 .yml
            name_without_ext = wf_name.replace(".yml", "").replace(".yaml", "")
            if short_name == name_without_ext:
                return wf_name
            # 去掉前缀
            for prefix in prefixes_to_try:
                if name_without_ext.startswith(prefix):
                    short = name_without_ext[len(prefix):]
                    if short_name == short:
                        return wf_name
        
        return None
    
    def _extract_all_workflow_details(self, llm_response: str) -> Dict[str, str]:
        """提取所有 workflow 详细描述
        
        支持多种格式：
        1. #### 数字.数字 workflow-name.yml
        2. #### workflow-name.yml
        3. ### workflow-name.yml
        """
        workflow_details = {}
        
        patterns = [
            r'(####\s+\d+\.\d+\s+(.+?)\s*\n)([\s\S]*?)(?=\n####\s+\d+\.\d+\s+|<!-- ARCHITECTURE_JSON|## 关键发现|## 附录)',
            r'(####\s+([\w-]+\.yml)\s*\n)([\s\S]*?)(?=\n####\s+[\w-]+\.yml|<!-- ARCHITECTURE_JSON|## 关键发现|## 附录)',
            r'(###\s+([\w-]+\.yml)\s*\n)([\s\S]*?)(?=\n###\s+[\w-]+\.yml|<!-- ARCHITECTURE_JSON|## 关键发现|## 附录)',
        ]
        
        for pattern in patterns:
            for match in re.finditer(pattern, llm_response):
                wf_header = match.group(1)
                wf_title = match.group(2).strip()
                wf_content = match.group(3)
                
                wf_name = wf_title.strip('`"\'()[]{}')
                
                if wf_name.endswith('.yml') or wf_name.endswith('.yaml'):
                    wf_content = re.sub(r'^##\s+阶段[^：:\n]+[：:].*?\n', '', wf_content, flags=re.MULTILINE)
                    wf_content = wf_content.strip()
                    if wf_name not in workflow_details:
                        workflow_details[wf_name] = f"{wf_header}{wf_content}"
        
        return workflow_details
    
    def _clean_batch_markers(self, content: str) -> str:
        """清理批次标记和批次标题"""
        content = re.sub(
            r'#\s*CI/CD\s+架构分析.*?批次.*?\d+/\d+.*?\n---\n?',
            '',
            content,
            flags=re.IGNORECASE | re.DOTALL
        )
        content = re.sub(
            r'本批次涵盖了.*?(?=\n---\n)',
            '',
            content,
            flags=re.DOTALL
        )
        return content
    
    def _reorganize_by_architecture(
        self,
        llm_response: str,
        architecture_data: dict,
        ci_data: dict
    ) -> str:
        """根据架构图重新组织阶段"""
        layers = architecture_data.get("layers", [])
        if not layers:
            return llm_response
        
        # 1. 从 Round 2 表格提取阶段说明（权威来源）
        stage_descriptions = self._extract_stage_descriptions_from_table(llm_response)
        
        # 2. 删除批次生成的阶段说明（可能错误）
        llm_response = self._remove_batch_stage_descriptions(llm_response)
        
        # 3. 清理批次标记
        llm_response = self._clean_batch_markers(llm_response)
        
        organized = []
        
        overview = self._extract_section_by_lines(llm_response, "项目概述")
        if overview:
            organized.append(overview)
        
        arch = self._extract_section_by_lines(llm_response, "架构图")
        if arch:
            organized.append(arch)
        
        stage_division = self._extract_section_by_lines(llm_response, "阶段划分")
        if stage_division:
            organized.append(stage_division)
        
        workflow_details = self._extract_all_workflow_details(llm_response)
        
        used_workflows = set()
        
        for i, layer in enumerate(layers, 1):
            layer_name = layer.get("name", f"阶段{i}")
            layer_sections = []
            layer_has_content = False
            
            trigger_info = []
            wf_in_layer = []
            
            for node in layer.get("nodes", []):
                label = node.get("label", "")
                description = node.get("description", "")
                
                if label.endswith(".yml") and label in workflow_details:
                    if label in used_workflows:
                        continue
                    wf_in_layer.append((label, workflow_details[label]))
                    used_workflows.add(label)
                elif self._is_workflow_short_name(label, ci_data):
                    full_name = self._get_full_workflow_name(label, ci_data)
                    if full_name and full_name in workflow_details:
                        if full_name in used_workflows:
                            continue
                        wf_in_layer.append((full_name, workflow_details[full_name]))
                        used_workflows.add(full_name)
                else:
                    trigger_info.append(f"### {label}\n{description}\n")
            
            if trigger_info:
                layer_sections.append(f"## {layer_name}\n")
                layer_sections.extend(trigger_info)
                layer_has_content = True
            
            if wf_in_layer:
                if not layer_has_content:
                    layer_sections.append(f"## {layer_name}\n")
                    # 在阶段章节开头插入阶段说明
                    matched_desc = self._match_stage_description(layer_name, stage_descriptions)
                    if matched_desc:
                        layer_sections.append(f"\n{matched_desc}\n")
                for j, (wf_name, content) in enumerate(wf_in_layer, 1):
                    new_num = f"{i}.{j}"
                    content = re.sub(r'####\s+\d+\.\d+', f'#### {new_num}', content, count=1)
                    layer_sections.append(f"\n{content}")
                layer_has_content = True
            
            if layer_has_content:
                organized.append("\n".join(layer_sections))
        
        all_workflows = set(ci_data.get("workflows", {}).keys())
        unassigned = all_workflows - used_workflows
        
        if unassigned:
            print(f"  [WARN] 未分配到阶段的工作流: {unassigned}")
            unassigned_section = ["\n## 其他\n"]
            unassigned_count = 0
            for wf_name in unassigned:
                if wf_name in workflow_details:
                    unassigned_count += 1
                    content = workflow_details[wf_name]
                    content = re.sub(r'####\s+\d+\.\d+', f'#### 99.{unassigned_count}', content, count=1)
                    unassigned_section.append("\n" + content)
            if unassigned_count > 0:
                organized.append("\n".join(unassigned_section))
        
        findings = self._extract_section_by_lines(llm_response, "关键发现")
        if findings:
            organized.append(findings)
        
        scripts = self._extract_section_by_lines(llm_response, "脚本目录索引")
        if scripts:
            organized.append(scripts)
        
        appendix = self._extract_section_by_lines(llm_response, "附录")
        if appendix:
            appendix_content = appendix.replace("## 附录\n", "")
            appendix_content = re.sub(r'\n##\s+脚本目录索引.*', '', appendix_content, flags=re.DOTALL)
            appendix_content = re.sub(
                r'<!--\s*ARCHITECTURE_JSON.*?ARCHITECTURE_JSON\s*-->',
                '',
                appendix_content,
                flags=re.DOTALL
            )
            appendix_content = re.sub(
                r'#\s*CI/CD\s+架构分析.*?批次.*?\d+/\d+.*?\n---\n?',
                '',
                appendix_content,
                flags=re.IGNORECASE | re.DOTALL
            )
            if appendix_content.strip():
                organized.append(f"## 附录\n{appendix_content.strip()}")
        
        return "\n\n".join(organized)
    
    def _match_stage_description(self, layer_name: str, stage_descriptions: Dict[str, str]) -> Optional[str]:
        """匹配层名称与阶段说明
        
        Args:
            layer_name: 层名称，如 "触发入口层"
            stage_descriptions: 从阶段表格提取的说明
        
        Returns:
            匹配的阶段说明，或 None
        """
        for stage_name, desc in stage_descriptions.items():
            # 提取阶段简称： "阶段一：触发入口" → "触发入口"
            stage_short = stage_name.split('：')[-1] if '：' in stage_name else stage_name
            # 匹配：层名称包含阶段简称，或阶段简称包含层名称（去掉"层"字）
            layer_short = layer_name.replace('层', '').strip()
            if stage_short in layer_name or layer_short in stage_short:
                return desc
        
        return None
    
    def _extract_stage_descriptions_from_table(self, llm_response: str) -> Dict[str, str]:
        """从阶段划分表格提取每个阶段的说明
        
        Returns:
            Dict[阶段名称, 阶段说明]
            例如: {"阶段一：触发入口": "主入口工作流，响应 push、定时调度等触发事件"}
        """
        descriptions = {}
        
        table_pattern = r'## 阶段划分.*?\n\n\|.*?\n\|.*?\n\|.*?\n((?:\|.*?\n)+)'
        match = re.search(table_pattern, llm_response, re.DOTALL)
        if not match:
            return descriptions
        
        table_content = match.group(1)
        
        for line in table_content.strip().split('\n'):
            if not line.startswith('|'):
                continue
            
            cells = [c.strip() for c in line.split('|')]
            if len(cells) >= 4:
                stage_name = cells[1]
                description = cells[3]
                if stage_name and description:
                    descriptions[stage_name] = description
        
        return descriptions
    
    def _remove_batch_stage_descriptions(self, content: str) -> str:
        """删除批次 prompt 生成的阶段说明
        
        批次 prompt 生成的阶段说明格式：
        ### 阶段说明
        此阶段负责xxx...
        ### 触发条件
        ...
        
        需要删除 "### 阶段说明" 到下一个 "###" 或 "####" 之间的内容
        """
        pattern = r'\n### 阶段说明\n.*?(?=\n###|\n####|\n##|\Z)'
        
        return re.sub(pattern, '', content, flags=re.DOTALL)
