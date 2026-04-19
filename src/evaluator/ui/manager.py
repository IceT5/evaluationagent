# UI Manager - 统一管理 CLI 输出和追踪

import os
import sys
import time
from typing import Optional, Any
from contextlib import contextmanager

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
    from rich.table import Table
    from rich.text import Text
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

from .components import StepStatus, render_progress, render_step_item
from .tracer import LangSmithTracer, get_tracer


class UIManager:
    DEFAULT_STEPS = [
        {"id": "input", "name": "输入处理", "status": StepStatus.PENDING},
        {"id": "loader", "name": "加载项目", "status": StepStatus.PENDING},
        {"id": "cicd", "name": "CI/CD 分析", "status": StepStatus.PENDING},
        {"id": "reviewer", "name": "验证报告", "status": StepStatus.PENDING},
        {"id": "reporter", "name": "生成报告", "status": StepStatus.PENDING},
        {"id": "finish", "name": "保存完成", "status": StepStatus.PENDING},
    ]
    
    def __init__(self, use_rich: bool = True):
        self.use_rich = use_rich and RICH_AVAILABLE
        self.console = Console() if self.use_rich else None
        self.tracer = get_tracer()
        self.steps = [s.copy() for s in self.DEFAULT_STEPS]
        self.current_step_index = 0
        self.start_time = time.time()
        self.project_info = {}
        self._progress_bar = None
    
    def init(self, project_name: str = None, project_path: str = None):
        self.project_info = {
            "project_name": project_name or "Unknown",
            "project_path": project_path or "",
            "version_id": None,
        }
        self.start_time = time.time()
        self._render_header()
    
    def set_version(self, version_id: str):
        self.project_info["version_id"] = version_id
    
    def _render_header(self):
        if not self.use_rich:
            print("\n" + "=" * 60)
            print("  CI/CD 架构评估")
            print("=" * 60)
            return
        
        from rich.box import ROUNDED
        title = Text(" CI/CD 架构评估 ", style="bold cyan")
        
        table = Table(box=ROUNDED, show_header=False, padding=(0, 2))
        table.add_column(style="dim")
        table.add_column()
        
        pn = self.project_info.get("project_name", "初始化中...")
        pp = self._truncate_path(self.project_info.get("project_path", ""))
        vid = self.project_info.get("version_id", "初始化中...")
        
        table.add_row("Project", pn)
        table.add_row("Path", pp)
        table.add_row("Version", vid)
        
        self.console.print(Panel(table, title=title, padding=(1, 2), style="cyan"))
    
    def _truncate_path(self, path: str, max_len: int = 50) -> str:
        if len(path) <= max_len:
            return path
        return "..." + path[-(max_len-3):]
    
    def _render_steps(self):
        if not self.use_rich:
            return
        
        from rich.box import ROUNDED
        lines = []
        for i, step in enumerate(self.steps):
            status_icon = {
                StepStatus.PENDING: "[ ]",
                StepStatus.RUNNING: "[>]",
                StepStatus.COMPLETED: "[x]",
                StepStatus.ERROR: "[!]",
            }.get(step["status"], "[ ]")
            
            status_color = {
                StepStatus.PENDING: "dim",
                StepStatus.RUNNING: "yellow",
                StepStatus.COMPLETED: "green",
                StepStatus.ERROR: "red",
            }.get(step["status"], "dim")
            
            prefix = "  " if i > 0 else ">"
            line = f"{prefix} {status_icon} [{status_color}]{step['name']}[/{status_color}]"
            
            if step.get("detail"):
                line += f"\n   - {step['detail']}"
            
            lines.append(line)
        
        content = "\n".join(lines)
        self.console.print(Panel(content, box=ROUNDED, padding=(1, 2), style="cyan"))
    
    def _render_progress_line(self):
        completed = sum(1 for s in self.steps if s["status"] == StepStatus.COMPLETED)
        total = len(self.steps)
        progress_str = render_progress(completed, total)
        
        if self.use_rich:
            self.console.print(progress_str)
        else:
            print(progress_str)
    
    @contextmanager
    def step(self, step_id: str, detail: str = None):
        step = self._get_step(step_id)
        if not step:
            yield
            return
        
        step["status"] = StepStatus.RUNNING
        if detail:
            step["detail"] = detail
        
        self._render_steps()
        
        start_time = time.time()
        error = None
        result = None
        
        with self.tracer.trace_node(step["name"], {"detail": detail}):
            try:
                yield
            except Exception as e:
                error = e
                step["status"] = StepStatus.ERROR
                step["detail"] = str(e)
                raise
            finally:
                elapsed = time.time() - start_time
                if error is None:
                    step["status"] = StepStatus.COMPLETED
                    step["detail"] = f"完成 ({elapsed:.1f}s)"
                self._render_steps()
    
    def step_start(self, step_id: str, detail: str = None):
        step = self._get_step(step_id)
        if step:
            step["status"] = StepStatus.RUNNING
            if detail:
                step["detail"] = detail
            self._render_steps()
    
    def step_update(self, step_id: str, detail: str = None):
        step = self._get_step(step_id)
        if step and detail:
            step["detail"] = detail
    
    def step_complete(self, step_id: str, detail: str = None):
        step = self._get_step(step_id)
        if step:
            step["status"] = StepStatus.COMPLETED
            if detail:
                step["detail"] = detail
            self._render_steps()
    
    def step_error(self, step_id: str, error: str):
        step = self._get_step(step_id)
        if step:
            step["status"] = StepStatus.ERROR
            step["detail"] = error
            self._render_steps()
    
    def _get_step(self, step_id: str) -> Optional[dict]:
        for step in self.steps:
            if step["id"] == step_id:
                return step
        return None
    
    def finish(self, result: dict = None):
        self.step_complete("finish", "全部完成")
        
        elapsed = time.time() - self.start_time
        
        if not self.use_rich:
            print("\n" + "=" * 60)
            print("  执行完成")
            print("=" * 60)
            print(f"  耗时: {elapsed:.1f}s")
            return
        
        from rich.box import ROUNDED
        table = Table(box=ROUNDED, show_header=False, padding=(0, 2))
        table.add_column(style="green bold", width=15)
        table.add_column()
        
        if result:
            stats = result.get("stats", {})
            for key, value in stats.items():
                table.add_row(key, str(value))
        
        if result and result.get("report_path"):
            table.add_row("Report", result["report_path"])
        
        table.add_row("Duration", f"{elapsed:.1f}s")
        
        self.console.print(Panel(table, title="Complete", padding=(1, 2), style="green"))
    
    def error(self, message: str):
        if not self.use_rich:
            print(f"\nError: {message}")
            return
        
        from rich.box import ROUNDED
        self.console.print(Panel(f"  {message}", title="Error", box=ROUNDED, padding=(1, 2), style="bold red"))
    
    def info(self, message: str):
        if not self.use_rich:
            print(f"  {message}")
            return
        
        self.console.print(f"  {message}", style="dim")
    
    def warn(self, message: str):
        if not self.use_rich:
            print(f"  Warning: {message}")
            return
        
        self.console.print(f"  Warning: {message}", style="yellow")
    
    def success(self, message: str):
        if not self.use_rich:
            print(f"  {message}")
            return
        
        self.console.print(f"  {message}", style="green")
    
    def print(self, message: str):
        if self.use_rich:
            self.console.print(message)
        else:
            print(message)
    
    def clear(self):
        if self.use_rich:
            self.console.clear()


_ui_manager: Optional[UIManager] = None


def get_ui_manager() -> UIManager:
    global _ui_manager
    if _ui_manager is None:
        _ui_manager = UIManager()
    return _ui_manager


def init_ui_manager(**kwargs) -> UIManager:
    global _ui_manager
    _ui_manager = UIManager(**kwargs)
    return _ui_manager
