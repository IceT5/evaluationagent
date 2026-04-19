"""LLM 调用 Agent - 执行 LLM 分析"""
import re
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

try:
    from evaluator.llm import LLMClient
    HAS_LLM = True
except ImportError:
    HAS_LLM = False
    LLMClient = None

try:
    from evaluator.config import config
    HAS_CONFIG = True
except ImportError:
    HAS_CONFIG = False
    config = None

from evaluator.utils import parallel_execute
from evaluator.state import EvaluatorState
from evaluator.agents.base_agent import BaseAgent, AgentMeta

# 导入中断控制器
try:
    from evaluator.core.interrupt import interrupt_controller, InterruptException
    HAS_INTERRUPT = True
except ImportError:
    interrupt_controller = None
    InterruptException = Exception
    HAS_INTERRUPT = False


def _get_concurrent_calls() -> int:
    return config.max_concurrent_llm_calls if config and HAS_CONFIG else 4

def _get_llm_timeout() -> int:
    return config.llm_call_timeout if config and HAS_CONFIG else 600


def validate_round_response(round_num: int, response: str) -> dict:
    """验证单轮响应
    
    复用 ReviewerAgent.validate_llm_response 的部分逻辑
    """
    result = {"valid": True, "warnings": []}
    
    if not response or len(response.strip()) < 20:
        result["valid"] = False
        result["warnings"].append(f"Round {round_num}: 响应过短 ({len(response) if response else 0} 字符)")
        return result
    
    expected_markers = {
        0: ["项目概述", "##"],
        1: ["阶段划分", "##"],
        2: ["ARCHITECTURE_JSON", "<!--"],
        3: ["架构图", "┌", "│"],
        4: ["附录", "├", "│"],
        5: ["scores", "{"],
    }
    
    markers = expected_markers.get(round_num, [])
    found = [m for m in markers if m in response]
    
    if markers and len(found) < len(markers) // 2:
        result["warnings"].append(f"Round {round_num}: 缺少预期标记 {set(markers) - set(found)}")
    
    return result


def parse_multi_round_responses(responses: List[str]) -> dict:
    """从多轮响应中直接提取结构化数据
    
    Args:
        responses: 所有轮次的响应
    
    Returns:
        {
            "overview": str,
            "stage_division": str,
            "architecture_diagram": str,
            "scores": dict,
            "strengths": list,
            "weaknesses": list,
            "recommendations": list,
            "call_tree": str,
            "architecture_json": dict,
            "merged_response": str,
            "key_configs": list
        }
    """
    import json
    import re
    
    result = {
        "overview": "",
        "stage_division": "",
        "architecture_diagram": "",
        "scores": {},
        "strengths": [],
        "weaknesses": [],
        "recommendations": [],
        "call_tree": "",
        "architecture_json": {},
        "merged_response": "",
        "parse_warnings": [],
        "key_configs": [],
    }
    
    for i, resp in enumerate(responses):
        resp = resp.strip()
        round_num = i
        
        validation = validate_round_response(round_num, resp)
        if validation["warnings"]:
            result["parse_warnings"].extend(validation["warnings"])
            for w in validation["warnings"]:
                print(f"  [WARN] {w}")
        
        print(f"  [Parse] Round {i}: {len(resp)} 字符")
        
        if round_num == 0:
            # Round 0: 项目概述
            result["overview"] = resp
        
        elif round_num == 1:
            # Round 1: 阶段划分
            result["stage_division"] = resp
        
        elif round_num == 2:
            # Round 2: JSON架构
            result["architecture_json"] = extract_architecture_json(resp)
        
        elif round_num == 3:
            # Round 3: 架构图
            result["architecture_diagram"] = resp
        
        elif round_num == 4:
            # Round 4: 调用关系树
            result["call_tree"] = resp
        
        elif round_num == 5:
            # Round 5: 合并JSON输出
            data = extract_json_from_response(resp, round_num)
            result["scores"] = data.get("scores", {})
            result["strengths"] = data.get("strengths", [])
            result["weaknesses"] = data.get("weaknesses", [])
            result["recommendations"] = data.get("recommendations", [])
            
            if not result["scores"]:
                result["parse_warnings"].append(f"Round {i}: scores 提取失败")
    
    required = ["overview", "stage_division"]
    for field in required:
        if not result.get(field):
            result["parse_warnings"].append(f"必要字段 '{field}' 为空")
            print(f"  [ERROR] 必要字段 '{field}' 为空")
    
    result["merged_response"] = merge_to_markdown(result)
    
    return result


def build_batch_input_context(
    ci_data: Dict[str, Any],
    parsed_main_data: Dict[str, Any],
    key_configs: List[dict],
    global_context: str,
    batch_files: List[str],
) -> Dict[str, Any]:
    """构建多轮到分批之间的显式输入契约。"""
    architecture_json = parsed_main_data.get("architecture_json") or {}
    required_artifacts = {
        "overview": parsed_main_data.get("overview") or "",
        "stage_division": parsed_main_data.get("stage_division") or "",
        "architecture_json": architecture_json,
        "key_configs": key_configs,
    }

    diagnostics = []
    missing_fields = []
    if not required_artifacts["overview"]:
        missing_fields.append("overview")
    if not required_artifacts["stage_division"]:
        missing_fields.append("stage_division")
    if not architecture_json:
        missing_fields.append("architecture_json")

    if missing_fields:
        diagnostics.append(f"缺少分批依赖的多轮产物字段: {', '.join(missing_fields)}")

    workflow_names = list((ci_data or {}).get("workflows", {}).keys())
    return {
        "context_status": "ready" if not missing_fields else "incomplete",
        "schema_version": "v1",
        "source": "multi_round_contract",
        "global_context": global_context or "",
        "analysis_scope": {
            "workflow_names": workflow_names,
            "batch_file_count": len(batch_files),
        },
        "constraints": {
            "allow_implicit_conversation_state": False,
            "batch_inputs_must_come_from_state": True,
        },
        "input_artifacts": required_artifacts,
        "retry_context": {},
        "diagnostics": diagnostics,
    }


def build_stage_mapping_data(
    ci_data: Dict[str, Any],
    parsed_main_data: Dict[str, Any],
    architecture_json: Dict[str, Any],
) -> Dict[str, Any]:
    """从 multi-round 和 architecture_json 构建权威阶段映射。"""
    workflows = list((ci_data or {}).get("workflows", {}).keys())
    layers = (architecture_json or {}).get("layers", [])
    stages = []
    workflow_to_stage: Dict[str, str] = {}

    for idx, layer in enumerate(layers, start=1):
        stage_id = layer.get("id") or f"stage_{idx}"
        stage_name = layer.get("name") or f"阶段{idx}"
        workflow_ids = []
        for node in layer.get("nodes", []):
            label = node.get("label", "")
            if label.endswith(".yml") and label in workflows:
                workflow_ids.append(label)
                workflow_to_stage[label] = stage_id
        stage_description = ""
        for stage_line in parsed_main_data.get("stage_division", "").splitlines():
            if stage_name in stage_line or stage_name.replace("层", "") in stage_line:
                stage_description = stage_line.strip()
                break

        stages.append(
            {
                "stage_id": stage_id,
                "stage_name": stage_name,
                "workflow_ids": workflow_ids,
                "description": stage_description,
            }
        )

    unassigned = [wf for wf in workflows if wf not in workflow_to_stage]
    if unassigned:
        stages.append({
            "stage_id": "unassigned",
            "stage_name": "其他",
            "workflow_ids": unassigned,
            "description": "未在架构图中明确分类的工作流",
        })
        for wf in unassigned:
            workflow_to_stage[wf] = "unassigned"

    return {
        "schema_version": "v1",
        "authoritative_source": "multi_round",
        "stage_division_markdown": parsed_main_data.get("stage_division", ""),
        "stages": stages,
        "workflow_to_stage": workflow_to_stage,
        "workflow_ids": workflows,
        "unassigned_workflows": unassigned,
    }


def _extract_batch_workflow_details(response: str) -> Dict[str, Dict[str, Any]]:
    """从 batch markdown 中提取 workflow 详情。"""
    workflow_details: Dict[str, Dict[str, Any]] = {}

    heading_pattern = re.compile(
        r'^(?P<level>##|###|####)\s+(?:(?P<numbering>\d+(?:\.\d+)*)\.?\s+)?(?P<wf_name>[\w.-]+\.ya?ml)\s*$',
        re.MULTILINE,
    )
    matches = list(heading_pattern.finditer(response))

    for idx, match in enumerate(matches):
        header = match.group(0).strip()
        numbering = (match.group("numbering") or "").strip()
        wf_name = (match.group("wf_name") or "").strip()
        body_start = match.end()
        body_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(response)
        body = response[body_start:body_end].strip()

        # 截断 body 中混入的非 workflow 章节（脚本索引、批次总结等）
        # 这些章节属于 script_analysis_data，不应出现在 detail_markdown 里
        for _section_marker in (
            '\n## 脚本目录索引',
            '\n## 脚本和 Action 索引',
            '\n## 本批次',
            '\n## 工作流调用关系总结',
        ):
            _pos = body.find(_section_marker)
            if _pos != -1:
                body = body[:_pos].strip()
                break

        if wf_name not in workflow_details:
            # 用 level + wf_name 重建 header，去掉 LLM 自动生成的编号前缀
            level = match.group("level")
            clean_header = f"{level} {wf_name}"
            detail_markdown = f"{clean_header}\n\n{body}".strip()
            workflow_details[wf_name] = {
                "workflow_id": wf_name,
                "header": clean_header,
                "numbering": numbering,
                "detail_markdown": detail_markdown,
                "observed_stage": _extract_observed_stage_from_detail(body),
            }
    return workflow_details


def _extract_observed_stage_from_detail(content: str) -> str:
    match = re.search(r'^##\s+([^\n]+)$', content, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _extract_script_analysis_data(response: str) -> Dict[str, Any]:
    """从脚本分析 batch 中提取脚本目录索引与关键配置。"""
    scripts_section_match = re.search(
        r'##\s+脚本目录索引\s*\n([\s\S]*?)(?=\n##\s+|\Z)',
        response,
    )
    scripts_section = scripts_section_match.group(0).strip() if scripts_section_match else ""

    key_config_match = re.search(
        r'###\s+关键配置\s*\n([\s\S]*?)(?=\n###\s+|\n##\s+|\Z)',
        response,
    )
    key_config_markdown = key_config_match.group(0).strip() if key_config_match else ""
    key_config_entries = _extract_key_configs_from_response(response)

    # 提取 ## 关键配置详细分析，分离主表格（### 之前）和子节（### 开始）
    key_config_detailed_match = re.search(
        r'##\s+关键配置详细分析\s*\n([\s\S]*?)(?=\n##\s+|\Z)',
        response,
    )
    main_table_header = ""
    main_table_rows = []
    subsections = ""
    if key_config_detailed_match:
        body = key_config_detailed_match.group(1)
        # 在第一个 ### 处分割
        subsection_split = re.search(r'^###\s+', body, re.MULTILINE)
        if subsection_split:
            main_part = body[:subsection_split.start()]
            subsections = body[subsection_split.start():].rstrip()
        else:
            main_part = body
            subsections = ""
        # 从主表格部分提取表头和数据行（丢弃描述文字）
        for line in main_part.splitlines():
            stripped = line.strip()
            if not stripped.startswith('|'):
                continue
            if re.match(r'^\|\s*[-:]+', stripped):
                continue  # 分隔行
            if not main_table_header:
                main_table_header = stripped
            else:
                main_table_rows.append(stripped)

    return {
        "scripts_section_markdown": scripts_section,
        "key_config_markdown": key_config_markdown,
        "key_config_main_table_header": main_table_header,
        "key_config_main_table_rows": main_table_rows,
        "key_config_subsections": subsections,
        "key_config_entries": key_config_entries,
        "raw_response": response,
    }


def _is_script_batch(prompt_path: str, batch_meta: Dict[str, Any]) -> bool:
    batch_type = batch_meta.get("batch_type")
    if batch_type:
        return batch_type == "script_detail"
    lowered = (prompt_path or "").lower()
    return "script_analysis" in lowered or "prompt_script_" in lowered


def _merge_key_configs_from_responses(responses: List[str]) -> List[dict]:
    """合并多个响应中的关键配置信息
    
    用于：
    - Batch N+1 分批（脚本分析）
    
    Args:
        responses: LLM响应列表
    
    Returns:
        合并后的关键配置列表
    """
    import re
    
    all_key_configs = []
    seen = set()
    
    for response in responses:
        key_configs = _extract_key_configs_from_response(response)
        for config in key_configs:
            config_name = config.get("name", "")
            if config_name and config_name not in seen:
                seen.add(config_name)
                all_key_configs.append(config)
    
    return all_key_configs


def _extract_key_configs_from_response(response: str) -> List[dict]:
    """从 LLM 响应中提取关键配置信息
    
    Args:
        response: LLM 响应
    
    Returns:
        关键配置列表
    """
    import re
    
    key_configs = []
    
    # 尝试提取 "关键配置" 小节
    match = re.search(
        r'###\s+关键配置\s*\n(.*?)(?=###|##|$)',
        response,
        re.DOTALL
    )
    
    if match:
        content = match.group(1)
        # 提取表格行
        table_matches = re.findall(r'\|\s*`?([^`|\n]+)`?\s*\|\s*([^|\n]+)\s*\|\s*([^|\n]+)\s*\|', content)
        for name, desc, scale in table_matches:
            name = name.strip()
            if name and name != "配置文件":
                key_configs.append({
                    "name": name,
                    "description": desc.strip(),
                    "scale": scale.strip(),
                })
    
    return key_configs


def extract_json_from_response(response: str, round_num: int) -> dict:
    """从响应中提取 JSON（健壮版）"""
    import json
    import re
    
    match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError as e:
            print(f"  [WARN] Round {round_num}: JSON 解析失败 (```json): {e}")
    
    start = response.find('{')
    end = response.rfind('}')
    if start != -1 and end != -1:
        try:
            return json.loads(response[start:end+1])
        except json.JSONDecodeError as e:
            print(f"  [WARN] Round {round_num}: JSON 解析失败 ({{...}}): {e}")
    
    result = extract_from_markdown_table(response, round_num)
    if result:
        print(f"  [INFO] Round {round_num}: 使用 Markdown 表格回退")
        return result
    
    print(f"  [WARN] Round {round_num}: 无法提取数据，使用默认值")
    return {}


def extract_from_markdown_table(response: str, round_num: int) -> dict:
    """回退：从 Markdown 表格或列表提取数据"""
    import re
    
    if round_num == 4:
        pattern = r'\|\s*(\w+)\s*\|\s*(\d+)\s*\|'
        matches = re.findall(pattern, response)
        if matches:
            scores = {}
            for dimension, score in matches:
                if dimension in ["architecture_design", "best_practices", "security", "maintainability", "scalability"]:
                    scores[dimension] = {"score": int(score), "rationale": ""}
            if scores:
                return {"scores": scores}
    
    elif round_num == 5:
        strengths = []
        pattern = r'####\s*✅\s*模式[_\s]*\d*[:：]\s*(.+?)\n\n([\s\S]*?)(?=####\s*✅|####\s*⚠️|##|$)'
        matches = re.findall(pattern, response)
        for title, desc in matches:
            if title.strip():
                strengths.append({
                    "title": title.strip(),
                    "description": desc.strip()[:200],
                    "evidence": ""
                })
        if not strengths:
            pattern2 = r'####\s*✅\s*(.+?)\n([\s\S]*?)(?=####|$)'
            matches2 = re.findall(pattern2, response)
            for title, desc in matches2:
                if title.strip():
                    strengths.append({
                        "title": title.strip(),
                        "description": desc.strip()[:200],
                        "evidence": ""
                    })
        if strengths:
            return {"strengths": strengths}
    
    elif round_num == 6:
        weaknesses = []
        pattern = r'####\s*⚠️\s*(问题|反模式)[_\s]*\d*[:：]\s*(.+?)\n\n([\s\S]*?)(?=####\s*⚠️|####\s*建议|##|$)'
        matches = re.findall(pattern, response)
        for ptype, title, desc in matches:
            if title.strip():
                weaknesses.append({
                    "title": title.strip(),
                    "description": desc.strip()[:200],
                    "impact": "",
                    "suggestion": ""
                })
        if not weaknesses:
            pattern2 = r'####\s*⚠️\s*(.+?)\n([\s\S]*?)(?=####|$)'
            matches2 = re.findall(pattern2, response)
            for title, desc in matches2:
                if title.strip():
                    weaknesses.append({
                        "title": title.strip(),
                        "description": desc.strip()[:200],
                        "impact": "",
                        "suggestion": ""
                    })
        if weaknesses:
            return {"weaknesses": weaknesses}
    
    elif round_num == 7:
        recommendations = []
        pattern = r'\|\s*(P\d|high|medium|low|🔴|🟡|🟢)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|'
        matches = re.findall(pattern, response)
        priority_map = {"P0": "high", "P1": "medium", "P2": "low", "🔴": "high", "🟡": "medium", "🟢": "low"}
        for priority, content, benefit in matches:
            content = content.strip()
            benefit = benefit.strip()
            if content and content != "建议":
                recommendations.append({
                    "priority": priority_map.get(priority, priority.lower()),
                    "content": content,
                    "expected_benefit": benefit
                })
        if recommendations:
            return {"recommendations": recommendations}
    
    return {}


def extract_architecture_json(response: str) -> dict:
    """从响应中提取 ARCHITECTURE_JSON"""
    import json
    import re
    
    match = re.search(r'<!--\s*ARCHITECTURE_JSON\s*([\s\S]*?)\s*ARCHITECTURE_JSON\s*-->', response)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    
    return {}


def merge_to_markdown(data: dict) -> str:
    """将结构化数据合并为 Markdown"""
    import json
    
    parts = []
    
    if data["overview"]:
        parts.append(data["overview"])
    
    if data["stage_division"]:
        parts.append(data["stage_division"])
    
    if data["architecture_diagram"]:
        parts.append(data["architecture_diagram"])
    
    findings_parts = ["## 关键发现和建议"]
    
    if data["scores"]:
        findings_parts.append("\n### 架构特点总结\n")
        findings_parts.append(_format_scores_table(data["scores"]))
    
    if data["strengths"]:
        findings_parts.append("\n### 优势架构模式\n")
        findings_parts.append(_format_strengths(data["strengths"]))
    
    if data["weaknesses"]:
        findings_parts.append("\n### 架构问题\n")
        findings_parts.append(_format_weaknesses(data["weaknesses"]))
    
    if data["recommendations"]:
        findings_parts.append("\n### 改进建议\n")
        findings_parts.append(_format_recommendations(data["recommendations"]))
    
    parts.append("\n".join(findings_parts))
    
    if data["call_tree"]:
        parts.append(data["call_tree"])
    
    if data["architecture_json"]:
        parts.append("<!-- ARCHITECTURE_JSON\n" + json.dumps(data["architecture_json"], ensure_ascii=False, indent=2) + "\nARCHITECTURE_JSON -->")
    
    return "\n\n---\n\n".join(parts)


def _format_scores_table(scores: dict) -> str:
    """将 scores 格式化为 Markdown 表格"""
    lines = []
    lines.append("| 维度 | 评分 | 说明 |")
    lines.append("|------|------|------|")
    for dim, info in scores.items():
        score = info.get("score", "-")
        rationale = info.get("rationale", "")
        dim_cn = {
            "architecture_design": "架构设计",
            "best_practices": "最佳实践",
            "security": "安全性",
            "maintainability": "可维护性",
            "scalability": "可扩展性"
        }.get(dim, dim)
        lines.append(f"| {dim_cn} | {score} | {rationale} |")
    return "\n".join(lines)


def _format_strengths(strengths: list) -> str:
    """将 strengths 格式化为 Markdown"""
    lines = []
    for i, s in enumerate(strengths, 1):
        title = s.get("title", "")
        desc = s.get("description", "")
        lines.append(f"#### ✅ 模式 {i}: {title}")
        lines.append(desc)
        lines.append("")
    return "\n".join(lines)


def _format_weaknesses(weaknesses: list) -> str:
    """将 weaknesses 格式化为 Markdown"""
    lines = []
    for i, w in enumerate(weaknesses, 1):
        title = w.get("title", "")
        desc = w.get("description", "")
        suggestion = w.get("suggestion", "")
        lines.append(f"#### ⚠️ 问题 {i}: {title}")
        lines.append(desc)
        if suggestion:
            lines.append(f"**建议**: {suggestion}")
        lines.append("")
    return "\n".join(lines)


def _format_recommendations(recommendations: list) -> str:
    """将 recommendations 格式化为 Markdown"""
    lines = []
    lines.append("| 优先级 | 建议 | 预期效果 |")
    lines.append("|--------|------|----------|")
    priority_map = {"high": "🔴 高", "medium": "🟡 中", "low": "🟢 低"}
    for r in recommendations:
        priority = priority_map.get(r.get("priority", ""), r.get("priority", ""))
        content = r.get("content", "")
        benefit = r.get("expected_benefit", "")
        lines.append(f"| {priority} | {content} | {benefit} |")
    return "\n".join(lines)

def _get_llm_max_retries() -> int:
    return config.llm_max_retries if config and HAS_CONFIG else 5

def _get_retry_delay() -> float:
    return config.llm_retry_base_delay if config and HAS_CONFIG else 1.0


class LLMInvocationAgent(BaseAgent):
    """LLM 调用 Agent
    
    职责：根据策略执行 LLM 调用（单次/并发）
    输入：EvaluatorState.prompts, strategy
    输出：EvaluatorState.llm_responses
    """
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="LLMInvocationAgent",
            description="执行 LLM 调用进行分析",
            category="analysis",
            inputs=["prompts", "strategy", "ci_data"],
            outputs=["llm_responses"],
            dependencies=["AnalysisPlanningAgent"],
        )
    
    def __init__(self, llm: Optional[Any] = None):
        super().__init__()
        self.llm = llm
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行 LLM 调用"""
        strategy = state.get("strategy")
        prompts = state.get("prompts", [])
        ci_data = state.get("ci_data") or {}
        storage_dir = state.get("storage_dir")
        prompt_strategy = state.get("prompt_strategy") or ""
        batch_files = state.get("batch_files", [])
        batch_inputs = state.get("batch_inputs", [])
        cicd_global_context = state.get("cicd_global_context") or ""
        
        if strategy == "skip":
            return {
            **state,
            "llm_responses": [],
            "merged_response": "",
            "key_configs": [],
            "cicd_rounds_data": {
                "schema_version": "v1",
                "rounds": [],
                "diagnostics": [],
            },
            "cicd_batch_outputs_data": {
                "schema_version": "v1",
                "batches": [],
                "diagnostics": [],
            },
            "batch_input_context": {
                "context_status": "incomplete",
                "schema_version": "v1",
                "source": "multi_round_contract",
                "global_context": "",
                "analysis_scope": {"workflow_names": [], "batch_file_count": 0},
                "constraints": {
                    "allow_implicit_conversation_state": False,
                    "batch_inputs_must_come_from_state": True,
                },
                "input_artifacts": {},
                "retry_context": {},
                "diagnostics": ["分析策略为 skip，未生成多轮与分批输入契约"],
            },
            "workflow_details_data": {
                "schema_version": "v1",
                "workflow_entries": {},
                "diagnostics": [],
            },
            "script_analysis_data": {
                "schema_version": "v1",
                "scripts_present": False,
                "scripts_section_markdown": "## 脚本目录索引\n\n未检测到独立脚本文件。\n",
                "key_config_markdown": "### 关键配置\n\n未识别到关键配置。\n",
                "key_config_entries": [],
                "diagnostics": [],
            },
        }
        
        if self.llm is None and HAS_LLM:
            from evaluator.llm import get_default_client
            self.llm = get_default_client()
        
        output_dir = Path(storage_dir) if storage_dir else Path(str(state.get("project_path", ".")))
        
        if prompt_strategy == "multi_round":
            responses = self._multi_round_call(state)
        else:
            responses = self._parallel_calls(prompts)
        
        key_configs = self._extract_key_configs_from_responses(responses)
        
        merged_response = self._merge_responses(responses, ci_data, state.get("ci_data_path") or "")
        
        response_path = output_dir / "llm_response.md"
        response_path.write_text(merged_response, encoding="utf-8")
        
        main_multi_round = next((r for r in responses if r.get("prompt_path") == "main_multi_round"), {})
        parsed_main_data = main_multi_round.get("parsed_data", {}) if main_multi_round else {}
        round_responses = main_multi_round.get("round_responses", []) if main_multi_round else []
        round_durations = main_multi_round.get("round_durations", []) if main_multi_round else []

        cicd_rounds_data = {
            "schema_version": "v1",
            "rounds": [
                {
                    "round_id": f"round_{idx}",
                    "stage_type": stage_type,
                    "raw_response": response,
                    "parsed_artifacts": (
                        {"overview": parsed_main_data.get("overview")}
                        if idx == 0 else
                        {"stage_division": parsed_main_data.get("stage_division")}
                        if idx == 1 else
                        {"architecture_json": parsed_main_data.get("architecture_json")}
                        if idx == 2 else
                        {"architecture_diagram": parsed_main_data.get("architecture_diagram")}
                        if idx == 3 else
                        {"call_tree": parsed_main_data.get("call_tree")}
                        if idx == 4 else
                        {
                            "scores": parsed_main_data.get("scores", {}),
                            "strengths": parsed_main_data.get("strengths", []),
                            "weaknesses": parsed_main_data.get("weaknesses", []),
                            "recommendations": parsed_main_data.get("recommendations", []),
                        }
                    ),
                    "protocol_status": "ok" if response else "invalid",
                    "errors": [],
                    "duration": round_durations[idx] if idx < len(round_durations) else "",
                }
                for idx, (response, stage_type) in enumerate(
                    zip(
                        round_responses,
                        ["overview", "stage_division", "architecture_json", "architecture_diagram", "call_tree", "summary"],
                    )
                )
            ],
            "diagnostics": parsed_main_data.get("parse_warnings", []),
        }

        cicd_batch_outputs_data = {
            "schema_version": "v1",
            "batches": [
                {
                    "batch_id": f"batch_{idx}",
                    "prompt_path": response.get("prompt_path"),
                    "response": response.get("response", ""),
                    "success": response.get("success", False),
                    "error": response.get("error"),
                    "index": response.get("index", idx),
                    "batch_type": next((meta.get("batch_type") for meta in batch_inputs if meta.get("path") == response.get("prompt_path")), ""),
                }
                for idx, response in enumerate(
                    [r for r in responses if r.get("prompt_path") != "main_multi_round"],
                    start=1,
                )
            ],
            "diagnostics": [],
        }

        workflow_details_data = {
            "schema_version": "v1",
            "workflow_entries": {},
            "diagnostics": [],
        }
        script_analysis_data = {
            "schema_version": "v1",
            "scripts_present": False,
            "scripts_section_markdown": "",
            "key_config_markdown": "",
            "key_config_detailed_analysis": "",
            "key_config_table_groups": [],   # list of {"header": str, "rows": list[str]}
            "key_config_subsections_list": [],  # list of subsection blocks (str)
            "key_config_entries": [],
            "diagnostics": [],
        }

        for batch in cicd_batch_outputs_data["batches"]:
            prompt_path = batch.get("prompt_path", "")
            batch_response = batch.get("response", "")
            if not batch_response:
                continue
            if _is_script_batch(prompt_path, batch):
                extracted = _extract_script_analysis_data(batch_response)
                script_analysis_data["scripts_present"] = True
                if extracted.get("scripts_section_markdown"):
                    script_analysis_data["scripts_section_markdown"] = extracted["scripts_section_markdown"]
                if extracted.get("key_config_markdown"):
                    script_analysis_data["key_config_markdown"] = extracted["key_config_markdown"]
                if extracted.get("key_config_entries"):
                    script_analysis_data["key_config_entries"].extend(extracted["key_config_entries"])
                # 主表格：按表头分组合并
                header = extracted.get("key_config_main_table_header", "")
                rows = extracted.get("key_config_main_table_rows", [])
                if header and rows:
                    groups = script_analysis_data["key_config_table_groups"]
                    matched = next((g for g in groups if g["header"] == header), None)
                    if matched:
                        matched["rows"].extend(rows)
                    else:
                        groups.append({"header": header, "rows": list(rows)})
                # 子节：按顺序追加
                subsections = extracted.get("key_config_subsections", "")
                if subsections:
                    script_analysis_data["key_config_subsections_list"].append(subsections)
            else:
                workflow_details = _extract_batch_workflow_details(batch_response)
                workflow_details_data["workflow_entries"].update(workflow_details)

        if not script_analysis_data["scripts_section_markdown"]:
            script_analysis_data["scripts_section_markdown"] = "## 脚本目录索引\n\n未检测到独立脚本文件。\n"
        if not script_analysis_data["key_config_markdown"]:
            script_analysis_data["key_config_markdown"] = "### 关键配置\n\n未识别到关键配置。\n"

        # 重建 key_config_detailed_analysis：按表头分组的主表格 + 各批次子节
        detailed_parts = ["## 关键配置详细分析"]
        for group in script_analysis_data["key_config_table_groups"]:
            header = group["header"]
            rows = group["rows"]
            # 生成分隔行（与表头列数一致）
            col_count = header.count('|') - 1
            separator = '|' + '|'.join(['------'] * col_count) + '|'
            detailed_parts.append(header)
            detailed_parts.append(separator)
            detailed_parts.extend(rows)
            detailed_parts.append("")
        for subsection in script_analysis_data["key_config_subsections_list"]:
            detailed_parts.append(subsection)
            detailed_parts.append("")
        rebuilt = "\n".join(detailed_parts).strip()
        script_analysis_data["key_config_detailed_analysis"] = rebuilt if len(detailed_parts) > 1 else ""


        architecture_json = parsed_main_data.get("architecture_json") or {}
        cicd_stage_mapping_data = build_stage_mapping_data(
            ci_data=ci_data,
            parsed_main_data=parsed_main_data,
            architecture_json=architecture_json,
        )

        batch_input_context = build_batch_input_context(
            ci_data=ci_data,
            parsed_main_data=parsed_main_data,
            key_configs=key_configs,
            global_context=cicd_global_context,
            batch_files=[meta.get("path", "") for meta in batch_inputs] or batch_files,
        )

        return {
            **state,
            "llm_responses": responses,
            "merged_response": merged_response,
            "key_configs": key_configs,
            "retry_count": state.get("retry_count", 0),
            "cicd_rounds_data": cicd_rounds_data,
            "cicd_batch_outputs_data": cicd_batch_outputs_data,
            "batch_input_context": batch_input_context,
            "cicd_stage_mapping_data": cicd_stage_mapping_data,
            "workflow_details_data": workflow_details_data,
            "script_analysis_data": script_analysis_data,
        }
    
    def _extract_key_configs_from_responses(self, responses: List[Dict[str, Any]]) -> List[dict]:
        """从 LLM 响应中提取关键配置
        
        Args:
            responses: LLM 响应列表
        
        Returns:
            关键配置列表
        """
        # 1. 从main_multi_round响应中提取
        for r in responses:
            if r.get("success") and r.get("prompt_path") == "main_multi_round":
                parsed_data = r.get("parsed_data", {})
                key_configs = parsed_data.get("key_configs", [])
                if key_configs:
                    print(f"  [LLM] 提取关键配置: {len(key_configs)} 个")
                return key_configs
        
        # 2. 从脚本分析Batch响应中提取
        script_analysis_responses = [
            r.get("response", "") for r in responses 
            if r.get("success") and _is_script_batch(r.get("prompt_path", ""), r)
        ]
        
        if script_analysis_responses:
            key_configs = _merge_key_configs_from_responses(script_analysis_responses)
            print(f"  [LLM] 从脚本分析中提取关键配置: {len(key_configs)} 个")
            return key_configs
        
        return []
    
    def _multi_round_call(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """多轮对话调用
        
        执行步骤：
        1. 从 state 获取 main_rounds 和 main_system_prompt
        2. 并发执行：main 多轮对话 + batch prompts
        3. 返回合并的 responses
        """
        main_rounds = state.get("main_rounds", [])
        main_system_prompt = state.get("main_system_prompt", "")
        batch_files = state.get("batch_files", [])
        
        results = []
        
        if main_rounds:
            main_response = self._execute_multi_round(main_rounds, main_system_prompt)
            results.append(main_response)
            print(f"  [Multi-Round] main 分析完成")
        
        if batch_files:
            batch_responses = self._parallel_calls(batch_files)
            results.extend(batch_responses)
            print(f"  [LLM] batch 分析完成 ({len(batch_responses)} 个)")
        
        if not results:
            print(f"  [LLM] 警告：没有执行任何 LLM 调用")
        
        return results
    
    def _execute_multi_round(
        self,
        rounds: List[str],
        system_prompt: str = "",
    ) -> Dict[str, Any]:
        """执行多轮对话
        
        Args:
            rounds: 轮次 prompt 列表
            system_prompt: 系统提示
        """
        print(f"  [Multi-Round] 开始 {len(rounds)} 轮对话...")
        
        # 使用 get_stream_writer 输出进度（Studio 可接收）
        try:
            from langgraph.config import get_stream_writer
            writer = get_stream_writer()
        except (ImportError, RuntimeError):
            writer = None  # 非 LangGraph 执行环境，fallback 到 print
        
        # 检查中断
        if HAS_INTERRUPT and interrupt_controller and interrupt_controller.is_interrupted():
            raise InterruptException("用户中断")
        
        try:
            timeout = config.llm_call_timeout if config and HAS_CONFIG else 180
            if self.llm is None:
                raise RuntimeError("LLM 客户端未初始化")
            responses, durations = self.llm.chat_multi_round(
                rounds,
                system_prompt or None,
                timeout=timeout
            )
            
            parsed = parse_multi_round_responses(responses)
            
            print(f"  [Multi-Round] 完成")
            for i, (resp, dur) in enumerate(zip(responses, durations)):
                print(f"    Round {i}: {dur}, {len(resp)} 字符")
                if writer:
                    try:
                        writer({"step": "multi_round", "current": i+1, "total": len(responses)})
                    except Exception:
                        pass  # writer 写入失败不影响主流程
            
            return {
                "success": True,
                "prompt_path": "main_multi_round",
                "response": parsed["merged_response"],
                "parsed_data": parsed,
                "round_responses": responses,
                "round_durations": durations,
                "index": 0,
            }
        except InterruptException:
            raise  # 中断异常直接抛出
        except Exception as e:
            print(f"  [Multi-Round] 失败: {e}")
            return {
                "success": False,
                "prompt_path": "main_multi_round",
                "error": str(e),
                "index": 0,
            }
    
    def _parallel_calls(self, prompt_files: List[str]) -> List[Dict[str, Any]]:
        """并发 LLM 调用（使用统一并发工具）
        
        自动关联LangSmith trace，保留重试机制。
        """
        prompts = []
        skipped_files = []
        for pf in prompt_files:
            if pf.endswith('.txt') and not pf.endswith('README.txt') and 'main' not in pf:
                try:
                    with open(pf, 'r', encoding='utf-8') as f:
                        prompts.append({
                            'path': pf,
                            'content': f.read()
                        })
                except Exception as e:
                    print(f"  [LLM] 警告：无法读取文件 {pf}: {str(e)}")
                    skipped_files.append(pf)

        if skipped_files:
            print(f"  [LLM] 警告：跳过了 {len(skipped_files)} 个文件")

        if not prompts:
            return []
        
        print(f"  [LLM] 并发调用 {len(prompts)} 个 prompt...")
        
        # 使用 get_stream_writer 输出进度（Studio 可接收）
        try:
            from langgraph.config import get_stream_writer
            _writer = get_stream_writer()
        except (ImportError, RuntimeError):
            _writer = None
        
        # 创建任务列表（保留重试逻辑）
        def create_task(prompt_data: Dict[str, str], index: int, total: int):
            def task():
                return self._call_with_retry(
                    prompt_data['content'],
                    prompt_data['path'],
                    index,
                    total
                )
            return task
        
        tasks = [create_task(p, i+1, len(prompts)) for i, p in enumerate(prompts)]
        
        # 使用统一并发工具执行
        max_concurrent = _get_concurrent_calls()
        results = parallel_execute(tasks, max_concurrent=max_concurrent)
        
        # 输出 batch 完成进度
        if _writer:
            try:
                _writer({"step": "batch_llm", "total": len(prompts), "completed": len(results)})
            except Exception:
                pass  # writer 写入失败不影响主流程
        
        return results
    
    def _interruptible_sleep(self, seconds: float):
        """可中断的 sleep
        
        每秒检查一次中断状态，如果检测到中断则抛出 InterruptException。
        """
        if not HAS_INTERRUPT or not interrupt_controller:
            time.sleep(seconds)
            return
        
        end_time = time.time() + seconds
        while time.time() < end_time:
            if interrupt_controller.is_interrupted():
                raise InterruptException("用户中断")
            remaining = end_time - time.time()
            time.sleep(min(1.0, remaining))
    
    def _call_with_retry(
        self,
        prompt: str,
        prompt_path: str,
        index: int,
        total: int
    ) -> Dict[str, Any]:
        """带重试的 LLM 调用"""
        max_retries = _get_llm_max_retries()
        retry_delay_base = _get_retry_delay()
        
        for attempt in range(max_retries):
            # 检查中断
            if HAS_INTERRUPT and interrupt_controller and interrupt_controller.is_interrupted():
                raise InterruptException("用户中断")
            
            try:
                print(f"  [LLM-{index}/{total}] 处理 {Path(prompt_path).name}...")
                if self.llm is None:
                    raise RuntimeError("LLM 客户端未初始化")
                response = self.llm.chat(prompt)
                print(f"  [LLM-{index}/{total}] 完成 ({len(response)} 字符)")
                return {
                    'success': True,
                    'prompt_path': prompt_path,
                    'response': response,
                    'index': index
                }
            except InterruptException:
                raise  # 中断异常直接抛出
            except Exception as e:
                if attempt < max_retries - 1:
                    delay = retry_delay_base * 10 * (attempt + 1)
                    print(f"  [LLM-{index}/{total}] 失败，{delay}s 后重试 {attempt + 2}/{max_retries}...")
                    # 分段 sleep，每秒检查中断
                    self._interruptible_sleep(delay)
                else:
                    raise e
        
        return {'success': False, 'error': 'max retries exceeded'}
    
    def _merge_responses(
        self,
        responses: List[Dict[str, Any]],
        ci_data: dict,
        ci_data_path: str = ""
    ) -> str:
        """合并多个 LLM 响应
        
        注意: 此方法保留用于结果合并，但合并逻辑已移至 ResultMergingAgent。
        CICDOrchestrator 负责编排 ResultMergingAgent，不在此 Agent 内直接调用。
        """
        successful = [r for r in responses if r.get("success")]
        if not successful:
            print("  [ERROR] 所有 LLM 调用都失败")
            return ""
        
        print(f"  [Merge] 成功响应数: {len(successful)}")
        
        merged_parts = []
        for r in successful:
            response = r.get("response", "")
            if response:
                response = self._clean_trailing_headers(response)
                merged_parts.append(response)
                prompt_name = Path(r.get('prompt_path', 'unknown')).name
                print(f"    - {prompt_name}: {len(response)} 字符")
        
        result = "\n\n---\n\n".join(merged_parts)
        print(f"  [Merge] 合并后长度: {len(result)} 字符")
        
        return result
    
    def _clean_trailing_headers(self, content: str) -> str:
        """清理响应末尾的残留标题
        
        删除批次响应末尾的空标题：
        - ### 触发条件
        - - xxx
        - ### 工作流详情
        - （后面没有 #### 工作流标题）
        
        这些残留标题会在合并时与下一批次的开头拼接，导致触发条件与工作流不匹配。
        """
        import re
        
        pattern = r'### 触发条件\s*\n(?:-.*\n|\s*\n)*### 工作流详情\s*\n\s*$'
        cleaned = re.sub(pattern, '', content)
        
        if len(cleaned) != len(content):
            print(f"    [Clean] 清理了 {len(content) - len(cleaned)} 字符的残留标题")
        
        return cleaned
