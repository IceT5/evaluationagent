# Rich 组件封装

from typing import Optional, Any
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.text import Text
from rich.live import Live

def render_header(title: str, subtitle: str = None) -> Panel:
    content_parts = []
    
    title_text = Text(f"  {title}  ", style="bold cyan")
    content_parts.append(title_text)
    
    if subtitle:
        content_parts.append(Text(f"\n  {subtitle}", style="dim"))
    
    return Panel(
        "\n".join(str(p) for p in content_parts) if isinstance(content_parts[0], str) else content_parts,
        title=title,
        style="cyan",
        padding=(1, 1),
    )


def render_project_info(project_name: str, project_path: str, version_id: str) -> Table:
    table = Table(box=None, show_header=False, padding=(0, 2))
    table.add_column(style="dim")
    table.add_column()
    
    table.add_row("📁 项目", project_name)
    table.add_row("📂 路径", project_path[:60] + "..." if len(project_path) > 60 else project_path)
    table.add_row("📅 版本", version_id or "初始化中...")
    
    return table


def render_progress(current: int, total: int, step_name: str = "") -> str:
    bar_length = 40
    filled = int(bar_length * current / total) if total > 0 else 0
    bar = "-" * filled + " " * (bar_length - filled)
    
    percent = int(100 * current / total) if total > 0 else 0
    return f" [{bar}] {percent}%  {step_name}"


def render_step_item(step_name: str, status: str, detail: str = None) -> str:
    status_icon = {
        "pending": "○",
        "running": "⏳",
        "completed": "✓",
        "error": "✗",
    }.get(status, "○")
    
    status_color = {
        "pending": "dim",
        "running": "yellow",
        "completed": "green",
        "error": "red",
    }.get(status, "dim")
    
    line = f" {status_icon} [{status_color}]{step_name}[/{status_color}]"
    
    if detail:
        line += f"\n   └─ {detail}"
    
    return line


def render_step_list(steps: list[dict]) -> Panel:
    lines = []
    for step in steps:
        lines.append(render_step_item(
            step.get("name", ""),
            step.get("status", "pending"),
            step.get("detail", "")
        ))
    
    content = "\n".join(lines) if lines else "  无步骤"
    
    return Panel(
        content,
        title="执行步骤",
        style="cyan",
        padding=(1, 2),
    )


def render_summary(data: dict) -> Panel:
    rows = []
    
    stats = data.get("stats", {})
    if stats:
        row = []
        for key, value in stats.items():
            row.append(f"{key}: {value}")
        rows.append("    " + "  |  ".join(row))
    
    if data.get("report_path"):
        rows.append(f"\n  Report: {data['report_path']}")
    
    content = "\n".join(rows) if rows else "无统计数据"
    
    return Panel(
        content,
        title="执行结果",
        style="green",
        padding=(1, 2),
    )


def render_error(error: str, title: str = "错误") -> Panel:
    return Panel(
        f"  {error}",
        title=title,
        style="bold red",
        padding=(1, 2),
    )


def render_success(message: str, title: str = "成功") -> Panel:
    return Panel(
        f"  {message}",
        title=title,
        style="bold green",
        padding=(1, 2),
    )


def create_progress_bar() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=None,
    )


class StepStatus:
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


def format_bytes(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"
