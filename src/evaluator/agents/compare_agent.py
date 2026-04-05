# CI/CD 架构对比 Agent

import json
from pathlib import Path
from typing import Optional, TypedDict, Any, List, Dict

from storage import StorageManager
from .compare_dimensions import (
    COMPARE_DIMENSIONS,
    DimensionCalculator,
    MetricResult,
    DimensionResult,
)
from evaluator.core.types import ComparisonResult
from .base_agent import BaseAgent, AgentMeta

try:
    from evaluator.llm import LLMClient
    HAS_LLM = True
except ImportError:
    HAS_LLM = False

try:
    from markdown_it import MarkdownIt
    HAS_MARKDOWN = True
except ImportError:
    HAS_MARKDOWN = False


class CompareInput(TypedDict):
    project_a: str
    project_b: str
    version_a: Optional[str]
    version_b: Optional[str]
    dimensions: Optional[list[str]]


class CompareAgent(BaseAgent):

    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="CompareAgent",
            description="对比两个已分析项目的 CI/CD 架构",
            category="analysis",
            inputs=["project_a", "project_b", "dimensions"],
            outputs=["comparison_result", "comparison_dir"],
            dependencies=[],
        )
    
    def __init__(
        self,
        storage_manager: Optional[StorageManager] = None,
        llm: Optional["LLMClient"] = None,
    ):
        super().__init__()
        self.storage = storage_manager or StorageManager()
        self.calculator = DimensionCalculator()
        self.llm = llm

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        project_a = state.get("project_a")
        project_b = state.get("project_b")
        version_a = state.get("version_a")
        version_b = state.get("version_b")
        selected_dimensions = state.get("dimensions") or list(COMPARE_DIMENSIONS.keys())

        if not project_a or not project_b:
            return {
                **state,
                "errors": state.get("errors", []) + ["缺少对比项目参数"],
                "comparison_result": None,
            }

        if not self.storage.project_exists(project_a):
            return {
                **state,
                "errors": state.get("errors", []) + [f"Project not found: {project_a}"],
                "comparison_result": None,
            }
        if not self.storage.project_exists(project_b):
            return {
                **state,
                "errors": state.get("errors", []) + [f"Project not found: {project_b}"],
                "comparison_result": None,
            }

        data_a = self.storage.load_project(project_a, version_a)
        data_b = self.storage.load_project(project_b, version_b)

        if not data_a:
            return {
                **state,
                "errors": state.get("errors", []) + [f"Failed to load {project_a}"],
                "comparison_result": None,
            }
        if not data_b:
            return {
                **state,
                "errors": state.get("errors", []) + [f"Failed to load {project_b}"],
                "comparison_result": None,
            }

        ci_data_a = data_a.get("ci_data", {})
        ci_data_b = data_b.get("ci_data", {})
        metadata_a = data_a.get("metadata", {})
        metadata_b = data_b.get("metadata", {})

        metrics_a = self.calculator.calculate_all(ci_data_a)
        metrics_b = self.calculator.calculate_all(ci_data_b)

        dimension_results = []
        dimension_scores = {"A": 0, "B": 0}

        for dim_key in selected_dimensions:
            if dim_key not in COMPARE_DIMENSIONS:
                continue

            dim_config = COMPARE_DIMENSIONS[dim_key]
            dim_results = []

            for metric_key, metric_config in dim_config["metrics"].items():
                val_a = metrics_a.get(dim_key, {}).get(metric_key)
                val_b = metrics_b.get(dim_key, {}).get(metric_key)

                result = MetricResult(
                    name=metric_config["name"],
                    value_a=val_a,
                    value_b=val_b,
                    unit=metric_config["unit"],
                    higher_is_better=metric_config["higher_is_better"],
                )
                dim_results.append(result)

            scores = self._calculate_dimension_score(
                dim_results, project_a, project_b, dim_key, 
                metrics_a.get(dim_key, {}), metrics_b.get(dim_key, {})
            )
            dim_results_obj = DimensionResult(
                name=dim_config["name"],
                metrics=dim_results,
                score_a=scores["A"],
                score_b=scores["B"],
            )
            dimension_results.append(dim_results_obj)

            dimension_scores["A"] += scores["A"]
            dimension_scores["B"] += scores["B"]

        # LLM 分析（如果可用）
        semantic_diff = None
        if self.llm and HAS_LLM:
            try:
                version_dir_a = self.storage.get_version_dir(project_a, version_a)
                version_dir_b = self.storage.get_version_dir(project_b, version_b)
                semantic_diff = self._analyze_semantic_diff(
                    project_a, project_b, version_dir_a, version_dir_b
                )
                summary = self._generate_summary_with_llm(
                    project_a, project_b, dimension_results, semantic_diff
                )
                recommendations = self._generate_recommendations_with_llm(
                    project_a, project_b, dimension_results, semantic_diff
                )
            except Exception as e:
                print(f"  [WARN] LLM 分析失败: {e}，使用规则分析")
                summary = self._generate_summary(
                    project_a, project_b, dimension_results, dimension_scores, metadata_a, metadata_b
                )
                recommendations = self._generate_recommendations(metrics_a, metrics_b, dimension_results)
        else:
            summary = self._generate_summary(
                project_a, project_b, dimension_results, dimension_scores, metadata_a, metadata_b
            )
            recommendations = self._generate_recommendations(metrics_a, metrics_b, dimension_results)

        dimensions_dicts = [self._dim_to_dict(d) for d in dimension_results]

        comparison_result = ComparisonResult(
            success=True,
            comparison_id="",
            project_a=project_a,
            project_b=project_b,
            version_a=metadata_a.get("version_id"),
            version_b=metadata_b.get("version_id"),
            dimensions=dimensions_dicts,
            semantic_diff=semantic_diff,
            summary=summary,
            recommendations=recommendations,
        )

        compare_md = self._generate_compare_markdown(comparison_result, data_a, data_b, dimension_results)
        compare_html = self._generate_compare_html(comparison_result, data_a, data_b, dimension_results)

        comparison_id = self.storage.save_comparison(
            project_a=project_a,
            project_b=project_b,
            version_a=metadata_a.get("version_id"),
            version_b=metadata_b.get("version_id"),
            compare_md=compare_md,
            compare_html=compare_html,
            dimensions=selected_dimensions,
        )

        comparison_dir = str(self.storage.data_dir / "comparisons" / comparison_id)

        return {
            **state,
            "comparison_result": {
                "comparison_id": comparison_id,
                "project_a": project_a,
                "project_b": project_b,
                "version_a": metadata_a.get("version_id"),
                "version_b": metadata_b.get("version_id"),
                "summary": summary,
                "semantic_diff": semantic_diff,
                "dimensions": dimensions_dicts,
                "recommendations": recommendations,
                "compare_html": compare_html,
            },
            "comparison_dir": comparison_dir,
        }

    def _analyze_semantic_diff(
        self,
        project_a: str,
        project_b: str,
        version_dir_a: str,
        version_dir_b: str,
    ) -> str:
        """使用 LLM 分析架构模式差异"""
        if not self.llm or not HAS_LLM:
            return ""

        system_prompt = """你是一个 CI/CD 架构专家，擅长分析 GitHub Actions 工作流的架构设计模式。
请从以下角度分析：
1. 工作流设计模式（串行/并行/矩阵等）
2. 复用策略（Actions、Reusable Workflows、模板）
3. 依赖管理策略（Caching、依赖预取等）
4. 部署策略（蓝绿、金丝雀、滚动等）
5. 安全最佳实践（权限控制、密钥管理）
6. 可扩展性和可维护性

请用中文回答，使用 Markdown 格式。"""

        dir_a = Path(version_dir_a)
        dir_b = Path(version_dir_b)

        summary_a = {}
        summary_b = {}
        if (dir_a / "analysis_summary.json").exists():
            with open(dir_a / "analysis_summary.json", "r", encoding="utf-8") as f:
                summary_a = json.load(f)
        if (dir_b / "analysis_summary.json").exists():
            with open(dir_b / "analysis_summary.json", "r", encoding="utf-8") as f:
                summary_b = json.load(f)

        arch_a = {}
        arch_b = {}
        if (dir_a / "architecture.json").exists():
            with open(dir_a / "architecture.json", "r", encoding="utf-8") as f:
                arch_a = json.load(f)
        if (dir_b / "architecture.json").exists():
            with open(dir_b / "architecture.json", "r", encoding="utf-8") as f:
                arch_b = json.load(f)

        md_a = ""
        md_b = ""
        if (dir_a / "CI_ARCHITECTURE.md").exists():
            with open(dir_a / "CI_ARCHITECTURE.md", "r", encoding="utf-8") as f:
                md_a = f.read()[:8000]
        if (dir_b / "CI_ARCHITECTURE.md").exists():
            with open(dir_b / "CI_ARCHITECTURE.md", "r", encoding="utf-8") as f:
                md_b = f.read()[:8000]

        prompt = f"""## 项目 A: {project_a}

### 分析摘要
```json
{json.dumps(summary_a, ensure_ascii=False, indent=2)}
```

### 架构层级
```json
{json.dumps(arch_a, ensure_ascii=False, indent=2)}
```

### Markdown 报告摘要
```
{md_a}
```

---

## 项目 B: {project_b}

### 分析摘要
```json
{json.dumps(summary_b, ensure_ascii=False, indent=2)}
```

### 架构层级
```json
{json.dumps(arch_b, ensure_ascii=False, indent=2)}
```

### Markdown 报告摘要
```
{md_b}
```

---

请分析这两个项目在 CI/CD 架构设计上的主要差异，包括：
1. 各自的优势架构模式
2. 存在的架构问题或反模式
3. 关键的设计选择对比

请用结构化的 Markdown 格式回答。"""

        return self.llm.chat(prompt, system_prompt)

    def _generate_summary_with_llm(
        self,
        project_a: str,
        project_b: str,
        dimension_results: list,
        semantic_diff: str,
    ) -> str:
        """使用 LLM 生成对比总结"""
        if not self.llm or not HAS_LLM:
            return ""

        system_prompt = """你是一个 CI/CD 架构评估专家，擅长总结项目对比结果。
请基于定量指标和定性分析，生成一份清晰、有见地的对比总结。
请用中文回答，使用 Markdown 格式。"""

        dimensions_list = [self._dim_to_dict(d) for d in dimension_results]
        dimensions_str = json.dumps(dimensions_list, ensure_ascii=False, indent=2)

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

        return self.llm.chat(prompt, system_prompt)

    def _generate_recommendations_with_llm(
        self,
        project_a: str,
        project_b: str,
        dimension_results: list,
        semantic_diff: str,
    ) -> List[str]:
        """使用 LLM 生成改进建议"""
        if not self.llm or not HAS_LLM:
            return []

        system_prompt = """你是一个 CI/CD 架构优化专家，擅长给出可操作的改进建议。
请根据对比分析，为落后的项目提供具体的改进建议。
请用中文回答，输出 JSON 数组格式的建议列表。"""

        dimensions_list = [self._dim_to_dict(d) for d in dimension_results]
        dimensions_str = json.dumps(dimensions_list, ensure_ascii=False, indent=2)

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
            result = self.llm.chat(prompt, system_prompt)
            recs = json.loads(result)
            if isinstance(recs, list):
                return [f"{r.get('project', 'N/A')}: {r.get('recommendation', '')}" for r in recs[:6]]
        except Exception:
            pass

        return []

    def _calculate_dimension_score(
        self,
        metrics: list[MetricResult],
        project_a: str = "",
        project_b: str = "",
        dimension_key: str = "",
        metrics_a: dict = None,
        metrics_b: dict = None,
    ) -> dict:
        """计算维度得分 - 使用 LLM 判定"""
        return self._calculate_dimension_score_with_llm(
            project_a, project_b, dimension_key, metrics_a or {}, metrics_b or {}
        )
    
    def _calculate_dimension_score_with_llm(
        self,
        project_a: str,
        project_b: str,
        dimension_key: str,
        metrics_a: dict,
        metrics_b: dict,
    ) -> dict:
        """使用 LLM 判定维度得分"""
        
        dimension_names = {
            "complexity": "架构复杂度",
            "best_practices": "最佳实践",
            "maintainability": "可维护性",
        }
        dimension_name = dimension_names.get(dimension_key, dimension_key)
        
        prompt = f"""你是一个 CI/CD 架构专家，请评估两个项目在"{dimension_name}"维度的得分。

## 项目 A: {project_a}
指标数据：
```json
{json.dumps(metrics_a, indent=2, ensure_ascii=False)}
```

## 项目 B: {project_b}
指标数据：
```json
{json.dumps(metrics_b, indent=2, ensure_ascii=False)}
```

## 评分要求
1. 考虑项目类型和业务复杂度
2. 不要单纯比较数量，要评估"必要的复杂度"
3. 满分 100 分，两个项目的得分之和应该接近 100
4. 如果一个项目明显更优，得分应该显著高于另一个

## 输出格式
只输出 JSON，不要其他内容：
{{"score_a": <0-100>, "score_b": <0-100>, "reasoning": "<评分理由>"}}
"""
        
        try:
            response = self.llm.chat(prompt)
            
            import re
            json_match = re.search(r'\{[^{}]*"score_a"[^{}]*\}', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                return {
                    "A": round(float(result.get("score_a", 50)), 1),
                    "B": round(float(result.get("score_b", 50)), 1),
                }
        except Exception as e:
            print(f"  [WARN] LLM 评分失败: {e}，使用规则计算")
        
        # 回退
        return {"A": 50.0, "B": 50.0}
    
    def _generate_summary(
        self,
        project_a: str,
        project_b: str,
        dimension_results: list[DimensionResult],
        dimension_scores: dict,
        metadata_a: dict,
        metadata_b: dict,
    ) -> str:
        overall_winner = "平手"
        if dimension_scores["A"] > dimension_scores["B"]:
            overall_winner = project_a
        elif dimension_scores["B"] > dimension_scores["A"]:
            overall_winner = project_b

        dim_winners = []
        for d in dimension_results:
            if d.score_a > d.score_b:
                dim_winners.append(f"{d.name}（{project_a}胜）")
            elif d.score_b > d.score_a:
                dim_winners.append(f"{d.name}（{project_b}胜）")
            else:
                dim_winners.append(f"{d.name}（平手）")

        summary = f"""## 对比总结

### 总体评估
- **项目 A**: {project_a}
- **项目 B**: {project_b}
- **综合胜出**: {overall_winner}

### 各维度表现
"""
        for winner in dim_winners:
            summary += f"- {winner}\n"

        return summary

    def _generate_recommendations(
        self,
        metrics_a: dict,
        metrics_b: dict,
        dimension_results: list[DimensionResult],
    ) -> list[str]:
        recommendations = []

        for dim_result in dimension_results:
            for metric in dim_result.metrics:
                if metric.value_a is None or metric.value_b is None:
                    continue

                diff = abs(metric.value_a - metric.value_b)
                max_val = max(abs(metric.value_a), abs(metric.value_b), 1)

                if max_val == 0:
                    continue

                relative_diff = diff / max_val
                if relative_diff < 0.2:
                    continue

                if metric.higher_is_better:
                    if metric.value_b < metric.value_a * 0.7:
                        recommendations.append(
                            f"{dim_result.name} - {metric.name}: "
                            f"{metric.value_b}{metric.unit} 显著低于 {metric.value_a}{metric.unit}，"
                            f"建议参考 {metric.name} 的实现方式"
                        )
                else:
                    if metric.value_b > metric.value_a * 1.3:
                        recommendations.append(
                            f"{dim_result.name} - {metric.name}: "
                            f"{metric.value_b}{metric.unit} 显著高于 {metric.value_a}{metric.unit}，"
                            f"考虑优化以降低复杂度"
                        )

        if not recommendations:
            recommendations.append("两个项目在各项指标上表现相近，无需特别优化建议")

        return recommendations

    def _markdown_to_html(self, md_text: str) -> str:
        """将 Markdown 转换为 HTML"""
        if not md_text:
            return ""
        
        if not HAS_MARKDOWN:
            return f"<pre style='white-space: pre-wrap;'>{md_text}</pre>"
        
        try:
            md = MarkdownIt()
            md.enable('table')  # 启用表格支持
            html = md.render(md_text)
            return html
        except Exception as e:
            print(f"  [WARN] Markdown 转 HTML 失败: {e}")
            return f"<pre style='white-space: pre-wrap;'>{md_text}</pre>"

    def _dim_to_dict(self, dim: DimensionResult) -> dict:
        return {
            "name": dim.name,
            "metrics": [
                {
                    "name": m.name,
                    "value_a": m.value_a,
                    "value_b": m.value_b,
                    "unit": m.unit,
                    "winner": m.winner,
                }
                for m in dim.metrics
            ],
            "score_a": dim.score_a,
            "score_b": dim.score_b,
            "winner": dim.winner,
        }

    def _generate_compare_markdown(self, result: ComparisonResult, data_a: dict, data_b: dict, dimension_results: list) -> str:
        md = f"""# CI/CD 架构对比报告

## 项目信息

| 项目 | 名称 | 版本 | 分析时间 |
|------|------|------|----------|
| A | {result.project_a} | {data_a.get('metadata', {}).get('version_id', 'N/A')} | {data_a.get('metadata', {}).get('analyzed_at', 'N/A')[:10]} |
| B | {result.project_b} | {data_b.get('metadata', {}).get('version_id', 'N/A')} | {data_b.get('metadata', {}).get('analyzed_at', 'N/A')[:10]} |

"""
        
        # 添加架构分析（如果有）
        if result.semantic_diff:
            md += f"""## 架构分析

{result.semantic_diff}

"""
        
        md += f"""## 对比总结

{result.summary}

## 详细对比

"""
        for dim in dimension_results:
            md += f"### {dim.name}\n\n"
            md += f"| 指标 | {result.project_a} | {result.project_b} | 胜出 |\n"
            md += f"|------|------|------|------|\n"
            for m in dim.metrics:
                val_a = f"{m.value_a}{m.unit}" if m.value_a is not None else "N/A"
                val_b = f"{m.value_b}{m.unit}" if m.value_b is not None else "N/A"
                winner = {"A": result.project_a, "B": result.project_b, "tie": "平手", "N/A": "N/A"}.get(m.winner, "N/A")
                md += f"| {m.name} | {val_a} | {val_b} | {winner} |\n"
            md += f"\n**维度得分**: {result.project_a}={dim.score_a}分, {result.project_b}={dim.score_b}分\n\n"

        if result.recommendations:
            md += "\n## 改进建议\n\n"
            for i, rec in enumerate(result.recommendations, 1):
                md += f"{i}. {rec}\n"

        return md

    def _generate_compare_html(self, result: ComparisonResult, data_a: dict, data_b: dict, dimension_results: list) -> str:
        project_info_rows = f"""
            <tr>
                <td><strong>A</strong></td>
                <td>{result.project_a}</td>
                <td>{data_a.get('metadata', {}).get('version_id', 'N/A')}</td>
                <td>{data_a.get('metadata', {}).get('analyzed_at', 'N/A')[:10]}</td>
            </tr>
            <tr>
                <td><strong>B</strong></td>
                <td>{result.project_b}</td>
                <td>{data_b.get('metadata', {}).get('version_id', 'N/A')}</td>
                <td>{data_b.get('metadata', {}).get('analyzed_at', 'N/A')[:10]}</td>
            </tr>
        """

        dimension_cards = ""
        for dim in dimension_results:
            metrics_rows = ""
            for m in dim.metrics:
                val_a = f"{m.value_a}{m.unit}" if m.value_a is not None else "N/A"
                val_b = f"{m.value_b}{m.unit}" if m.value_b is not None else "N/A"
                winner_class = {"A": "winner-a", "B": "winner-b", "tie": "winner-tie"}.get(m.winner, "")
                winner_text = {"A": result.project_a, "B": result.project_b, "tie": "平手"}.get(m.winner, "-")
                metrics_rows += f"""
                    <tr class="{winner_class}">
                        <td>{m.name}</td>
                        <td>{val_a}</td>
                        <td>{val_b}</td>
                        <td>{winner_text}</td>
                    </tr>
                """

            dim_winner_class = {"A": "card-a", "B": "card-b", "tie": "card-tie"}.get(dim.winner, "")
            dim_winner_text = {"A": result.project_a, "B": result.project_b, "tie": "平手"}.get(dim.winner, "")

            dimension_cards += f"""
                <div class="dimension-card {dim_winner_class}">
                    <div class="card-header">
                        <h3>{dim.name}</h3>
                        <span class="winner-badge">胜出: {dim_winner_text} ({max(dim.score_a, dim.score_b):.1f}分)</span>
                    </div>
                    <table class="metrics-table">
                        <thead>
                            <tr>
                                <th>指标</th>
                                <th>{result.project_a}</th>
                                <th>{result.project_b}</th>
                                <th>胜出</th>
                            </tr>
                        </thead>
                        <tbody>
                            {metrics_rows}
                        </tbody>
                    </table>
                    <div class="score-bar">
                        <div class="score-a" style="width: {dim.score_a}%">{dim.score_a}</div>
                        <div class="score-b" style="width: {dim.score_b}%">{dim.score_b}</div>
                    </div>
                </div>
            """

        recommendations_section = ""
        if result.recommendations:
            recommendations_list = ""
            for i, rec in enumerate(result.recommendations, 1):
                recommendations_list += f"<li>{rec}</li>"
            
            recommendations_section = f"""
        <div class="card recommendations">
            <h3>改进建议</h3>
            <ul>
                {recommendations_list}
            </ul>
        </div>
"""
        
        semantic_diff_section = ""
        if result.semantic_diff:
            semantic_diff_html = self._markdown_to_html(result.semantic_diff)
            semantic_diff_section = f"""
        <div class="card">
            <div class="card-header">
                <h2>架构分析</h2>
            </div>
            <div class="analysis-content" style="padding: 20px;">
                {semantic_diff_html}
            </div>
        </div>
"""
        
        summary_section = ""
        if result.summary:
            summary_html = self._markdown_to_html(result.summary)
            summary_section = f"""
        <div class="card">
            <div class="card-header">
                <h2>对比总结</h2>
            </div>
            <div class="summary-content" style="padding: 20px;">
                {summary_html}
            </div>
        </div>
"""

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CI/CD 架构对比报告 - {result.project_a} vs {result.project_b}</title>
    <style>
        :root {{
            --primary: #3498db;
            --success: #2ecc71;
            --warning: #f39c12;
            --danger: #e74c3c;
            --dark: #1a1a2e;
            --gray: #95a5a6;
        }}
        
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #f5f5f5;
            color: #333;
            line-height: 1.6;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }}
        
        .header {{
            background: linear-gradient(135deg, var(--dark) 0%, #2c3e50 100%);
            color: white;
            padding: 40px;
            border-radius: 12px;
            margin-bottom: 30px;
        }}
        
        .header h1 {{
            font-size: 28px;
            margin-bottom: 10px;
        }}
        
        .header .subtitle {{
            opacity: 0.8;
            font-size: 14px;
        }}
        
        .card {{
            background: white;
            border-radius: 12px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin-bottom: 20px;
            overflow: hidden;
        }}
        
        .card-header {{
            background: #f8f9fa;
            padding: 20px;
            border-bottom: 1px solid #eee;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .card-header h2 {{
            color: var(--dark);
            font-size: 20px;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        
        th {{
            background: var(--primary);
            color: white;
            padding: 12px 15px;
            text-align: left;
            font-weight: 600;
        }}
        
        td {{
            padding: 12px 15px;
            border-bottom: 1px solid #eee;
        }}
        
        tr:hover {{
            background: #f8f9fa;
        }}
        
        .winner-a {{
            background: rgba(52, 152, 219, 0.1);
        }}
        
        .winner-b {{
            background: rgba(46, 204, 113, 0.1);
        }}
        
        .winner-tie {{
            background: rgba(243, 156, 18, 0.1);
        }}
        
        .dimension-card {{
            background: white;
            border-radius: 12px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin-bottom: 20px;
            overflow: hidden;
        }}
        
        .dimension-card.card-a {{
            border-left: 4px solid var(--primary);
        }}
        
        .dimension-card.card-b {{
            border-left: 4px solid var(--success);
        }}
        
        .dimension-card.card-tie {{
            border-left: 4px solid var(--warning);
        }}
        
        .winner-badge {{
            background: var(--primary);
            color: white;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
        }}
        
        .score-bar {{
            display: flex;
            height: 30px;
            background: #eee;
            border-radius: 0 0 12px 12px;
            overflow: hidden;
        }}
        
        .score-a {{
            background: var(--primary);
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 600;
            font-size: 12px;
        }}
        
        .score-b {{
            background: var(--success);
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 600;
            font-size: 12px;
        }}
        
        .recommendations {{
            background: #fff3cd;
            border-radius: 8px;
            padding: 20px;
            margin-top: 20px;
        }}
        
        .recommendations h3 {{
            color: #856404;
            margin-bottom: 15px;
        }}
        
        .recommendations ul {{
            margin-left: 20px;
        }}
        
        .recommendations li {{
            color: #856404;
            margin-bottom: 8px;
        }}
        
        .analysis-content table,
        .summary-content table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        
        .analysis-content th,
        .summary-content th {{
            background: var(--primary);
            color: white;
            padding: 12px 15px;
            text-align: left;
            font-weight: 600;
        }}
        
        .analysis-content td,
        .summary-content td {{
            padding: 12px 15px;
            border-bottom: 1px solid #eee;
            vertical-align: top;
        }}
        
        .analysis-content tr:hover,
        .summary-content tr:hover {{
            background: #f8f9fa;
        }}
        
        .analysis-content h2,
        .summary-content h2 {{
            color: var(--dark);
            font-size: 20px;
            margin: 30px 0 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #eee;
        }}
        
        .analysis-content h3,
        .summary-content h3 {{
            color: var(--dark);
            font-size: 18px;
            margin: 25px 0 12px;
        }}
        
        .analysis-content p,
        .summary-content p {{
            margin: 10px 0;
            line-height: 1.8;
        }}
        
        .analysis-content ul,
        .analysis-content ol,
        .summary-content ul,
        .summary-content ol {{
            margin: 10px 0 10px 20px;
        }}
        
        .analysis-content li,
        .summary-content li {{
            margin: 5px 0;
            line-height: 1.6;
        }}
        
        .analysis-content strong,
        .summary-content strong {{
            color: var(--primary);
            font-weight: 600;
        }}
        
        .analysis-content code,
        .summary-content code {{
            background: #f1f1f1;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>CI/CD 架构对比报告</h1>
            <div class="subtitle">{result.project_a} vs {result.project_b}</div>
        </div>
        
        <div class="card">
            <div class="card-header">
                <h2>项目信息</h2>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>标识</th>
                        <th>项目名称</th>
                        <th>版本</th>
                        <th>分析时间</th>
                    </tr>
                </thead>
                <tbody>
                    {project_info_rows}
                </tbody>
            </table>
        </div>
        
        <h2 style="margin: 30px 0 20px;">维度对比</h2>
        {dimension_cards}
        
        {semantic_diff_section}
        
        {summary_section}
        
        {recommendations_section}
    </div>
</body>
</html>"""
