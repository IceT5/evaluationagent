# CI/CD 架构对比 Agent

import json
from pathlib import Path
from typing import Optional, TypedDict

from storage import StorageManager
from .compare_dimensions import (
    COMPARE_DIMENSIONS,
    DimensionCalculator,
    MetricResult,
    DimensionResult,
    ComparisonResult,
)


class CompareInput(TypedDict):
    project_a: str
    project_b: str
    version_a: Optional[str]
    version_b: Optional[str]
    dimensions: Optional[list[str]]


class CompareAgent:
    def __init__(self, storage_manager: Optional[StorageManager] = None):
        self.storage = storage_manager or StorageManager()
        self.calculator = DimensionCalculator()

    def run(self, input_data: CompareInput) -> dict:
        project_a = input_data["project_a"]
        project_b = input_data["project_b"]
        version_a = input_data.get("version_a")
        version_b = input_data.get("version_b")
        selected_dimensions = input_data.get("dimensions", list(COMPARE_DIMENSIONS.keys()))

        if not self.storage.project_exists(project_a):
            return {"error": f"Project not found: {project_a}"}
        if not self.storage.project_exists(project_b):
            return {"error": f"Project not found: {project_b}"}

        data_a = self.storage.load_project(project_a, version_a)
        data_b = self.storage.load_project(project_b, version_b)

        if not data_a:
            return {"error": f"Failed to load {project_a}"}
        if not data_b:
            return {"error": f"Failed to load {project_b}"}

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

            scores = self._calculate_dimension_score(dim_results)
            dim_results_obj = DimensionResult(
                name=dim_config["name"],
                metrics=dim_results,
                score_a=scores["A"],
                score_b=scores["B"],
            )
            dimension_results.append(dim_results_obj)

            dimension_scores["A"] += scores["A"]
            dimension_scores["B"] += scores["B"]

        summary = self._generate_summary(
            project_a, project_b, dimension_results, dimension_scores, metadata_a, metadata_b
        )
        recommendations = self._generate_recommendations(metrics_a, metrics_b, dimension_results)

        comparison_result = ComparisonResult(
            project_a=project_a,
            project_b=project_b,
            dimensions=dimension_results,
            summary=summary,
            recommendations=recommendations,
        )

        compare_md = self._generate_compare_markdown(comparison_result, data_a, data_b)
        compare_html = self._generate_compare_html(comparison_result, data_a, data_b)

        comparison_id = self.storage.save_comparison(
            project_a=project_a,
            project_b=project_b,
            version_a=metadata_a.get("version_id"),
            version_b=metadata_b.get("version_id"),
            compare_md=compare_md,
            compare_html=compare_html,
            dimensions=selected_dimensions,
        )

        return {
            "comparison_id": comparison_id,
            "project_a": project_a,
            "project_b": project_b,
            "version_a": metadata_a.get("version_id"),
            "version_b": metadata_b.get("version_id"),
            "summary": summary,
            "dimension_results": [self._dim_to_dict(d) for d in dimension_results],
            "recommendations": recommendations,
            "compare_html": compare_html,
        }

    def _calculate_dimension_score(self, metrics: list[MetricResult]) -> dict:
        score_a = 0
        score_b = 0
        total = 0

        for m in metrics:
            if m.value_a is None and m.value_b is None:
                continue
            if m.value_a is None or m.value_b is None:
                total += 1
                if m.value_a is None:
                    score_b += 1
                else:
                    score_a += 1
                continue

            total += 1
            diff = abs(m.value_a - m.value_b)
            max_val = max(abs(m.value_a), abs(m.value_b), 1)

            if m.higher_is_better:
                if m.value_a > m.value_b:
                    score_a += 1 + (diff / max_val) * 0.5
                elif m.value_b > m.value_a:
                    score_b += 1 + (diff / max_val) * 0.5
            else:
                if m.value_a < m.value_b:
                    score_a += 1 + (diff / max_val) * 0.5
                elif m.value_b < m.value_a:
                    score_b += 1 + (diff / max_val) * 0.5

        if total > 0:
            score_a = (score_a / total) * 100
            score_b = (score_b / total) * 100

        return {"A": round(score_a, 1), "B": round(score_b, 1)}

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

    def _generate_compare_markdown(self, result: ComparisonResult, data_a: dict, data_b: dict) -> str:
        md = f"""# CI/CD 架构对比报告

## 项目信息

| 项目 | 名称 | 版本 | 分析时间 |
|------|------|------|----------|
| A | {result.project_a} | {data_a.get('metadata', {}).get('version_id', 'N/A')} | {data_a.get('metadata', {}).get('analyzed_at', 'N/A')[:10]} |
| B | {result.project_b} | {data_b.get('metadata', {}).get('version_id', 'N/A')} | {data_b.get('metadata', {}).get('analyzed_at', 'N/A')[:10]} |

## 对比总结

{result.summary}

## 详细对比

"""
        for dim in result.dimensions:
            md += f"### {dim.name}\n\n"
            md += f"| 指标 | {result.project_a} | {result.project_b} | 胜出 |\n"
            md += f"|------|------|------|------|\n"
            for m in dim.metrics:
                val_a = f"{m.value_a}{m.unit}" if m.value_a is not None else "N/A"
                val_b = f"{m.value_b}{m.unit}" if m.value_b is not None else "N/A"
                winner = {"A": result.project_a, "B": result.project_b, "tie": "平手", "N/A": "N/A"}.get(m.winner, "N/A")
                md += f"| {m.name} | {val_a} | {val_b} | {winner} |\n"
            md += f"\n**维度得分**: {result.project_a}={dim.score_a}分, {result.project_b}={dim.score_b}分\n\n"

        md += "\n## 改进建议\n\n"
        for i, rec in enumerate(result.recommendations, 1):
            md += f"{i}. {rec}\n"

        return md

    def _generate_compare_html(self, result: ComparisonResult, data_a: dict, data_b: dict) -> str:
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
        for dim in result.dimensions:
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

        recommendations_list = ""
        for i, rec in enumerate(result.recommendations, 1):
            recommendations_list += f"<li>{rec}</li>"

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
        
        <div class="card recommendations">
            <h3>改进建议</h3>
            <ul>
                {recommendations_list}
            </ul>
        </div>
    </div>
</body>
</html>"""
