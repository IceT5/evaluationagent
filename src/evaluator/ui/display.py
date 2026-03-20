# 结果展示

from typing import Optional, Any


def display_result(result: dict, ui=None):
    if not ui:
        _display_result_console(result)
        return
    
    ui.finish(result)


def _display_result_console(result: dict):
    print("\n" + "=" * 60)
    print("  执行完成")
    print("=" * 60)
    
    stats = result.get("stats", {})
    if stats:
        print("\n统计数据:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
    
    if result.get("report_path"):
        print(f"\n报告: {result['report_path']}")
    
    if result.get("errors"):
        print("\n错误:")
        for err in result["errors"]:
            print(f"  - {err}")


def display_comparison_result(result: dict, ui=None):
    if not ui:
        _display_comparison_console(result)
        return
    
    ui.console.print("\n")
    
    table = ui.console.create_table(title="对比结果")
    table.add_column("维度", style="cyan")
    table.add_column(result.get("project_a", "A"), style="blue")
    table.add_column(result.get("project_b", "B"), style="green")
    table.add_column("胜出", style="yellow")
    
    for dim in result.get("dimension_results", []):
        winner = dim.get("winner", "N/A")
        winner_name = result.get("project_a") if winner == "A" else (
            result.get("project_b") if winner == "B" else "平手"
        )
        table.add_row(
            dim.get("name", ""),
            f"{dim.get('score_a', 0)}",
            f"{dim.get('score_b', 0)}",
            winner_name
        )
    
    ui.console.print(table)


def _display_comparison_console(result: dict):
    print("\n" + "=" * 60)
    print(f"  对比结果: {result.get('project_a')} vs {result.get('project_b')}")
    print("=" * 60)
    
    for dim in result.get("dimension_results", []):
        winner = dim.get("winner", "N/A")
        winner_name = result.get("project_a") if winner == "A" else (
            result.get("project_b") if winner == "B" else "平手"
        )
        print(f"\n{dim.get('name')}: {result.get('project_a')}={dim.get('score_a')} | "
              f"{result.get('project_b')}={dim.get('score_b')} | 胜出: {winner_name}")
    
    if result.get("recommendations"):
        print("\n改进建议:")
        for i, rec in enumerate(result.get("recommendations"), 1):
            print(f"  {i}. {rec}")
