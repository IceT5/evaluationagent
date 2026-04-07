# CLI 命令处理器

import re
import os
import sys
import time
import signal
from pathlib import Path
from typing import TYPE_CHECKING, Optional, List, Tuple, Dict, Any

if TYPE_CHECKING:
    from evaluator.agents.intent_parser_agent import ParsedIntent

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

from evaluator.core import (
    list_projects,
)
from evaluator.agents.intent_parser_agent import IntentParserAgent, Intent, ParsedIntent
from evaluator.skills import UrlParser
from evaluator.cli.context import ConversationContext, get_context
from storage import StorageManager

try:
    from evaluator.llm import LLMClient
    HAS_LLM = True
except ImportError:
    HAS_LLM = False
    LLMClient = None

try:
    from evaluator.core.interrupt import interrupt_controller, InterruptException
except ImportError:
    interrupt_controller = None
    InterruptException = Exception


from prompt_toolkit.completion import Completer, Completion


def setup_interrupt_handler():
    """设置中断信号处理器"""
    if interrupt_controller is None:
        return
    
    def handler(signum, frame):
        print("\n\n⚠️  正在中断...")
        interrupt_controller.interrupt("用户按下 Ctrl+C")
    
    signal.signal(signal.SIGINT, handler)


class CommandCompleter(Completer):
    """命令补全器 - 只有输入 / 时才显示命令列表"""
    
    def __init__(self, commands: List[str]):
        super().__init__()
        self.commands = commands
    
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        
        # 只有以 / 开头时才提供补全
        if text.startswith('/'):
            word = text[1:]  # 去掉 /
            for cmd in self.commands:
                if cmd.startswith(word):
                    yield Completion(
                        text='/' + cmd,
                        start_position=-len(text),
                        display='/' + cmd,
                    )
    
    async def get_completions_async(self, document, complete_event):
        """异步方法（新版本 prompt_toolkit）"""
        for completion in self.get_completions(document, complete_event):
            yield completion


class CommandParser:
    """命令解析器"""
    
    COMMANDS = {
        "analyze": r"^/analyze(?:\s+(?P<type>\w+))?(?:\s+(?P<path>.+))?$",
        "compare": r"^/compare(?:\s+(?P<project_a>.+?))?(?:\s+(?P<project_b>.+?))?(?:\s+--dim(?:\s+(?P<dimensions>.+)))?$",
        "list": r"^/list(?:\s+--all)?$",
        "show": r"^/show(?:\s+(?P<name>.+?))?(?:\s+--version(?:\s+(?P<version>.+)))?$",
        "delete": r"^/delete(?:\s+(?P<name>.+?))?(?:\s+--version(?:\s+(?P<version>.+)))?$",
        "analyzers": r"^/analyzers$",
        "insights": r"^/insights(?:\s+(?P<name>.+))?$",
        "recommend": r"^/recommend(?:\s+(?P<name>.+))?$",
        "similar": r"^/similar(?:\s+(?P<name>.+))?$",
        "help": r"^/help(?:\s+(?P<topic>.+))?$",
        "version": r"^/version$",
        "quit": r"^/(?:quit|exit)$",
        "clear": r"^/clear$",
    }
    
    @classmethod
    def parse(cls, line: str) -> Tuple[Optional[str], Dict[str, Any]]:
        """解析命令，返回 (command, args)"""
        line = line.strip()
        
        if not line:
            return None, {}
        
        # 匹配命令（必须以 / 开头）
        for cmd, pattern in cls.COMMANDS.items():
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                return cmd, match.groupdict() or {}
        
        return None, {}


class CommandHandler:
    """命令处理器
    
    架构原则:
    1. 核心命令(analyze/compare)通过LangGraph执行
    2. 简单命令(list/show/delete)直接调用core函数
    3. 智能Agent命令(insights/recommend/similar)通过BackgroundTasks执行
    """
    
    VERSION = "0.2.0"
    
    def __init__(self, output_func=None, llm_client=None):
        """
        Args:
            output_func: 输出函数
            llm_client: LLM 客户端
        """
        self.output_func = output_func or print
        self.llm_client = llm_client
        self.intent_parser = IntentParserAgent(llm=llm_client) if llm_client else IntentParserAgent()
        self.context = get_context()
        self._graph = None
    
    @property
    def graph(self):
        """延迟加载LangGraph实例"""
        if self._graph is None:
            from evaluator.core.graphs import create_main_graph
            llm_config = None
            if self.llm_client:
                llm_config = {
                    "api_key": os.getenv("OPENAI_API_KEY"),
                    "base_url": os.getenv("OPENAI_BASE_URL"),
                    "model": getattr(self.llm_client, 'model', None),
                }
            self._graph = create_main_graph(llm_config=llm_config)
        return self._graph
    
    def handle(self, command: str, args: Dict[str, Any]) -> bool:
        """处理命令，返回是否退出"""
        handlers = {
            "analyze": self._handle_analyze,
            "compare": self._handle_compare,
            "list": self._handle_list,
            "show": self._handle_show,
            "delete": self._handle_delete,
            "analyzers": self._handle_analyzers,
            "insights": self._handle_insights,
            "recommend": self._handle_recommend,
            "similar": self._handle_similar,
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
        """处理 /analyze 命令 - 使用 LangGraph 统一工作流"""
        analyzer_type = args.get("type") or "cicd"
        user_input = args.get("path") or ""
        
        if not user_input:
            self.output_func("用法: /analyze [type] <path|url>")
            self.output_func("  type: 分析类型 (默认: cicd)")
            self.output_func("  path: 本地项目路径")
            self.output_func("  url:  GitHub/GitLab 仓库地址")
            self.output_func("")
            self.output_func("示例:")
            self.output_func("  /analyze ./my-project")
            self.output_func("  /analyze cicd https://github.com/owner/repo")
            return False
        
        llm_config = None
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            llm_config = {"api_key": api_key, "base_url": os.getenv("OPENAI_BASE_URL")}
        
        known_projects = [p.name for p in list_projects()]
        
        initial_state = {
            "user_input": user_input,
            "intent": "analyze",
            "params": {
                "project": user_input,
                "analyzer_type": analyzer_type,
            },
            "orchestrator_decision": {
                "intent": "analyze",
                "params": {"project": user_input, "analyzer_type": analyzer_type},
                "confidence": 1.0,
                "needs_clarification": False,
                "next_step": "input",
            },
            "llm_config": llm_config or {},
            "known_projects": known_projects,
            "context": {"last_project": self.context.last_project},
            "current_step": "",
            "completed_steps": [],
            "errors": [],
            "warnings": [],
        }
        
        self.output_func(f"\n开始分析: {user_input}")
        self.output_func("-" * 50)
        self.output_func("  [使用 LangGraph 工作流]")
        
        if interrupt_controller:
            interrupt_controller.reset()
        
        start_time = time.time()
        
        final_state = None
        try:
            final_state = self.graph.invoke(initial_state)
        except InterruptException as e:
            elapsed = time.time() - start_time
            self.output_func(f"\n⚠️  任务已中断")
            self.output_func(f"  原因: {e}")
            self.output_func(f"  已运行时间: {elapsed:.1f}s")
            if interrupt_controller:
                summary = interrupt_controller.get_interrupt_summary()
                if summary.get("current_node"):
                    self.output_func(f"  当前节点: {summary['current_node']}")
                if summary.get("completed_nodes"):
                    nodes_str = ", ".join(summary["completed_nodes"])
                    self.output_func(f"  已完成节点: {nodes_str}")
            return False
        
        elapsed = time.time() - start_time
        
        errors = final_state.get("errors", [])
        if errors:
            self.output_func(f"\n[FAIL] 分析失败")
            for err in errors:
                self.output_func(f"  - {err}")
            return False
        
        project_name = final_state.get("project_name") or final_state.get("display_name") or user_input
        version_id = final_state.get("storage_version_id", "N/A")
        cicd_analysis = final_state.get("cicd_analysis", {})
        
        self.output_func(f"\n[OK] 分析完成")
        self.output_func(f"  项目: {project_name}")
        self.output_func(f"  版本: {version_id}")
        self.output_func(f"  耗时: {elapsed:.1f}s")
        
        if cicd_analysis:
            self.output_func(f"  工作流: {cicd_analysis.get('workflows_count', 0)}")
            self.output_func(f"  Jobs: {cicd_analysis.get('jobs_count', 0)}")
        
        if final_state.get("report_html"):
            self.output_func(f"  报告: {final_state.get('report_html')}")
        
        self.context.last_project = project_name
        
        return False
    
    def _handle_compare(self, args: Dict[str, Any]) -> bool:
        """处理 /compare 命令 - 使用 LangGraph 统一工作流"""
        project_a = args.get("project_a") or ""
        project_b = args.get("project_b") or ""
        dimensions_str = args.get("dimensions") or ""
        
        if not project_a or not project_b:
            self.output_func("用法: /compare <project_a> <project_b> [--dim dimensions]")
            return False
        
        dimensions = None
        if dimensions_str:
            dimensions = [d.strip() for d in dimensions_str.split(",")]
        
        api_key = os.getenv("OPENAI_API_KEY")
        llm_config = None
        if api_key:
            llm_config = {
                "api_key": api_key,
                "base_url": os.getenv("OPENAI_BASE_URL"),
            }
        else:
            self.output_func("  警 未配置 LLM API Key，将使用规则分析")
        
        initial_state = {
            "user_input": f"/compare {project_a} {project_b}",
            "intent": "compare",
            "params": {
                "project_a": project_a,
                "project_b": project_b,
                "dimensions": dimensions,
            },
            "orchestrator_decision": {
                "intent": "compare",
                "params": {"project_a": project_a, "project_b": project_b, "dimensions": dimensions},
                "confidence": 1.0,
                "needs_clarification": False,
                "next_step": "compare",
            },
            "llm_config": llm_config or {},
            "known_projects": [p.name for p in list_projects()],
            "context": {"last_project": self.context.last_project},
            "project_a": project_a,
            "project_b": project_b,
            "dimensions": dimensions,
            "current_step": "",
            "completed_steps": [],
            "errors": [],
            "warnings": [],
        }
        
        self.output_func(f"\n开始对比: {project_a} vs {project_b}")
        self.output_func("-" * 50)
        self.output_func("  [使用 LangGraph 工作流]")
        
        start_time = time.time()
        
        final_state = self.graph.invoke(initial_state)
        elapsed = time.time() - start_time
        
        errors = final_state.get("errors", [])
        if errors:
            self.output_func(f"\n[FAIL] 对比失败")
            for err in errors:
                self.output_func(f"  - {err}")
            return False
        
        comparison_result = final_state.get("comparison_result", {})
        
        if comparison_result:
            self.output_func(f"\n[OK] 对比完成")
            self.output_func(f"  耗时: {elapsed:.1f}s")
            
            dimensions_data = comparison_result.get("dimensions", [])
            if dimensions_data:
                self.output_func("\n维度得分:")
                for dim in dimensions_data:
                    winner = dim.get("winner", "N/A")
                    winner_name = project_a if winner == "A" else (project_b if winner == "B" else "平手")
                    self.output_func(f"  {dim['name']}: {project_a}={dim['score_a']:.0f} | "
                                   f"{project_b}={dim['score_b']:.0f} | 胜出: {winner_name}")
            
            semantic_diff = comparison_result.get("semantic_diff")
            if semantic_diff:
                self.output_func("\n" + "=" * 50)
                self.output_func("LLM 架构分析:")
                self.output_func("-" * 50)
                self.output_func(semantic_diff)
                self.output_func("=" * 50)
            
            summary = comparison_result.get("summary")
            if summary:
                self.output_func("\n总结:")
                self.output_func(summary)
            
            recommendations = comparison_result.get("recommendations", [])
            if recommendations:
                self.output_func("\n建议:")
                for i, rec in enumerate(recommendations[:5], 1):
                    self.output_func(f"  {i}. {rec}")
            
            comp_dir = final_state.get("comparison_dir")
            if comp_dir:
                self.output_func(f"\n报告已保存:")
                self.output_func(f"  {comp_dir}")
        else:
            self.output_func(f"\n[FAIL] 对比失败")
            self.output_func(f"  未获取到对比结果")
        
        return False
    
    def _handle_list(self, args: Dict[str, Any]) -> bool:
        """处理 /list 命令 - 使用 LangGraph"""
        known_projects = [p.name for p in list_projects()]
        context = {"last_project": self.context.last_project}
        
        initial_state = {
            "user_input": "/list",
            "intent": "list",
            "params": args,
            "known_projects": known_projects,
            "context": context,
            "orchestrator_decision": {
                "intent": "list",
                "next_step": "list_handler",
            },
            "current_step": "",
            "errors": [],
            "warnings": [],
            "completed_steps": [],
        }
        
        final_state = self.graph.invoke(initial_state)
        
        list_result = final_state.get("list_result", {})
        storage_info = list_result.get("storage_info", {})
        projects = list_result.get("projects", [])
        
        self.output_func(f"\n存储概览")
        self.output_func("-" * 50)
        self.output_func(f"  项目数量: {storage_info.get('project_count', 0)}")
        self.output_func(f"  对比数量: {storage_info.get('comparison_count', 0)}")
        self.output_func(f"  总大小: {storage_info.get('total_size_mb', 0)} MB")
        
        if projects:
            self.output_func(f"\n已保存的项目:")
            self.output_func(f"{'名称':<30} {'版本':<15} {'工作流':<10}")
            self.output_func("-" * 60)
            
            for p in projects:
                display_name = p.get("display_name") or p.get("name", "N/A")
                latest_version = p.get("latest_version") or "N/A"
                workflows = p.get("workflows", 0)
                self.output_func(f"{display_name:<30} {latest_version:<15} {workflows}")
        else:
            self.output_func("\n暂无已保存的项目")
        
        return False
    
    def _handle_show(self, args: Dict[str, Any]) -> bool:
        """处理 /show 命令 - 使用 LangGraph"""
        name = args.get("name") or ""
        
        if not name:
            self.output_func("用法: /show <name> [--version version_id]")
            return False
        
        known_projects = [p.name for p in list_projects()]
        context = {"last_project": self.context.last_project}
        
        initial_state = {
            "user_input": f"/show {name}",
            "intent": "info",
            "params": {"project": name, "version": args.get("version")},
            "known_projects": known_projects,
            "context": context,
            "orchestrator_decision": {
                "intent": "info",
                "next_step": "info_handler",
            },
            "project_name": name,
            "current_step": "",
            "errors": [],
            "warnings": [],
            "completed_steps": [],
        }
        
        final_state = self.graph.invoke(initial_state)
        
        info_result = final_state.get("info_result", {})
        
        if not info_result.get("success"):
            self.output_func(f"项目不存在: {name}")
            return False
        
        self.output_func(f"\n项目详情: {info_result.get('display_name', name)}")
        self.output_func("-" * 50)
        self.output_func(f"  名称: {info_result.get('name', name)}")
        self.output_func(f"  版本数: {info_result.get('version_count', 0)}")
        
        if info_result.get("source_url"):
            self.output_func(f"  来源: {info_result.get('source_url')}")
        if info_result.get("source_path"):
            self.output_func(f"  路径: {info_result.get('source_path')}")
        
        versions = info_result.get("versions", [])
        if versions:
            self.output_func(f"\n版本历史:")
            for v in reversed(versions):
                analyzed = v.get("analyzed_at", "")
                if len(analyzed) > 19:
                    analyzed = analyzed[:19]
                self.output_func(f"  - {v.get('version_id')}")
                self.output_func(f"    时间: {analyzed}")
                self.output_func(f"    工作流: {v.get('workflows', 0)}")
        
        return False
    
    def _handle_delete(self, args: Dict[str, Any]) -> bool:
        """处理 /delete 命令 - 使用 LangGraph"""
        name = args.get("name") or ""
        version = args.get("version")
        
        if not name:
            self.output_func("用法: /delete <name> [--version version_id]")
            self.output_func("  注意: 删除后将无法恢复")
            return False
        
        known_projects = [p.name for p in list_projects()]
        context = {"last_project": self.context.last_project}
        
        initial_state = {
            "user_input": f"/delete {name}",
            "intent": "delete",
            "params": {"project": name, "version": version},
            "known_projects": known_projects,
            "context": context,
            "orchestrator_decision": {
                "intent": "delete",
                "next_step": "delete_handler",
            },
            "project_name": name,
            "current_step": "",
            "errors": [],
            "warnings": [],
            "completed_steps": [],
        }
        
        final_state = self.graph.invoke(initial_state)
        
        delete_result = final_state.get("delete_result", {})
        
        if delete_result.get("success"):
            if version:
                self.output_func(f"[OK] 已删除项目 {name} 的版本 {version}")
            else:
                self.output_func(f"[OK] 已删除项目 {name} 及其所有版本")
        else:
            self.output_func(f"项目不存在: {name}")
        
        return False
    
    def _handle_insights(self, args: Dict[str, Any]) -> bool:
        """处理 /insights 命令 - 显示智能分析结果"""
        project_name = args.get("name") or self.context.last_project
        
        if not project_name:
            self.output_func("用法: /insights [project_name]")
            self.output_func("  显示项目的智能分析结果（改进建议、相似项目等）")
            return False
        
        from storage import StorageManager
        storage = StorageManager()
        version_dir = storage.get_latest_version_dir(project_name)
        
        initial_state = {
            "user_input": f"/insights {project_name}",
            "intent": "insights",
            "project_name": project_name,
            "storage_dir": str(version_dir) if version_dir else None,
            "current_step": "",
            "completed_steps": [],
            "errors": [],
            "warnings": [],
            "orchestrator_decision": {
                "intent": "insights",
                "next_step": "insights_handler",
            },
        }
        
        final_state = self.graph.invoke(initial_state)
        
        if final_state.get("errors"):
            for err in final_state["errors"]:
                self.output_func(f"  - {err}")
            return False
        
        insights_result = final_state.get("insights_result", {})
        
        if insights_result.get("success"):
            self.output_func(f"\n智能分析结果: {project_name}")
            self.output_func("=" * 50)
            
            recommendations = insights_result.get("recommendations", [])
            if recommendations:
                self.output_func(f"\n改进建议 ({len(recommendations)} 项):")
                for rec in recommendations[:5]:
                    priority = rec.get('priority', 'medium')
                    priority_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(priority, "⚪")
                    self.output_func(f"  {priority_icon} [{priority.upper()}] {rec.get('title', '')}")
                    if rec.get('action'):
                        self.output_func(f"      → {rec.get('action')}")
            
            similar_projects = insights_result.get("similar_projects", [])
            if similar_projects:
                self.output_func(f"\n相似项目 ({len(similar_projects)} 个):")
                for sim in similar_projects[:5]:
                    name = sim.get('name', '')
                    similarity = sim.get('similarity', 0)
                    self.output_func(f"  • {name} (相似度: {similarity:.0%})")
            
            quick_wins = insights_result.get("quick_wins", [])
            if quick_wins:
                self.output_func(f"\n快速改进项:")
                for qw in quick_wins[:3]:
                    self.output_func(f"  ⚡ {qw.get('title', '')}")
                    self.output_func(f"     投入: {qw.get('effort', 'N/A')} | 收益: {qw.get('impact', 'N/A')}")
            
            reflection_result = insights_result.get("reflection_result", {})
            if reflection_result:
                self.output_func(f"\n执行分析:")
                self.output_func(f"  成功率: {reflection_result.get('success_rate', 0):.0%}")
                self.output_func(f"  平均耗时: {reflection_result.get('avg_duration', 0):.1f}s")
                if reflection_result.get('bottlenecks'):
                    self.output_func(f"  瓶颈: {reflection_result['bottlenecks'][0]}")
            
            generated_at = insights_result.get("generated_at")
            if generated_at:
                self.output_func(f"\n生成时间: {generated_at}")
        else:
            self.output_func(insights_result.get("error", "未找到智能分析结果"))
        
        return False
    
    def _handle_recommend(self, args: Dict[str, Any]) -> bool:
        """处理 /recommend 命令 - 显示改进建议"""
        project_name = args.get("name") or self.context.last_project
        
        if not project_name:
            self.output_func("用法: /recommend [project_name]")
            self.output_func("  显示项目的改进建议")
            return False
        
        from storage import StorageManager
        storage = StorageManager()
        version_dir = storage.get_latest_version_dir(project_name)
        
        initial_state = {
            "user_input": f"/recommend {project_name}",
            "intent": "recommend",
            "project_name": project_name,
            "storage_dir": str(version_dir) if version_dir else None,
            "current_step": "",
            "completed_steps": [],
            "errors": [],
            "warnings": [],
            "orchestrator_decision": {
                "intent": "recommend",
                "next_step": "recommend_handler",
            },
        }
        
        final_state = self.graph.invoke(initial_state)
        
        if final_state.get("errors"):
            for err in final_state["errors"]:
                self.output_func(f"  - {err}")
            return False
        
        recommend_result = final_state.get("recommend_result", {})
        
        if recommend_result.get("success"):
            recommendations = recommend_result.get("recommendations", [])
            if recommendations:
                self.output_func(f"\n改进建议: {project_name}")
                self.output_func("=" * 50)
                
                for i, rec in enumerate(recommendations, 1):
                    priority = rec.get('priority', 'medium')
                    self.output_func(f"\n{i}. [{priority.upper()}] {rec.get('title', '')}")
                    if rec.get('description'):
                        self.output_func(f"   {rec.get('description')}")
                    if rec.get('action'):
                        self.output_func(f"   → 操作: {rec.get('action')}")
                    if rec.get('effort'):
                        self.output_func(f"   → 投入: {rec.get('effort')}")
            else:
                self.output_func(f"未找到改进建议")
        else:
            self.output_func(recommend_result.get("error", "未找到改进建议"))
        
        return False
    
    def _handle_similar(self, args: Dict[str, Any]) -> bool:
        """处理 /similar 命令 - 显示相似项目"""
        project_name = args.get("name") or self.context.last_project
        
        if not project_name:
            self.output_func("用法: /similar [project_name]")
            self.output_func("  显示与项目相似的其他项目")
            return False
        
        from storage import StorageManager
        storage = StorageManager()
        version_dir = storage.get_latest_version_dir(project_name)
        
        initial_state = {
            "user_input": f"/similar {project_name}",
            "intent": "similar",
            "project_name": project_name,
            "storage_dir": str(version_dir) if version_dir else None,
            "current_step": "",
            "completed_steps": [],
            "errors": [],
            "warnings": [],
            "orchestrator_decision": {
                "intent": "similar",
                "next_step": "similar_handler",
            },
        }
        
        final_state = self.graph.invoke(initial_state)
        
        if final_state.get("errors"):
            for err in final_state["errors"]:
                self.output_func(f"  - {err}")
            return False
        
        similar_result = final_state.get("similar_result", {})
        
        if similar_result.get("success"):
            similar_projects = similar_result.get("similar_projects", [])
            if similar_projects:
                self.output_func(f"\n相似项目: {project_name}")
                self.output_func("=" * 50)
                
                for sim in similar_projects:
                    name = sim.get('name', '')
                    similarity = sim.get('similarity', 0)
                    reason = sim.get('reason', '')
                    
                    self.output_func(f"\n• {name} ({similarity:.0%})")
                    if reason:
                        self.output_func(f"  原因: {reason}")
                    
                    if sim.get('suggest_compare'):
                        self.output_func(f"  → 建议对比: /compare {project_name} {name}")
            else:
                self.output_func(f"未找到相似项目")
        else:
            self.output_func(similar_result.get("error", "未找到相似项目"))
        
        return False
    
    def _handle_analyzers(self, args: Dict[str, Any]) -> bool:
        """处理 /analyzers 命令"""
        initial_state = {
            "user_input": "/analyzers",
            "intent": "analyzers",
            "current_step": "",
            "completed_steps": [],
            "errors": [],
            "warnings": [],
            "orchestrator_decision": {
                "intent": "analyzers",
                "next_step": "analyzers_handler",
            },
        }
        
        final_state = self.graph.invoke(initial_state)
        
        if final_state.get("errors"):
            for err in final_state["errors"]:
                self.output_func(f"  - {err}")
            return False
        
        analyzers_result = final_state.get("analyzers_result", {})
        
        if analyzers_result.get("success"):
            analyzers = analyzers_result.get("analyzers", [])
            self.output_func("\n可用的分析器:")
            self.output_func("-" * 50)
            
            for a in analyzers:
                status = "[x]" if a.get("enabled") else "[ ]"
                self.output_func(f"  {status} {a.get('name', ''):<15} {a.get('description', '')}")
        else:
            self.output_func(analyzers_result.get("error", "获取分析器失败"))
        
        return False
    
    def _handle_help(self, args: Dict[str, Any]) -> bool:
        """处理 /help 命令"""
        topic = args.get("topic")
        
        initial_state = {
            "user_input": f"/help {topic}" if topic else "/help",
            "intent": "help",
            "params": {"topic": topic},
            "current_step": "",
            "completed_steps": [],
            "errors": [],
            "warnings": [],
            "orchestrator_decision": {
                "intent": "help",
                "next_step": "help_handler",
            },
        }
        
        final_state = self.graph.invoke(initial_state)
        
        if final_state.get("errors"):
            for err in final_state["errors"]:
                self.output_func(f"  - {err}")
            return False
        
        help_result = final_state.get("help_result", {})
        
        if help_result.get("success") or help_result.get("content"):
            self.output_func(help_result.get("content", ""))
        else:
            self.output_func(help_result.get("error", "获取帮助失败"))
        
        return False
    
    def _handle_version(self, args: Dict[str, Any]) -> bool:
        """处理 /version 命令"""
        initial_state = {
            "user_input": "/version",
            "intent": "version",
            "current_step": "",
            "completed_steps": [],
            "errors": [],
            "warnings": [],
            "orchestrator_decision": {
                "intent": "version",
                "next_step": "version_handler",
            },
        }
        
        final_state = self.graph.invoke(initial_state)
        
        if final_state.get("errors"):
            for err in final_state["errors"]:
                self.output_func(f"  - {err}")
            return False
        
        version_result = final_state.get("version_result", {})
        
        if version_result.get("success"):
            version = version_result.get("version", "unknown")
            self.output_func(f"eval-agent v{version}")
        else:
            self.output_func(version_result.get("error", "获取版本失败"))
        
        return False
    
    def _handle_quit(self, args: Dict[str, Any]) -> bool:
        """处理退出命令"""
        initial_state = {
            "user_input": "/quit",
            "intent": "quit",
            "current_step": "",
            "completed_steps": [],
            "errors": [],
            "warnings": [],
            "orchestrator_decision": {
                "intent": "quit",
                "next_step": "quit_handler",
            },
        }
        
        final_state = self.graph.invoke(initial_state)
        
        if final_state.get("errors"):
            for err in final_state["errors"]:
                self.output_func(f"  - {err}")
            return False
        
        self.output_func("再见!")
        return final_state.get("should_quit", True)
    
    def _handle_clear(self, args: Dict[str, Any]) -> bool:
        """处理清除屏幕命令"""
        initial_state = {
            "user_input": "/clear",
            "intent": "clear",
            "current_step": "",
            "completed_steps": [],
            "errors": [],
            "warnings": [],
            "orchestrator_decision": {
                "intent": "clear",
                "next_step": "clear_handler",
            },
        }
        
        final_state = self.graph.invoke(initial_state)
        
        if final_state.get("errors"):
            for err in final_state["errors"]:
                self.output_func(f"  - {err}")
        
        return False
    
    def route_intent(self, parsed: "ParsedIntent") -> bool:
        """根据解析的意图路由到处理函数
        
        Args:
            parsed: 解析后的意图
        
        Returns:
            是否退出
        """
        intent = parsed.intent
        params = parsed.params
        
        # 解析代词引用（如 "这个项目"、"它"）
        if params.get("project"):
            resolved = self.context.resolve_reference(params["project"])
            if resolved:
                params["project"] = resolved
        
        if params.get("project_a"):
            resolved = self.context.resolve_reference(params["project_a"])
            if resolved:
                params["project_a"] = resolved
        
        if params.get("project_b"):
            resolved = self.context.resolve_reference(params["project_b"])
            if resolved:
                params["project_b"] = resolved
        
        result = None
        
        if intent == Intent.ANALYZE:
            result = self._handle_analyze({"path": params.get("project") or params.get("url", "")})
        
        elif intent == Intent.COMPARE:
            result = self._handle_compare({
                "project_a": params.get("project_a", ""),
                "project_b": params.get("project_b", ""),
            })
        
        elif intent == Intent.LIST:
            result = self._handle_list({})
        
        elif intent == Intent.INFO:
            result = self._handle_show({"name": params.get("project", "")})
        
        elif intent == Intent.HELP:
            result = self._handle_help({})
        
        elif intent == Intent.DELETE:
            result = self._handle_delete({"name": params.get("project", "")})
        
        else:
            self.output_func(f"无法识别的意图")
            return False
        
        # 更新对话上下文
        self.context.add_turn(
            user_input=parsed.raw_input,
            intent=intent.value,
            params=params,
            result=result,
        )
        
        return result


def run_cli():
    """运行 CLI"""
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import InMemoryHistory
        
        llm_client = None
        if HAS_LLM and LLMClient and os.getenv("OPENAI_API_KEY"):
            try:
                llm_client = LLMClient()
            except Exception:
                pass
        
        commands = ["analyze", "compare", "list", "show", "delete", "analyzers", 
                   "insights", "recommend", "similar", "help", "version", "quit", "exit", "clear"]
        completer = CommandCompleter(commands)
        
        session = PromptSession(
            "eval-agent> ",
            completer=completer,
            history=InMemoryHistory(),
        )
        
        handler = CommandHandler(llm_client=llm_client)
        
        setup_interrupt_handler()
        
        print(f"""
╭──────────────────────────────────────────────────────────────╮
│  eval-agent v1.0.0 - CI/CD 架构评估工具                        │
╰──────────────────────────────────────────────────────────────╯
支持自然语言输入，例如：
  - "分析 cccl 项目"
  - "对比 cccl 和 TensorRT-LLM"
  - "有哪些已分析的项目"
输入 / 查看传统命令
""")
        
        while True:
            try:
                text = session.prompt()
            except KeyboardInterrupt:
                print("\n再见!")
                break
            
            text = text.strip()
            if not text:
                continue
            
            if text.startswith('/'):
                parser = CommandParser()
                command, args = parser.parse(text)
                if command:
                    should_quit = handler.handle(command, args)
                    if should_quit:
                        break
                continue
            
            known_projects = [p.name for p in list_projects()]
            context = {"last_project": handler.context.last_project}
            parsed = handler.intent_parser.parse(text, known_projects, context)
            
            if parsed.needs_clarification and parsed.confidence < 0.5:
                print(f"\n💡 {parsed.clarification_question}")
                continue
            
            should_quit = handler.route_intent(parsed)
            if should_quit:
                break
    
    except ImportError:
        print("提示: 安装 prompt_toolkit 以获得更好的交互体验")
        print("      pip install prompt_toolkit")
        print()
        
        run_cli_simple()


def run_cli_simple():
    """简单的 CLI（无 prompt_toolkit）"""
    llm_client = None
    if HAS_LLM and LLMClient and os.getenv("OPENAI_API_KEY"):
        try:
            llm_client = LLMClient()
        except Exception:
            pass
    
    handler = CommandHandler(llm_client=llm_client)
    
    setup_interrupt_handler()
    
    print(f"""
╭──────────────────────────────────────────────────────────────┐
│  eval-agent v1.0.0 - CI/CD 架构评估工具                        │
╰──────────────────────────────────────────────────────────────┘
支持自然语言输入，例如：
  - "分析 cccl 项目"
  - "对比 cccl 和 TensorRT-LLM"
  - "有哪些已分析的项目"
输入 / 查看传统命令
""")
    
    while True:
        try:
            text = input("eval-agent> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n再见!")
            break
        
        if not text:
            continue
        
        if text.startswith('/'):
            parser = CommandParser()
            command, args = parser.parse(text)
            if command:
                should_quit = handler.handle(command, args)
                if should_quit:
                    break
            continue
        
        known_projects = [p.name for p in list_projects()]
        context = {"last_project": handler.context.last_project}
        parsed = handler.intent_parser.parse(text, known_projects, context)
        
        if parsed.needs_clarification and parsed.confidence < 0.5:
            print(f"\n{parsed.clarification_question}")
            continue
        
        should_quit = handler.route_intent(parsed)
        if should_quit:
            break


if __name__ == "__main__":
    run_cli()
