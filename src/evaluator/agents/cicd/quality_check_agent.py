"""质量检查 Agent - 验证结构化产物质量"""
import re
import json
from pathlib import Path
from typing import Optional, Dict, Any

from evaluator.agents.base_agent import BaseAgent, AgentMeta


class QualityCheckAgent(BaseAgent):
    """质量检查 Agent
    
    职责：验证 merge 后结构化产物是否满足 pre-organize 继续执行条件。
    """
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="QualityCheckAgent",
            description="验证结构化产物质量",
            category="analysis",
            inputs=["batch_input_context", "cicd_assembled_data", "ci_data"],
            outputs=["validation_result", "architecture_json_path"],
            dependencies=["ResultMergingAgent"],
        )
    
    def __init__(self, llm=None):
        super().__init__()
        self.llm = llm
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行质量检查"""
        ci_data = state.get("ci_data") or {}
        storage_dir = state.get("storage_dir")
        batch_input_context = state.get("batch_input_context") or {}
        assembled_data = state.get("cicd_assembled_data") or {}
        
        output_dir = Path(storage_dir) if storage_dir else Path(str(state.get("project_path", ".")))
        
        architecture_json_path = str(output_dir / "architecture.json")

        contract_result = self._contract_check(batch_input_context)
        if contract_result["status"] != "passed":
            return {
                **state,
                "contract_check_result": contract_result,
                "validation_result": {
                    "status": "skipped",
                    "reason": "contract_check_failed",
                    "valid": False,
                    "issues": contract_result.get("issues", []),
                },
                "architecture_json": {"layers": [], "connections": []},
            }

        assembly_validation = self._validate_assembled_data(assembled_data)
        if not assembly_validation["valid"]:
            issues = assembly_validation.get("issues", [])
            needs_retry = assembly_validation.get("needs_retry", True)
            retry_reason = assembly_validation.get("retry_reason", "assembly 关键结构不完整")
            failure_scope = assembly_validation.get("failure_scope", "final_validation")
            print(f"  [Quality] assembly 校验失败: {'; '.join(issues)}")
            return {
                **state,
                "contract_check_result": contract_result,
                "validation_result": {
                    "status": "failed",
                    "valid": False,
                    "needs_retry": needs_retry,
                    "retry_reason": retry_reason,
                    "failure_scope": failure_scope,
                    "issues": issues,
                    "missing_workflows": [],
                    "missing_trigger_types": [],
                },
                "cicd_failure_data": {
                    "failure_type": "final_validation_failure",
                    "failure_scope": failure_scope,
                    "reason": retry_reason,
                },
                "architecture_json": {"layers": [], "connections": []},
            }

        architecture_data = assembled_data.get("artifacts", {}).get("architecture_json") or {}
        if not architecture_data:
            print("  [Quality] assembly 后缺少 architecture_json，进入最终校验失败")
            return {
                **state,
                "contract_check_result": contract_result,
                "validation_result": {
                    "status": "failed",
                    "valid": False,
                    "needs_retry": True,
                    "retry_reason": "assembly 后缺少 architecture_json",
                    "failure_scope": "final_validation",
                    "issues": ["assembly 后缺少 architecture_json"],
                    "missing_workflows": [],
                    "missing_trigger_types": [],
                },
                "cicd_failure_data": {
                    "failure_type": "final_validation_failure",
                    "failure_scope": "final_validation",
                    "reason": "assembly_missing_architecture_json",
                },
                "architecture_json": {"layers": [], "connections": []},
            }

        architecture_data = self._fix_trigger_layer(architecture_data, ci_data)
        architecture_data = self._supplement_connections(architecture_data, ci_data)
        
        validation = self._validate_architecture(ci_data, architecture_data)
        
        if not validation["is_complete"]:
            print(f"  [Quality] 架构不完整，补充遗漏...")
            architecture_data = self._supplement_architecture(
                architecture_data, ci_data, validation
            )
            validation = self._validate_architecture(ci_data, architecture_data)

        with open(architecture_json_path, "w", encoding="utf-8") as f:
            json.dump(architecture_data, f, ensure_ascii=False, indent=2)
        
        return {
            **state,
            "architecture_json": architecture_data,
            "contract_check_result": contract_result,
            "validation_result": {
                **validation,
                "status": "passed" if validation.get("is_complete") else "failed",
                "valid": validation.get("is_complete", False),
                "needs_retry": not validation.get("is_complete", False),
                "retry_reason": "最终结构化产物不完整" if not validation.get("is_complete", False) else "",
                "failure_scope": "final_validation" if not validation.get("is_complete", False) else "",
                "issues": self._build_validation_issues(validation),
            },
            "cicd_failure_data": {} if validation.get("is_complete") else {
                "failure_type": "final_validation_failure",
                "failure_scope": "final_validation",
                "reason": "incomplete_final_artifact",
            },
        }

    def _contract_check(self, batch_input_context: Dict[str, Any]) -> Dict[str, Any]:
        issues = []
        if not batch_input_context:
            issues.append("缺少 batch_input_context")
        if batch_input_context.get("context_status") != "ready":
            issues.extend(batch_input_context.get("diagnostics", []))
        constraints = batch_input_context.get("constraints", {})
        if constraints.get("allow_implicit_conversation_state", True):
            issues.append("batch_input_context 未禁止隐式会话上下文")
        if not batch_input_context.get("input_artifacts", {}).get("architecture_json"):
            issues.append("batch_input_context 缺少 architecture_json")

        return {
            "status": "passed" if not issues else "failed",
            "valid": not issues,
            "issues": issues,
            "failure_scope": "contract" if issues else "",
        }

    def _validate_assembled_data(self, assembled_data: Dict[str, Any]) -> Dict[str, Any]:
        issues = []
        if not assembled_data:
            issues.append("缺少 cicd_assembled_data")
            return {"valid": False, "issues": issues}

        assembly_status = assembled_data.get("assembly_status")
        missing_fields = set(assembled_data.get("missing_fields", []))

        blocking_fields = [field for field in ("architecture_json", "stage_division") if field in missing_fields]

        if assembly_status == "incomplete" and blocking_fields:
            issues.append(f"assembly 缺少关键字段: {', '.join(blocking_fields)}")

        # 检查 findings 数据是否全为空（Round 5 解析失败的典型症状）
        summary_input = assembled_data.get("artifacts", {}).get("summary_input_data", {})
        findings_empty = (
            not summary_input.get("scores")
            and not summary_input.get("strengths")
            and not summary_input.get("weaknesses")
            and not summary_input.get("recommendations")
        )
        if findings_empty:
            issues.append("summary_input_data 为空（Round 5 解析失败）")

        result = {
            "valid": not issues,
            "issues": issues,
        }

        # 当 findings 为空时，携带 retry 指令供 RetryHandlingAgent 使用
        if findings_empty:
            result.update({
                "needs_retry": True,
                "retry_reason": "findings_empty",
                "failure_scope": "multi_round_summary",
            })

        return result

    def _build_validation_issues(self, validation: Dict[str, Any]) -> list:
        issues = []
        for workflow in validation.get("missing_workflows", []):
            issues.append(f"缺少工作流: {workflow}")
        for trigger in validation.get("missing_trigger_types", []):
            issues.append(f"缺少触发器: {trigger}")
        return issues
    
    def _extract_architecture_json(self, content: str, output_path: str, ci_data: Dict) -> bool:
        """从响应中提取架构 JSON
        
        Returns:
            True: 成功提取
            False: 未找到ARCHITECTURE_JSON标记，需要重试
        """
        match = re.search(
            r'<!--\s*ARCHITECTURE_JSON\s*(.*?)\s*ARCHITECTURE_JSON\s*-->',
            content,
            re.DOTALL
        )
        
        if match:
            try:
                arch_data = json.loads(match.group(1).strip())
                arch_data = self._normalize_node_labels(arch_data, ci_data)
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(arch_data, f, ensure_ascii=False, indent=2)
                print("  [OK] ARCHITECTURE_JSON 提取成功")
                return True
            except json.JSONDecodeError as e:
                print(f"  [ERROR] ARCHITECTURE_JSON 解析失败: {e}")
                self._save_empty_architecture_json(output_path)
                return False
        
        # 未找到 ARCHITECTURE_JSON 标记
        print("  [ERROR] 未找到 ARCHITECTURE_JSON 标记")
        self._save_empty_architecture_json(output_path)
        return False
    
    def _extract_valid_triggers(self, ci_data: Dict) -> set:
        """从 ci_data 中提取项目实际使用的触发类型"""
        triggers = set()
        for wf_data in ci_data.get("workflows", {}).values():
            triggers.update(wf_data.get("triggers", []))
        return triggers
    
    def _normalize_node_labels(self, arch_data: Dict, ci_data: Dict) -> Dict:
        """统一节点标签格式：为工作流节点添加 .yml 后缀"""
        # 动态获取项目实际使用的触发类型
        valid_triggers = self._extract_valid_triggers(ci_data)
        
        for layer in arch_data.get("layers", []):
            for node in layer.get("nodes", []):
                label = node.get("label", "")
                if not label.endswith(".yml") and not label.endswith(".yaml"):
                    base_label = label.split(" (")[0].strip()
                    if base_label not in valid_triggers and "事件" not in label:
                        node["label"] = f"{label}.yml"
        
        return arch_data
    
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
        trigger_types = self._collect_trigger_types(ci_data)

        if not trigger_types:
            return architecture_data

        layers = architecture_data.get("layers", [])

        trigger_layer = None
        for layer in layers:
            if self._is_trigger_layer(layer):
                trigger_layer = layer
                break

        if trigger_layer is None:
            trigger_layer = {
                "id": "layer-trigger",
                "name": "触发入口",
                "nodes": [],
            }
            layers.insert(0, trigger_layer)

        nodes = trigger_layer.setdefault("nodes", [])

        # 清除误放入触发层的 workflow 节点（.yml 文件不应出现在触发层）
        nodes[:] = [n for n in nodes if not n.get("label", "").endswith((".yml", ".yaml"))]

        # 清除不在 ci_data 中的幻觉触发器节点
        nodes[:] = [
            n for n in nodes
            if self._normalize_trigger_label(n.get("label", "")) in trigger_types
        ]

        # existing_triggers 在两次清除之后计算
        existing_triggers = {
            self._normalize_trigger_label(n.get("label", ""))
            for n in nodes
        }

        for trigger_type in sorted(trigger_types):
            if trigger_type in existing_triggers:
                continue
            nodes.append({
                "id": self._build_trigger_node_id(trigger_type),
                "label": trigger_type,
                "description": f"触发器: {trigger_type}",
            })

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
        
        trigger_types = self._collect_trigger_types(ci_data)
        
        reported_triggers = set()
        for layer in architecture_data.get("layers", []):
            if self._is_trigger_layer(layer):
                for node in layer.get("nodes", []):
                    normalized = self._normalize_trigger_label(node.get("label", ""))
                    if normalized:
                        reported_triggers.add(normalized)
        
        missing_triggers = trigger_types - reported_triggers
        
        return {
            "is_complete": len(missing_workflows) == 0 and len(missing_triggers) == 0,
            "missing_workflows": list(missing_workflows),
            "missing_trigger_types": list(missing_triggers),
        }

    def _collect_trigger_types(self, ci_data: Dict) -> set[str]:
        return {
            trigger_type
            for wf_data in ci_data.get("workflows", {}).values()
            for trigger_type in wf_data.get("triggers", [])
            if trigger_type
        }

    def _is_trigger_layer(self, layer: Dict[str, Any]) -> bool:
        layer_name = layer.get("name", "")
        lowered = layer_name.lower()
        return "trigger" in lowered or "入口" in layer_name or "触发" in layer_name

    def _normalize_trigger_label(self, label: str) -> str:
        normalized = (label or "").strip()
        if not normalized:
            return ""
        if normalized.endswith(".yml"):
            return normalized[:-4]
        if normalized.endswith(".yaml"):
            return normalized[:-5]
        return normalized

    def _build_trigger_node_id(self, trigger_type: str) -> str:
        safe_trigger = re.sub(r"[^a-zA-Z0-9_-]", "-", trigger_type)
        return f"trigger-{safe_trigger}"
    
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
                # 找最后一个非触发层，避免把 workflow 补充进触发入口层
                for layer in reversed(layers):
                    if not self._is_trigger_layer(layer):
                        build_layer = layer
                        break
            if build_layer is None:
                # 所有层都是触发层（极端情况），新建一个兜底层
                build_layer = {"id": "layer-other", "name": "其他", "nodes": []}
                layers.append(build_layer)
            
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

    def _supplement_connections(
        self,
        architecture_data: Dict,
        ci_data: Optional[Dict]
    ) -> Dict:
        """用 ci_data 补全 connections

        补全两类连线：
        1. trigger→workflow：从 workflow 的 triggers 提取
        2. workflow→workflow：从 jobs.calls_workflows 提取
        """
        if not ci_data:
            return architecture_data

        # 1. 构建 node id → label 和 label → node id 映射
        node_id_to_label = {}
        label_to_node_id = {}
        for layer in architecture_data.get("layers", []):
            for node in layer.get("nodes", []):
                nid = node.get("id")
                label = node.get("label", "")
                if nid and label:
                    node_id_to_label[nid] = label
                    label_to_node_id[label] = nid

        # 2. 收集现有 connections（去重用）
        existing_connections = set()
        for conn in architecture_data.get("connections", []):
            src = conn.get("source")
            tgt = conn.get("target")
            if src and tgt:
                existing_connections.add((src, tgt))

        new_connections = []

        # 3. 补全 trigger→workflow 连线
        workflows = ci_data.get("workflows", {})
        for wf_name, wf_data in workflows.items():
            wf_node_id = label_to_node_id.get(wf_name)
            if not wf_node_id:
                continue

            triggers = wf_data.get("triggers", [])
            for trigger in triggers:
                trigger_node_id = f"trigger-{trigger}"
                if trigger_node_id in node_id_to_label:
                    if (trigger_node_id, wf_node_id) not in existing_connections:
                        new_connections.append({
                            "source": trigger_node_id,
                            "target": wf_node_id,
                            "type": "trigger"
                        })
                        existing_connections.add((trigger_node_id, wf_node_id))

        # 4. 补全 workflow→workflow 连线
        for caller_wf_name, wf_data in workflows.items():
            caller_node_id = label_to_node_id.get(caller_wf_name)
            if not caller_node_id:
                continue

            for job_name, job_data in wf_data.get("jobs", {}).items():
                calls_workflows = job_data.get("calls_workflows", [])
                for called_ref in calls_workflows:
                    # 归一化 workflow ref
                    called_wf_name = self._normalize_workflow_ref(called_ref)
                    called_node_id = label_to_node_id.get(called_wf_name)

                    if called_node_id and (caller_node_id, called_node_id) not in existing_connections:
                        new_connections.append({
                            "source": caller_node_id,
                            "target": called_node_id,
                            "type": "workflow_call"
                        })
                        existing_connections.add((caller_node_id, called_node_id))

        # 5. 合并到 architecture_data
        if new_connections:
            architecture_data.setdefault("connections", []).extend(new_connections)
            print(f"  [Connections] 补全了 {len(new_connections)} 条连线 (trigger: {sum(1 for c in new_connections if c.get('type') == 'trigger')}, workflow_call: {sum(1 for c in new_connections if c.get('type') == 'workflow_call')})")

        return architecture_data

    def _normalize_workflow_ref(self, ref: str) -> str:
        """归一化 workflow 引用为文件名

        Examples:
            ./.github/workflows/_linux-build.yml → _linux-build.yml
            pytorch/pytorch/.github/workflows/_runner-determinator.yml@main → _runner-determinator.yml
        """
        if not ref:
            return ""

        # 移除 @ref 后缀
        if "@" in ref:
            ref = ref.split("@")[0]

        # 提取文件名
        if "/" in ref:
            ref = ref.split("/")[-1]

        return ref

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
    
    def _validate_overview(self, overview: str, ci_data: Dict[str, Any]) -> Dict[str, Any]:
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
