# Core 对比函数

import time
from typing import List, Optional, Dict, Any

from storage import StorageManager
from .types import ComparisonResult

try:
    from ..llm.client import LLMClient, create_client
    HAS_LLM = True
except ImportError:
    HAS_LLM = False


def compare_projects(
    project_a: str,
    project_b: str,
    version_a: str = None,
    version_b: str = None,
    dimensions: List[str] = None,
    llm_config: Dict[str, Any] = None,
) -> ComparisonResult:
    """
    对比两个项目
    
    Args:
        project_a: 项目 A 名称
        project_b: 项目 B 名称
        version_a: 项目 A 版本（默认最新）
        version_b: 项目 B 版本（默认最新）
        dimensions: 对比维度列表，默认 ["complexity", "best_practices", "maintainability"]
        llm_config: LLM 配置（可选），包含 model, api_key, base_url 等
    
    Returns:
        ComparisonResult: 对比结果
    """
    start_time = time.time()
    
    dimensions = dimensions or ["complexity", "best_practices", "maintainability"]
    
    storage = StorageManager()
    
    # 检查项目是否存在
    if not storage.project_exists(project_a):
        return ComparisonResult(
            success=False,
            comparison_id="",
            project_a=project_a,
            project_b=project_b,
        )
    
    if not storage.project_exists(project_b):
        return ComparisonResult(
            success=False,
            comparison_id="",
            project_a=project_a,
            project_b=project_b,
        )
    
    # 加载项目数据
    data_a = storage.load_project(project_a, version_a)
    data_b = storage.load_project(project_b, version_b)
    
    if not data_a:
        return ComparisonResult(
            success=False,
            comparison_id="",
            project_a=project_a,
            project_b=project_b,
            dimensions=[],
            summary=f"无法加载项目 {project_a}",
        )
    
    if not data_b:
        return ComparisonResult(
            success=False,
            comparison_id="",
            project_a=project_a,
            project_b=project_b,
            dimensions=[],
            summary=f"无法加载项目 {project_b}",
        )
    
    # 计算对比
    ci_data_a = data_a.get("ci_data", {})
    ci_data_b = data_b.get("ci_data", {})
    meta_a = data_a.get("metadata", {})
    meta_b = data_b.get("metadata", {})
    
    dimension_results = _calculate_dimensions(ci_data_a, ci_data_b, dimensions)
    
    # 初始化 LLM 相关结果
    semantic_diff = None
    summary = None
    recommendations = None
    
    # 如果配置了 LLM，使用 LLM 生成分析
    if llm_config and HAS_LLM:
        try:
            llm_client = _create_llm_client(llm_config)
            
            # 并行调用 LLM 生成语义分析、总结和建议
            semantic_diff = _analyze_semantic_diff(
                llm_client, project_a, project_b, ci_data_a, ci_data_b, meta_a, meta_b
            )
            summary = _generate_summary_with_llm(
                llm_client, project_a, project_b, dimension_results, semantic_diff
            )
            recommendations = _generate_recommendations_with_llm(
                llm_client, project_a, project_b, dimension_results, semantic_diff
            )
        except Exception as e:
            # LLM 调用失败，回退到规则生成
            semantic_diff = f"[LLM 分析失败: {str(e)}]"
            summary = _generate_summary(project_a, project_b, dimension_results)
            recommendations = _generate_recommendations(dimension_results)
    else:
        # 使用规则生成
        summary = _generate_summary(project_a, project_b, dimension_results)
        recommendations = _generate_recommendations(dimension_results)
    
    # 保存对比结果
    comparison_id = f"{project_a}_vs_{project_b}_{int(time.time())}"
    compare_dir = storage._get_comparison_dir(comparison_id)
    compare_dir.mkdir(parents=True, exist_ok=True)
    
    import json
    with open(compare_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump({
            "comparison_id": comparison_id,
            "project_a": project_a,
            "project_b": project_b,
            "version_a": meta_a.get("version_id"),
            "version_b": meta_b.get("version_id"),
            "dimensions": dimensions,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }, f, ensure_ascii=False, indent=2)
    
    duration = time.time() - start_time
    
    return ComparisonResult(
        success=True,
        comparison_id=comparison_id,
        project_a=project_a,
        project_b=project_b,
        version_a=meta_a.get("version_id"),
        version_b=meta_b.get("version_id"),
        dimensions=dimension_results,
        semantic_diff=semantic_diff,
        summary=summary,
        recommendations=recommendations,
        duration_seconds=duration,
    )


def _calculate_dimensions(ci_data_a: dict, ci_data_b: dict, dimensions: List[str]) -> List[Dict[str, Any]]:
    """计算各维度对比"""
    results = []
    
    if "complexity" in dimensions:
        results.append(_calculate_complexity(ci_data_a, ci_data_b))
    
    if "best_practices" in dimensions:
        results.append(_calculate_best_practices(ci_data_a, ci_data_b))
    
    if "maintainability" in dimensions:
        results.append(_calculate_maintainability(ci_data_a, ci_data_b))
    
    return results


def _calculate_complexity(ci_data_a: dict, ci_data_b: dict) -> Dict[str, Any]:
    """计算架构复杂度维度"""
    def calc(data):
        workflows = data.get("workflows", {})
        return {
            "workflow_count": len(workflows),
            "job_count": sum(len(wf.get("jobs", {})) for wf in workflows.values()),
        }
    
    a = calc(ci_data_a)
    b = calc(ci_data_b)
    
    score_a = a["workflow_count"] * 2 + a["job_count"]
    score_b = b["workflow_count"] * 2 + b["job_count"]
    
    winner = "tie"
    if score_a > score_b:
        winner = "A"
    elif score_b > score_a:
        winner = "B"
    
    return {
        "name": "架构复杂度",
        "metrics": [
            {"name": "工作流数量", "value_a": a["workflow_count"], "value_b": b["workflow_count"], "unit": "个"},
            {"name": "Job 总数", "value_a": a["job_count"], "value_b": b["job_count"], "unit": "个"},
        ],
        "score_a": min(score_a / max(score_a + score_b, 1) * 100, 100),
        "score_b": min(score_b / max(score_a + score_b, 1) * 100, 100),
        "winner": winner,
    }


def _calculate_best_practices(ci_data_a: dict, ci_data_b: dict) -> Dict[str, Any]:
    """计算最佳实践维度"""
    def calc(data):
        workflows = data.get("workflows", {})
        job_count = sum(len(wf.get("jobs", {})) for wf in workflows.values())
        cache_count = sum(1 for wf in workflows.values() for job in wf.get("jobs", {}).values() if "cache" in str(job).lower())
        
        return {
            "cache_usage": (cache_count / job_count * 100) if job_count > 0 else 0,
            "job_count": job_count,
        }
    
    a = calc(ci_data_a)
    b = calc(ci_data_b)
    
    score_a = a["cache_usage"]
    score_b = b["cache_usage"]
    
    winner = "tie"
    if score_a > score_b:
        winner = "A"
    elif score_b > score_a:
        winner = "B"
    
    return {
        "name": "最佳实践",
        "metrics": [
            {"name": "缓存使用率", "value_a": round(a["cache_usage"], 1), "value_b": round(b["cache_usage"], 1), "unit": "%"},
        ],
        "score_a": min(score_a, 100),
        "score_b": min(score_b, 100),
        "winner": winner,
    }


def _calculate_maintainability(ci_data_a: dict, ci_data_b: dict) -> Dict[str, Any]:
    """计算可维护性维度"""
    def calc(data):
        actions = data.get("actions", [])
        scripts = data.get("scripts", [])
        workflows = data.get("workflows", {})
        
        return {
            "action_count": len(actions),
            "script_count": len(scripts),
            "workflow_count": len(workflows),
        }
    
    a = calc(ci_data_a)
    b = calc(ci_data_b)
    
    score_a = (a["action_count"] + a["script_count"]) / max(a["workflow_count"], 1)
    score_b = (b["action_count"] + b["script_count"]) / max(b["workflow_count"], 1)
    
    winner = "tie"
    if score_a > score_b:
        winner = "A"
    elif score_b > score_a:
        winner = "B"
    
    return {
        "name": "可维护性",
        "metrics": [
            {"name": "Action 数量", "value_a": a["action_count"], "value_b": b["action_count"], "unit": "个"},
            {"name": "脚本数量", "value_a": a["script_count"], "value_b": b["script_count"], "unit": "个"},
        ],
        "score_a": min(score_a * 20, 100),
        "score_b": min(score_b * 20, 100),
        "winner": winner,
    }


def _generate_summary(project_a: str, project_b: str, dimensions: List[Dict[str, Any]]) -> str:
    """生成对比总结"""
    wins_a = sum(1 for d in dimensions if d.get("winner") == "A")
    wins_b = sum(1 for d in dimensions if d.get("winner") == "B")
    
    if wins_a > wins_b:
        overall = f"{project_a} 综合表现更优"
    elif wins_b > wins_a:
        overall = f"{project_b} 综合表现更优"
    else:
        overall = "两个项目综合表现持平"
    
    lines = [f"## 对比总结\n", f"**总体评估**: {overall}\n\n"]
    lines.append("| 维度 | 胜出 |\n|------|------|\n")
    
    for d in dimensions:
        winner_name = project_a if d.get("winner") == "A" else (project_b if d.get("winner") == "B" else "平手")
        lines.append(f"| {d.get('name')} | {winner_name} |\n")
    
    return "".join(lines)


def _generate_recommendations(dimensions: List[Dict[str, Any]]) -> List[str]:
    """生成改进建议"""
    recommendations = []
    
    for d in dimensions:
        for m in d.get("metrics", []):
            if m.get("value_a") is not None and m.get("value_b") is not None:
                diff = abs(m["value_a"] - m["value_b"])
                max_val = max(abs(m["value_a"]), abs(m["value_b"]), 1)
                
                if diff / max_val > 0.5:
                    lower = "A" if m["value_a"] < m["value_b"] else "B"
                    higher = "B" if m["value_a"] < m["value_b"] else "A"
                    recommendations.append(
                        f"{d['name']} - {m['name']}: "
                        f"项目{lower} ({m[f'value_{lower}']}{m['unit']}) 显著低于 "
                        f"项目{higher} ({m[f'value_{higher}']}{m['unit']})"
                    )
    
    if not recommendations:
        recommendations.append("两个项目在各项指标上表现相近，无需特别优化建议")
    
    return recommendations[:5]


def _create_llm_client(llm_config: Dict[str, Any]):
    """创建 LLM 客户端"""
    if not HAS_LLM:
        raise RuntimeError("LLM module not available")
    if llm_config.get("api_key"):
        return LLMClient(
            model=llm_config.get("model", "gpt-4o-mini"),
            api_key=llm_config.get("api_key"),
            base_url=llm_config.get("base_url"),
            temperature=llm_config.get("temperature", 0.7),
            max_tokens=llm_config.get("max_tokens", 131072),
        )
    return create_client(model=llm_config.get("model"))


def _analyze_semantic_diff(
    llm_client,
    project_a: str,
    project_b: str,
    ci_data_a: dict,
    ci_data_b: dict,
    meta_a: dict,
    meta_b: dict,
) -> str:
    """使用 LLM 分析架构模式差异"""
    if not HAS_LLM:
        raise RuntimeError("LLM module not available")
    import json
    
    system_prompt = """你是一个 CI/CD 架构专家，擅长分析 GitHub Actions 工作流的架构设计模式。
请从以下角度分析：
1. 工作流设计模式（串行/并行/矩阵等）
2. 复用策略（Actions、Reusable Workflows、模板）
3. 依赖管理策略（Caching、依赖预取等）
4. 部署策略（蓝绿、金丝雀、滚动等）
5. 安全最佳实践（权限控制、密钥管理）
6. 可扩展性和可维护性

请用中文回答，使用 Markdown 格式。"""

    prompt = f"""## 项目 A: {project_a} (版本: {meta_a.get('version_id', 'N/A')})
```yaml
{json.dumps(ci_data_a, ensure_ascii=False, indent=2)}
```

---

## 项目 B: {project_b} (版本: {meta_b.get('version_id', 'N/A')})
```yaml
{json.dumps(ci_data_b, ensure_ascii=False, indent=2)}
```

---

请分析这两个项目在 CI/CD 架构设计上的主要差异，包括：
1. 各自的优势架构模式
2. 存在的架构问题或反模式
3. 关键的设计选择对比

请用结构化的 Markdown 格式回答。"""

    return llm_client.chat(prompt, system_prompt)


def _generate_summary_with_llm(
    llm_client,
    project_a: str,
    project_b: str,
    dimensions: List[Dict[str, Any]],
    semantic_diff: str,
) -> str:
    """使用 LLM 生成对比总结"""
    if not HAS_LLM:
        raise RuntimeError("LLM module not available")
    import json
    
    system_prompt = """你是一个 CI/CD 架构评估专家，擅长总结项目对比结果。
请基于定量指标和定性分析，生成一份清晰、有见地的对比总结。
请用中文回答，使用 Markdown 格式。"""

    dimensions_str = json.dumps(dimensions, ensure_ascii=False, indent=2)
    
    prompt = f"""## 项目对比
- 项目 A: {project_a}
- 项目 B: {project_b}

## 定量维度得分
```json
{dimensions_str}
```

## 架构模式差异分析
{semantic_diff}

---

请生成一份总结，包括：
1. 总体评估（哪个项目更好，好在哪里）
2. 各维度的关键发现
3. 两个项目的主要差距

请用中文回答。"""

    return llm_client.chat(prompt, system_prompt)


def _generate_recommendations_with_llm(
    llm_client,
    project_a: str,
    project_b: str,
    dimensions: List[Dict[str, Any]],
    semantic_diff: str,
) -> List[str]:
    """使用 LLM 生成改进建议"""
    if not HAS_LLM:
        raise RuntimeError("LLM module not available")
    import json
    
    system_prompt = """你是一个 CI/CD 架构优化专家，擅长给出可操作的改进建议。
请根据对比分析，为落后的项目提供具体的改进建议。
请用中文回答，输出 JSON 数组格式的建议列表。"""

    dimensions_str = json.dumps(dimensions, ensure_ascii=False, indent=2)
    
    prompt = f"""## 项目对比
- 项目 A: {project_a}
- 项目 B: {project_b}

## 定量维度得分
```json
{dimensions_str}
```

## 架构模式差异分析
{semantic_diff}

---

请为两个项目分别提供改进建议。输出格式：
```json
[
  {{"project": "{project_a}", "recommendation": "建议内容..."}},
  {{"project": "{project_b}", "recommendation": "建议内容..."}}
]
```

只输出 JSON，不要有其他内容。"""

    try:
        result = llm_client.chat(prompt, system_prompt)
        import json
        recs = json.loads(result)
        if isinstance(recs, list):
            return [f"{r.get('project', 'N/A')}: {r.get('recommendation', '')}" for r in recs[:6]]
    except Exception:
        pass
    
    return _generate_recommendations(dimensions)
