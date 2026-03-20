# CLI 命令处理器

import re
import os
import sys
import time
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

from evaluator.core import (
    analyze_project,
    compare_projects,
    list_projects,
    get_project,
    delete_project,
    list_analyzers,
    get_storage_info,
)
from evaluator.core.types import AnalysisResult, ComparisonResult, ProjectInfo


class CommandParser:
    """命令解析器"""
    
    COMMANDS = {
        "analyze": r"^/?analyze(?:\s+(?P<type>\w+))?(?:\s+(?P<path>.+))?$",
        "compare": r"^/?compare(?:\s+(?P<project_a>.+?))?(?:\s+(?P<project_b>.+?))?(?:\s+--dim(?:\s+(?P<dimensions>.+)))?$",
        "list": r"^/?list(?:\s+--all)?$",
        "show": r"^/?show(?:\s+(?P<name>.+?))?(?:\s+--version(?:\s+(?P<version>.+)))?$",
        "delete": r"^/?delete(?:\s+(?P<name>.+?))?(?:\s+--version(?:\s+(?P<version>.+)))?$",
        "analyzers": r"^/?analyzers$",
        "help": r"^/?help(?:\s+(?P<topic>.+))?$",
        "version": r"^/?version$",
        "quit": r"^/?(?:quit|exit)$",
        "clear": r"^/?clear$",
    }
    
    @classmethod
    def parse(cls, line: str) -> Tuple[Optional[str], Dict[str, Any]]:
        """解析命令，返回 (command, args)"""
        line = line.strip()
        
        if not line:
            return None, {}
        
        # 匹配命令
        for cmd, pattern in cls.COMMANDS.items():
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                return cmd, match.groupdict() or {}
        
        return None, {}


class CommandHandler:
    """命令处理器"""
    
    VERSION = "1.0.0"
    
    def __init__(self, output_func=None):
        self.output_func = output_func or print
    
    def handle(self, command: str, args: Dict[str, Any]) -> bool:
        """处理命令，返回是否退出"""
        handlers = {
            "analyze": self._handle_analyze,
            "compare": self._handle_compare,
            "list": self._handle_list,
            "show": self._handle_show,
            "delete": self._handle_delete,
            "analyzers": self._handle_analyzers,
            "help": self._handle_help,
            "version": self._handle_version,
            "quit": self._handle_quit,
            "clear": self._handle_clear,
        }
        
        handler = handlers.get(command)
        if handler:
            return handler(args)
        
        self.output_func(f"未知命令: {command}")
        return False
    
    def _handle_analyze(self, args: Dict[str, Any]) -> bool:
        """处理 /analyze 命令"""
        analyzer_type = args.get("type") or "cicd"
        path = args.get("path") or ""
        
        if not path:
            self.output_func("用法: /analyze [type] <path>")
            self.output_func("  type: 分析类型 (默认: cicd)")
            self.output_func("  path: 项目路径")
            return False
        
        # 验证路径
        project_path = Path(path)
        if not project_path.exists():
            self.output_func(f"错误: 路径不存在: {path}")
            return False
        
        if not project_path.is_dir():
            self.output_func(f"错误: 路径不是目录: {path}")
            return False
        
        # 构建 LLM 配置
        llm_config = None
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            llm_config = {
                "api_key": api_key,
                "base_url": os.getenv("OPENAI_BASE_URL"),
                "model": os.getenv("DEFAULT_MODEL", "glm-4"),
            }
        
        self.output_func(f"\n开始分析: {project_path.name}")
        self.output_func("-" * 50)
        
        start_time = time.time()
        
        result = analyze_project(
            path=str(project_path),
            types=[analyzer_type] if analyzer_type else ["cicd"],
            llm_config=llm_config,
        )
        
        elapsed = time.time() - start_time
        
        if result.success:
            self.output_func(f"\n[OK] 分析完成")
            self.output_func(f"  项目: {result.project_name}")
            self.output_func(f"  版本: {result.version_id}")
            self.output_func(f"  耗时: {elapsed:.1f}s")
            
            if result.stats:
                stats = result.stats
                self.output_func(f"  工作流: {stats.get('workflows_count', 0)}")
                self.output_func(f"  Jobs: {stats.get('jobs_count', 0)}")
        else:
            self.output_func(f"\n[FAIL] 分析失败")
            for err in result.errors:
                self.output_func(f"  - {err}")
        
        return False
    
    def _handle_compare(self, args: Dict[str, Any]) -> bool:
        """处理 /compare 命令"""
        project_a = args.get("project_a") or ""
        project_b = args.get("project_b") or ""
        dimensions_str = args.get("dimensions") or ""
        
        if not project_a or not project_b:
            self.output_func("用法: /compare <project_a> <project_b> [--dim dimensions]")
            return False
        
        self.output_func(f"\n开始对比: {project_a} vs {project_b}")
        self.output_func("-" * 50)
        
        dimensions = None
        if dimensions_str:
            dimensions = [d.strip() for d in dimensions_str.split(",")]
        
        api_key = os.getenv("OPENAI_API_KEY")
        llm_config = None
        if api_key:
            llm_config = {
                "api_key": api_key,
                "base_url": os.getenv("OPENAI_BASE_URL"),
                "model": os.getenv("DEFAULT_MODEL", "glm-4"),
            }
        else:
            self.output_func("  警 未配置 LLM API Key，将使用规则分析")
        
        result = compare_projects(
            project_a=project_a,
            project_b=project_b,
            dimensions=dimensions,
            llm_config=llm_config,
        )
        
        if result.success:
            self.output_func(f"\n[OK] 对比完成")
            self.output_func(f"  对比ID: {result.comparison_id}")
            
            self.output_func("\n维度得分:")
            for dim in result.dimensions:
                winner = dim.get("winner", "N/A")
                winner_name = project_a if winner == "A" else (project_b if winner == "B" else "平手")
                self.output_func(f"  {dim['name']}: {project_a}={dim['score_a']:.0f} | "
                               f"{project_b}={dim['score_b']:.0f} | 胜出: {winner_name}")
            
            if result.semantic_diff:
                self.output_func("\n" + "=" * 50)
                self.output_func("LLM 架构分析:")
                self.output_func("-" * 50)
                self.output_func(result.semantic_diff)
                self.output_func("=" * 50)
            
            if result.summary:
                self.output_func("\n总结:")
                self.output_func(result.summary)
            
            if result.recommendations:
                self.output_func("\n建议:")
                for i, rec in enumerate(result.recommendations[:5], 1):
                    self.output_func(f"  {i}. {rec}")
        else:
            self.output_func(f"\n[FAIL] 对比失败")
            self.output_func(f"  {result.summary}")
        
        return False
    
    def _handle_list(self, args: Dict[str, Any]) -> bool:
        """处理 /list 命令"""
        show_all = "--all" in args or args.get("all") == "--all"
        
        info = get_storage_info()
        projects = list_projects()
        
        self.output_func(f"\n存储概览")
        self.output_func("-" * 50)
        self.output_func(f"  项目数量: {info['project_count']}")
        self.output_func(f"  对比数量: {info['comparison_count']}")
        self.output_func(f"  总大小: {info['total_size_mb']} MB")
        
        if projects:
            self.output_func(f"\n已保存的项目:")
            self.output_func(f"{'名称':<30} {'版本':<15} {'工作流':<10}")
            self.output_func("-" * 60)
            
            for p in projects:
                detail = get_project(p.name)
                workflows = 0
                if detail and detail.versions:
                    workflows = detail.versions[-1].get("workflows", 0) if detail.versions else 0
                display_name = p.display_name or p.name
                latest_version = p.latest_version or "N/A"
                self.output_func(f"{display_name:<30} {latest_version:<15} {workflows}")
        else:
            self.output_func("\n暂无已保存的项目")
        
        return False
    
    def _handle_show(self, args: Dict[str, Any]) -> bool:
        """处理 /show 命令"""
        name = args.get("name") or ""
        version = args.get("version")
        
        if not name:
            self.output_func("用法: /show <name> [--version version_id]")
            return False
        
        detail = get_project(name)
        
        if not detail:
            self.output_func(f"项目不存在: {name}")
            return False
        
        self.output_func(f"\n项目详情: {detail.display_name}")
        self.output_func("-" * 50)
        self.output_func(f"  名称: {detail.name}")
        self.output_func(f"  版本数: {len(detail.versions)}")
        
        if detail.source_url:
            self.output_func(f"  来源: {detail.source_url}")
        if detail.source_path:
            self.output_func(f"  路径: {detail.source_path}")
        
        if detail.versions:
            self.output_func(f"\n版本历史:")
            for v in reversed(detail.versions):
                analyzed = v.get("analyzed_at", "")
                if len(analyzed) > 19:
                    analyzed = analyzed[:19]
                self.output_func(f"  - {v.get('version_id')}")
                self.output_func(f"    时间: {analyzed}")
                self.output_func(f"    工作流: {v.get('workflows', 0)}")
        
        return False
    
    def _handle_delete(self, args: Dict[str, Any]) -> bool:
        """处理 /delete 命令"""
        name = args.get("name") or ""
        version = args.get("version")
        
        if not name:
            self.output_func("用法: /delete <name> [--version version_id]")
            self.output_func("  注意: 删除后将无法恢复")
            return False
        
        if delete_project(name, version):
            if version:
                self.output_func(f"[OK] 已删除项目 {name} 的版本 {version}")
            else:
                self.output_func(f"[OK] 已删除项目 {name} 及其所有版本")
        else:
            self.output_func(f"项目不存在: {name}")
        
        return False
    
    def _handle_analyzers(self, args: Dict[str, Any]) -> bool:
        """处理 /analyzers 命令"""
        analyzers = list_analyzers()
        
        self.output_func("\n可用的分析器:")
        self.output_func("-" * 50)
        
        for a in analyzers:
            status = "[x]" if a.enabled else "[ ]"
            self.output_func(f"  {status} {a.name:<15} {a.description}")
        
        return False
    
    def _handle_help(self, args: Dict[str, Any]) -> bool:
        """处理 /help 命令"""
        topic = args.get("topic")
        
        if topic == "analyze":
            self.output_func("\n/analyze 命令")
            self.output_func("-" * 50)
            self.output_func("用法: /analyze [type] <path>")
            self.output_func("")
            self.output_func("示例:")
            self.output_func("  /analyze ./my-project")
            self.output_func("  /analyze cicd ./my-project")
            self.output_func("")
            self.output_func("可用类型: cicd (默认)")
        elif topic == "compare":
            self.output_func("\n/compare 命令")
            self.output_func("-" * 50)
            self.output_func("用法: /compare <project_a> <project_b> [--dim dimensions]")
            self.output_func("")
            self.output_func("示例:")
            self.output_func("  /compare project-a project-b")
            self.output_func("  /compare project-a project-b --dim complexity,best_practices")
            self.output_func("  (默认使用 LLM 进行语义分析)")
        elif topic == "list":
            self.output_func("\n/list 命令")
            self.output_func("-" * 50)
            self.output_func("用法: /list [--all]")
            self.output_func("")
            self.output_func("示例:")
            self.output_func("  /list")
            self.output_func("  /list --all")
        else:
            self._print_help()
        
        return False
    
    def _print_help(self) -> None:
        """打印帮助信息"""
        self.output_func(f"""
╭──────────────────────────────────────────────────────────────╮
│  eval-agent v{self.VERSION} - CI/CD 架构评估工具                        │
╰──────────────────────────────────────────────────────────────╯

支持的命令：

  /analyze [type] <path>
              分析项目的 CI/CD 架构
              type: 分析类型 (默认: cicd)
              示例: /analyze ./my-project

  /compare <a> <b> [--dim dims]
              对比两个项目的 CI 架构
              示例: /compare project-a project-b

  /list [--all]  列出已保存的项目

  /show <name>   显示项目详情
              示例: /show my-project

  /delete <name> 删除项目
              示例: /delete my-project

  /analyzers     列出可用的分析器

  /help [topic]  显示帮助
              示例: /help analyze

  /version       显示版本信息

  /clear         清除屏幕

  /quit, /exit   退出程序
""")
    
    def _handle_version(self, args: Dict[str, Any]) -> bool:
        """处理 /version 命令"""
        self.output_func(f"eval-agent v{self.VERSION}")
        return False
    
    def _handle_quit(self, args: Dict[str, Any]) -> bool:
        """处理退出命令"""
        self.output_func("再见!")
        return True
    
    def _handle_clear(self, args: Dict[str, Any]) -> bool:
        """处理清除屏幕命令"""
        os.system("cls" if os.name == "nt" else "clear")
        return False


def run_cli():
    """运行 CLI"""
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import InMemoryHistory
        from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
        from prompt_toolkit.completion import WordCompleter
        
        # 命令补全
        commands = ["analyze", "compare", "list", "show", "delete", "analyzers", "help", "version", "quit", "exit", "clear"]
        completer = WordCompleter(commands, ignore_case=True)
        
        session = PromptSession(
            "eval-agent> ",
            completer=completer,
            history=InMemoryHistory(),
            auto_suggest=AutoSuggestFromHistory(),
        )
        
        handler = CommandHandler()
        
        print(f"""
╭──────────────────────────────────────────────────────────────╮
│  eval-agent v1.0.0 - CI/CD 架构评估工具                        │
╰──────────────────────────────────────────────────────────────╯
""")
        
        while True:
            try:
                text = session.prompt()
            except KeyboardInterrupt:
                print("\n再见!")
                break
            
            parser = CommandParser()
            command, args = parser.parse(text)
            
            if not command:
                continue
            
            should_quit = handler.handle(command, args)
            if should_quit:
                break
    
    except ImportError:
        print("提示: 安装 prompt_toolkit 以获得更好的交互体验")
        print("      pip install prompt_toolkit")
        print()
        
        run_cli_simple()


def run_cli_simple():
    """简单的 CLI（无 prompt_toolkit）"""
    handler = CommandHandler()
    
    print(f"""
╭──────────────────────────────────────────────────────────────╮
│  eval-agent v1.0.0 - CI/CD 架构评估工具                        │
╰──────────────────────────────────────────────────────────────╯
""")
    
    while True:
        try:
            text = input("eval-agent> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n再见!")
            break
        
        parser = CommandParser()
        command, args = parser.parse(text)
        
        if not command:
            continue
        
        should_quit = handler.handle(command, args)
        if should_quit:
            break


if __name__ == "__main__":
    run_cli()
