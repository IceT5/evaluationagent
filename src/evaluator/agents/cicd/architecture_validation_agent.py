"""架构验证Agent - 验证和补充架构数据"""
import json
import re
from pathlib import Path
from typing import Optional, Dict, Any, Set, List

from .state import CICDState
from evaluator.agents.base_agent import BaseAgent, AgentMeta


class ArchitectureValidationAgent(BaseAgent):
    """架构验证Agent
    
    负责架构验证和补充：
    1. 验证架构完整性（工作流、触发类型）
    2. 修正触发入口层
    3. 补充遗漏的工作流
    
    输入（CICDState）:
    - ci_data: 项目数据
    - architecture_json: 架构JSON路径
    - validation_result: 验证结果（来自ReviewerAgent）
    
    输出（CICDState）:
    - architecture_json: 更新后的架构JSON路径
    - validation_result: 更新后的验证结果
    """
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="ArchitectureValidationAgent",
            description="验证和补充架构数据",
            category="analysis",
            inputs=["ci_data", "architecture_json_path", "validation_result"],
            outputs=["architecture_json_path", "validation_result"],
            dependencies=["QualityCheckAgent"],
        )
    
    def __init__(self):
        super().__init__()
    
    def run(self, state: CICDState) -> CICDState:
        """执行架构验证和补充"""
        ci_data = state.get("ci_data", {})
        architecture_path = state.get("architecture_json_path")
        
        if not architecture_path or not ci_data:
            return state
        
        architecture = self._load_architecture(architecture_path)
        if not architecture:
            return state
        
        print("\n[Architecture Validation] 验证并补充架构数据...")
        
        # 1. 修正触发入口层
        architecture = self._fix_trigger_layer(architecture, ci_data)
        
        # 2. 获取验证结果
        validation_result = state.get("validation_result", {})
        
        # 3. 如果架构不完整，补充遗漏的工作流
        if not validation_result.get("is_complete", True):
            missing_workflows = validation_result.get("missing_workflows", [])
            missing_triggers = validation_result.get("missing_trigger_types", [])
            
            if missing_workflows:
                print(f"  [WARN] 遗漏工作流: {len(missing_workflows)} 个")
                architecture = self._supplement_workflows(architecture, ci_data, missing_workflows)
            
            if missing_triggers:
                print(f"  [WARN] 遗漏触发类型: {missing_triggers}")
        
        # 4. 保存更新后的架构
        self._save_architecture(architecture_path, architecture)
        
        return {**state, "architecture_json": architecture}
    
    def _load_architecture(self, path: str) -> Optional[Dict]:
        """加载架构JSON"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    
    def _save_architecture(self, path: str, architecture: Dict):
        """保存架构JSON"""
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(architecture, f, ensure_ascii=False, indent=2)
            print(f"  [OK] 架构已保存")
        except Exception as e:
            print(f"  [ERROR] 保存架构失败: {e}")
    
    def _fix_trigger_layer(self, architecture: Dict, ci_data: Dict) -> Dict:
        """根据ci_data修正触发入口层"""
        trigger_counts = {}
        for wf_name, wf in ci_data.get("workflows", {}).items():
            for trigger in wf.get("triggers", []):
                if trigger not in trigger_counts:
                    trigger_counts[trigger] = 0
                trigger_counts[trigger] += 1
        
        trigger_layer = None
        trigger_layer_index = -1
        for i, layer in enumerate(architecture.get("layers", [])):
            if "触发" in layer.get("name", "") or "入口" in layer.get("name", ""):
                trigger_layer = layer
                trigger_layer_index = i
                break
        
        if trigger_layer is None:
            trigger_layer = {
                "id": "layer-trigger",
                "name": "触发条件",
                "nodes": []
            }
            architecture.setdefault("layers", [])
            architecture["layers"].insert(0, trigger_layer)
            trigger_layer_index = 0
        
        trigger_layer["nodes"] = []
        for trigger, count in sorted(trigger_counts.items()):
            node_id = f"node-trigger-{trigger}"
            label = f"{trigger}"
            if count > 1:
                label = f"{trigger} ({count})"
            
            description = self._get_trigger_description(trigger, count)
            
            trigger_layer["nodes"].append({
                "id": node_id,
                "label": label,
                "description": description,
                "detail_section": "阶段一：触发入口"
            })
        
        return architecture
    
    def _get_trigger_description(self, trigger: str, count: int) -> str:
        """获取触发类型描述"""
        descriptions = {
            "push": "代码推送触发",
            "pull_request": "Pull Request 事件触发",
            "pull_request_target": "PR 目标分支事件触发",
            "pull_request_review_comment": "PR 审查评论触发",
            "schedule": "定时任务触发",
            "workflow_dispatch": "手动触发",
            "workflow_call": "工作流调用触发",
            "issues": "Issue 事件触发",
            "issue_comment": "Issue 评论触发",
            "create": "分支/标签创建触发",
            "delete": "分支/标签删除触发",
            "repository_dispatch": "仓库派发触发",
        }
        base = descriptions.get(trigger, f"{trigger} 事件触发")
        if count > 1:
            return f"{base}，{count} 个工作流使用"
        return base
    
    def _supplement_workflows(
        self,
        architecture: Dict,
        ci_data: Dict,
        missing_workflows: List[str]
    ) -> Dict:
        """补充遗漏的工作流"""
        layers = architecture.get("layers", [])
        
        all_existing_workflows = set()
        for layer in layers:
            for node in layer.get("nodes", []):
                label = node.get("label", "")
                if label.endswith(".yml"):
                    all_existing_workflows.add(label)
        
        truly_missing = [wf for wf in missing_workflows if wf not in all_existing_workflows]
        
        if not truly_missing:
            print("  [INFO] 所有遗漏的工作流已存在于架构中，跳过补充")
            return architecture
        
        supplement_layer = None
        for layer in reversed(layers):
            layer_name = layer.get("name", "").lower()
            if "辅助" in layer_name or "其他" in layer_name or "工作流" in layer_name:
                supplement_layer = layer
                break
        
        if supplement_layer is None and layers:
            supplement_layer = layers[-1]
        
        if supplement_layer is None:
            supplement_layer = {
                "id": "layer-auxiliary",
                "name": "辅助工作流",
                "nodes": []
            }
            architecture.setdefault("layers", [])
            architecture["layers"].append(supplement_layer)
        
        workflows = ci_data.get("workflows", {})
        existing_labels = {node.get("label") for node in supplement_layer.get("nodes", [])}
        
        for wf_name in truly_missing:
            if wf_name in existing_labels:
                continue
            
            wf = workflows.get(wf_name, {})
            triggers = wf.get("triggers", [])
            trigger_str = ", ".join(triggers) if triggers else "其他"
            
            node = {
                "id": f"node-{wf_name}",
                "label": wf_name,
                "description": f"辅助工作流，触发类型: {trigger_str}",
                "detail_section": "阶段五：辅助工作流"
            }
            supplement_layer.setdefault("nodes", []).append(node)
            print(f"  补充工作流: {wf_name}")
        
        return architecture
    
    def validate_architecture_completeness(
        self,
        ci_data: Dict,
        architecture: Dict
    ) -> Dict:
        """验证架构完整性"""
        result = {
            "is_complete": True,
            "missing_workflows": [],
            "trigger_types_in_ci": set(),
            "trigger_types_in_arch": set(),
            "missing_trigger_types": set(),
            "layer_workflow_count": 0,
            "ci_workflow_count": 0,
        }
        
        workflows = ci_data.get("workflows", {})
        result["ci_workflow_count"] = len(workflows)
        ci_workflow_names = set(workflows.keys())
        
        for wf in workflows.values():
            for trigger in wf.get("triggers", []):
                result["trigger_types_in_ci"].add(trigger)
        
        layers = architecture.get("layers", [])
        for layer in layers:
            nodes = layer.get("nodes", [])
            layer_name = layer.get("name", "")
            
            if "触发" in layer_name:
                for node in nodes:
                    label = node.get("label", "")
                    if "事件" in label or "dispatch" in label:
                        trigger_name = label.replace(" 事件", "").replace("dispatch", "workflow_dispatch")
                        result["trigger_types_in_arch"].add(trigger_name)
            else:
                for node in nodes:
                    label = node.get("label", "")
                    if label.endswith(".yml"):
                        result["layer_workflow_count"] += 1
        
        arch_workflow_labels = set()
        for layer in layers:
            for node in layer.get("nodes", []):
                label = node.get("label", "")
                if label.endswith(".yml"):
                    arch_workflow_labels.add(label)
        
        result["missing_workflows"] = sorted(list(ci_workflow_names - arch_workflow_labels))
        result["missing_trigger_types"] = result["trigger_types_in_ci"] - result["trigger_types_in_arch"]
        
        result["is_complete"] = (
            len(result["missing_workflows"]) == 0 and
            len(result["missing_trigger_types"]) == 0
        )
        
        return result
