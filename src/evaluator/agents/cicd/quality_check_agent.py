"""质量检查 Agent - 验证报告质量"""
import re
import json
from pathlib import Path
from typing import Optional, Dict, Any

try:
    from evaluator.llm import LLMClient
    HAS_LLM = True
except ImportError:
    HAS_LLM = False
    LLMClient = None

from .state import CICDState
from evaluator.agents.base_agent import BaseAgent, AgentMeta


class QualityCheckAgent(BaseAgent):
    """质量检查 Agent
    
    职责：验证 LLM 响应的质量，包括：
    - 架构完整性
    - 概述准确性
    - 阶段划分合理性
    - JSON 数据有效性
    输入：CICDState.merged_response, ci_data, architecture_json
    输出：CICDState.validation_result
    """
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="QualityCheckAgent",
            description="验证报告质量",
            category="analysis",
            inputs=["merged_response", "ci_data"],
            outputs=["validation_result", "architecture_json_path"],
            dependencies=["ResultMergingAgent"],
        )
    
    def __init__(self, llm=None):
        super().__init__()
        self.llm = llm
    
    def run(self, state):
        """执行质量检查"""
        merged_response = state.get("merged_response", "")
        ci_data = state.get("ci_data") or {}
        storage_dir = state.get("storage_dir")
        
        output_dir = Path(storage_dir) if storage_dir else Path(state.get("project_path", "."))
        
        architecture_json_path = str(output_dir / "architecture.json")
        self._extract_architecture_json(merged_response, architecture_json_path)
        
        architecture_data = self._load_architecture_json(architecture_json_path)
        architecture_data = self._fix_trigger_layer(architecture_data, ci_data)
        
        validation = self._validate_architecture(ci_data, architecture_data)
        
        if not validation["is_complete"]:
            print(f"  [Quality] 架构不完整，补充遗漏...")
            architecture_data = self._supplement_architecture(
                architecture_data, ci_data, validation
            )
            with open(architecture_json_path, "w", encoding="utf-8") as f:
                json.dump(architecture_data, f, ensure_ascii=False, indent=2)
        
        # 跳过 _organize_stages（StageOrganizationAgent 会在后续处理）
        
        overview_match = re.search(r'^##\s+项目概述\s*\n(.*?)(?=^##\s+)', merged_response, re.MULTILINE | re.DOTALL)
        if overview_match:
            overview = f"## 项目概述{overview_match.group(1)}"
            overview_validation = self._validate_overview(overview, ci_data)
            if not overview_validation["is_accurate"]:
                corrected_overview = overview_validation["corrected_overview"]
                merged_response = merged_response[:overview_match.start()] + corrected_overview + merged_response[overview_match.end():]
        
        return {
            **state,
            "merged_response": merged_response,
            "architecture_json": architecture_data,
            "validation_result": validation,
        }
    
    def _extract_architecture_json(self, content: str, output_path: str) -> None:
        """从响应中提取架构 JSON"""
        match = re.search(
            r'<!--\s*ARCHITECTURE_JSON\s*(.*?)\s*ARCHITECTURE_JSON\s*-->',
            content,
            re.DOTALL
        )
        
        if match:
            try:
                arch_data = json.loads(match.group(1).strip())
                arch_data = self._normalize_node_labels(arch_data)
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(arch_data, f, ensure_ascii=False, indent=2)
                return
            except json.JSONDecodeError:
                pass
        
        sections = self._extract_sections(content)
        if not sections:
            self._save_empty_architecture_json(output_path)
            return
        
        sections_text = "\n".join([
            f"{'  ' * (s['level'] - 2)}{'##' if s['level'] == 2 else '###'} {s['title']}"
            for s in sections[:25]
        ])
        
        prompt = f'''根据以下 CI/CD 报告章节，生成架构图的 JSON 结构。

章节:
{sections_text}

输出 JSON 格式:
{{"layers": [{{"id": "layer1", "name": "层名", "nodes": [{{"id": "n1", "label": "节点名", "description": "描述"}}]}}], "connections": [{{"source": "n1", "target": "n2"}}]}}
'''
        
        if self.llm:
            try:
                response = self.llm.chat(prompt)
                json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                else:
                    json_str = response.strip()
                
                arch_data = json.loads(json_str)
                arch_data = self._normalize_node_labels(arch_data)
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(arch_data, f, ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                self._save_empty_architecture_json(output_path)
        else:
            self._save_empty_architecture_json(output_path)
    
    def _normalize_node_labels(self, arch_data: Dict) -> Dict:
        """统一节点标签格式：为工作流节点添加 .yml 后缀"""
        VALID_TRIGGERS = {
            "push", "pull_request", "pull_request_target", "pull_request_review",
            "pull_request_review_comment", "schedule", "workflow_dispatch", 
            "workflow_call", "issues", "issue_comment", "create", "delete",
            "repository_dispatch", "release", "workflow_run"
        }
        
        for layer in arch_data.get("layers", []):
            for node in layer.get("nodes", []):
                label = node.get("label", "")
                if not label.endswith(".yml") and not label.endswith(".yaml"):
                    base_label = label.split(" (")[0].strip()
                    if base_label not in VALID_TRIGGERS and "事件" not in label:
                        node["label"] = f"{label}.yml"
        
        return arch_data
    
    def _extract_sections(self, content: str) -> list:
        """提取所有章节标题"""
        sections = []
        pattern = r'^(#{2,4})\s+(.+)$'
        for match in re.finditer(pattern, content, re.MULTILINE):
            level = len(match.group(1))
            title = match.group(2).strip()
            sections.append({"level": level, "title": title})
        return sections
    
    def _save_empty_architecture_json(self, output_path: str) -> None:
        """保存空的架构图 JSON"""
        empty_data = {"layers": [], "connections": []}
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(empty_data, f, ensure_ascii=False, indent=2)
    
    def _load_architecture_json(self, path: str) -> Dict[str, Any]:
        """加载架构 JSON"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {"layers": [], "connections": []}
    
    def _fix_trigger_layer(self, architecture_data: Dict, ci_data: Dict) -> Dict:
        """修正触发入口层"""
        triggers = {}
        for wf_name, wf_data in ci_data.get("workflows", {}).items():
            for trigger_type in wf_data.get("triggers", []):
                triggers[trigger_type] = triggers.get(trigger_type, 0) + 1
        
        if not triggers:
            return architecture_data
        
        layers = architecture_data.get("layers", [])
        trigger_layer_exists = False
        trigger_layer_index = -1
        
        for i, layer in enumerate(layers):
            layer_name = layer.get("name", "").lower()
            if "trigger" in layer_name or "入口" in layer.get("name", "") or "触发" in layer.get("name", ""):
                trigger_layer_exists = True
                trigger_layer_index = i
                break
        
        if not trigger_layer_exists:
            trigger_nodes = []
            for trigger, count in triggers.items():
                if count >= 1:
                    trigger_nodes.append({
                        "id": f"trigger_{trigger}",
                        "label": f"{trigger}.yml",
                        "description": f"触发器: {trigger}",
                    })
            
            if trigger_nodes:
                trigger_layer = {
                    "id": "trigger_layer",
                    "name": "触发层 (入口)",
                    "nodes": trigger_nodes
                }
                layers.insert(0, trigger_layer)
                architecture_data["layers"] = layers
        
        return architecture_data
    
    def _validate_architecture(self, ci_data: Dict, architecture_data: Dict) -> Dict:
        """验证架构完整性"""
        workflows = ci_data.get("workflows", {})
        workflow_names = set(workflows.keys())
        
        reported_workflows = set()
        for layer in architecture_data.get("layers", []):
            for node in layer.get("nodes", []):
                label = node.get("label", "")
                if label.endswith(".yml"):
                    reported_workflows.add(label)
        
        missing_workflows = workflow_names - reported_workflows
        
        trigger_types = set()
        for wf_data in workflows.values():
            trigger_types.update(wf_data.get("triggers", []))
        
        reported_triggers = set()
        for layer in architecture_data.get("layers", []):
            if "trigger" in layer.get("name", "").lower() or "入口" in layer.get("name", "") or "触发" in layer.get("name", ""):
                for node in layer.get("nodes", []):
                    label = node.get("label", "")
                    if label.endswith(".yml"):
                        trigger_types_list = label.replace(".yml", "")
                        reported_triggers.add(trigger_types_list)
        
        missing_triggers = trigger_types - reported_triggers
        
        return {
            "is_complete": len(missing_workflows) == 0 and len(missing_triggers) == 0,
            "missing_workflows": list(missing_workflows),
            "missing_trigger_types": list(missing_triggers),
        }
    
    def _supplement_architecture(
        self,
        architecture_data: Dict,
        ci_data: Optional[Dict],
        validation: Dict
    ) -> Dict:
        """补充架构数据"""
        layers = architecture_data.get("layers", [])
        
        missing_workflows = validation.get("missing_workflows", [])
        if missing_workflows:
            build_layer = None
            for layer in layers:
                layer_name = layer.get("name", "").lower()
                if "build" in layer_name or "构建" in layer.get("name", ""):
                    build_layer = layer
                    break
            
            if build_layer is None and layers:
                build_layer = layers[-1]
            
            if build_layer:
                existing_labels = {n.get("label", "") for n in build_layer.get("nodes", [])}
                for wf_name in missing_workflows:
                    if wf_name not in existing_labels:
                        build_layer["nodes"].append({
                            "id": f"wf_{wf_name}",
                            "label": wf_name,
                            "description": "从工作流补充",
                        })
        
        return architecture_data
    
    def _organize_stages(
        self,
        content: str,
        architecture_data: Dict,
        ci_data: Dict
    ) -> str:
        """组织阶段划分"""
        if not self.llm:
            return content
        
        layers = architecture_data.get("layers", [])
        if not layers:
            return content
        
        stage_info = []
        for i, layer in enumerate(layers, 1):
            nodes = layer.get("nodes", [])
            wf_names = [n.get("label", "") for n in nodes if n.get("label", "").endswith(".yml")]
            stage_info.append(f"阶段 {i}: {layer.get('name', '')} - {len(wf_names)} 个工作流")
        
        prompt = f'''请重新组织以下 CI/CD 报告的阶段划分，使其与架构一致。

当前架构:
{chr(10).join(stage_info)}

报告内容:
{content[:8000]}

要求:
1. 确保每个阶段对应架构中的一个 layer
2. 工作流应放在正确的阶段下
3. 保持报告的其他内容不变

只输出修改后的报告内容，不要其他说明。'''
        
        try:
            organized = self.llm.chat(prompt)
            if organized and len(organized) > 500:
                return organized
        except:
            pass
        
        return content
    
    def _validate_overview(self, overview: str, ci_data: Optional[Dict]) -> Dict:
        """验证概述准确性"""
        workflows = ci_data.get("workflows", {})
        actual_count = len(workflows)
        
        count_match = re.search(r'工作流[:：]\s*(\d+)', overview)
        if count_match:
            reported_count = int(count_match.group(1))
            is_accurate = reported_count == actual_count
            
            if not is_accurate:
                corrected = overview.replace(
                    f"工作流: {reported_count}",
                    f"工作流: {actual_count}"
                )
                return {
                    "is_accurate": False,
                    "workflow_count_in_overview": reported_count,
                    "actual_workflow_count": actual_count,
                    "corrected_overview": corrected,
                }
        
        return {"is_accurate": True}
