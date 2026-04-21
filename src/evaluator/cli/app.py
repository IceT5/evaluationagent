# CLI 命令处理器

import re
import os
import sys
import time
import signal
from pathlib import Path
from typing import TYPE_CHECKING, Optional, List, Tuple, Dict, Any
from dataclasses import dataclass
from enum import Enum

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
from evaluator.config import resolve_interactive_mode
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


# ========== 补全类型定义 ==========

class CompletionType(Enum):
    """补全类型枚举"""
    PROJECT = "project"        # 项目名称
    VERSION = "version"        # 版本号
    DIMENSION = "dimension"    # 对比维度
    FILE = "file"             # 文件路径
    URL = "url"               # URL地址


@dataclass
class ParameterMeta:
    """参数元数据"""
    name: str                           # 参数名
    completion_type: CompletionType     # 补全类型
    required: bool = True              # 是否必需
    depends_on: Optional[str] = None   # 依赖的参数（如version依赖project）
    position: Optional[int] = None     # 位置参数的位置（可选）


@dataclass
class CommandMeta:
    """命令元数据"""
    name: str                           # 命令名
    pattern: str                        # 正则表达式（从CommandParser.COMMANDS获取）
    description: str = ""               # 描述（可选）
    parameters: List[ParameterMeta] = None  # 参数列表


class CommandRegistry:
    """命令注册中心 - 集中管理所有命令定义和补全配置"""

    COMMANDS: Dict[str, CommandMeta] = {}

    @classmethod
    def register(cls, name: str, parameters: List[ParameterMeta], description: str = ""):
        """注册命令元数据"""
        # 从CommandParser.COMMANDS获取pattern
        pattern = CommandParser.COMMANDS.get(name, "")
        cls.COMMANDS[name] = CommandMeta(
            name=name,
            pattern=pattern,
            description=description,
            parameters=parameters,
        )

    @classmethod
    def get(cls, name: str) -> Optional[CommandMeta]:
        """获取命令元数据"""
        return cls.COMMANDS.get(name)

    @classmethod
    def initialize(cls):
        """初始化所有命令的元数据"""
        # show命令
        cls.register(
            "show",
            parameters=[
                ParameterMeta("name", CompletionType.PROJECT, required=True, position=1),
                ParameterMeta("version", CompletionType.VERSION, required=False, depends_on="name"),
            ],
            description="显示项目信息"
        )

        # delete命令
        cls.register(
            "delete",
            parameters=[
                ParameterMeta("name", CompletionType.PROJECT, required=True, position=1),
                ParameterMeta("version", CompletionType.VERSION, required=False, depends_on="name"),
            ],
            description="删除项目或版本"
        )

        # compare命令
        cls.register(
            "compare",
            parameters=[
                ParameterMeta("project_a", CompletionType.PROJECT, required=True, position=1),
                ParameterMeta("project_b", CompletionType.PROJECT, required=True, position=2),
                ParameterMeta("version_a", CompletionType.VERSION, required=False, depends_on="project_a"),
                ParameterMeta("version_b", CompletionType.VERSION, required=False, depends_on="project_b"),
                ParameterMeta("dimensions", CompletionType.DIMENSION, required=False),
            ],
            description="对比两个项目"
        )

        # insights/recommend/similar命令
        for cmd in ["insights", "recommend", "similar"]:
            cls.register(
                cmd,
                parameters=[
                    ParameterMeta("name", CompletionType.PROJECT, required=True, position=1),
                ],
                description=f"{cmd}分析"
            )

        # 其他命令（无需参数补全）
        for cmd in ["analyze", "list", "analyzers", "help", "version", "quit", "clear"]:
            cls.register(cmd, parameters=[], description=cmd)


def setup_interrupt_handler():
    """设置中断信号处理器"""
    if interrupt_controller is None:
        return
    
    def handler(signum, frame):
        print("\n\n⚠️  正在中断...")
        interrupt_controller.interrupt("用户按下 Ctrl+C")
    
    signal.signal(signal.SIGINT, handler)


class CommandCompleter(Completer):
    """智能命令补全器 - 基于命令注册中心自动处理"""

    def __init__(self, commands: List[str], storage_manager: Optional[StorageManager] = None):
        super().__init__()
        self.commands = commands
        self.storage = storage_manager

        # 初始化命令注册中心
        if not CommandRegistry.COMMANDS:
            CommandRegistry.initialize()

        # 补全提供者映射
        self.completion_providers = {
            CompletionType.PROJECT: self._complete_projects,
            CompletionType.VERSION: self._complete_versions,
            CompletionType.DIMENSION: self._complete_dimensions,
        }

        # 缓存机制
        self._projects_cache = None
        self._cache_time = 0
        self._cache_ttl = 5  # 缓存5秒

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor

        # 1. 命令名称补全（原有逻辑，保持不变）
        if text.startswith('/') and ' ' not in text:
            word = text[1:]
            for cmd in self.commands:
                if cmd.startswith(word):
                    yield Completion(
                        text='/' + cmd,
                        start_position=-len(text),
                        display='/' + cmd,
                    )
            return

        # 2. 参数补全（新增逻辑）
        if not self.storage:
            return  # 无存储管理器时，不提供参数补全

        yield from self._complete_parameters(text)

    def _complete_parameters(self, text: str):
        """参数补全逻辑"""
        parts = text.split()
        if len(parts) < 2:
            return

        command = parts[0][1:]  # 去掉 /
        command_meta = CommandRegistry.get(command)

        if not command_meta or not command_meta.parameters:
            return

        last_word = parts[-1]

        # 检测当前正在输入的参数
        current_param = self._detect_current_parameter(parts, command_meta)

        if current_param:
            # 构建上下文（已输入的参数值）
            context = self._build_context(parts, command_meta)

            # 如果最后一个词是命名参数（如 --version-a），则前缀为空
            if last_word.startswith('--'):
                prefix = ''
            else:
                prefix = last_word

            # 获取补全提供者
            provider = self.completion_providers.get(current_param.completion_type)
            if provider:
                try:
                    yield from provider(prefix, current_param, context)
                except Exception:
                    pass  # 静默失败

    def _detect_current_parameter(self, parts: List[str], command_meta: CommandMeta) -> Optional[ParameterMeta]:
        """检测当前正在输入的参数"""
        # 检查命名参数（如 --version）
        # 情况1: --param value（parts[-2]是--param）
        # 情况2: --param （parts[-1]是--param，正在输入值）
        if len(parts) >= 2 and parts[-2].startswith('--'):
            param_name = parts[-2][2:].replace('-', '_')  # 去掉 -- 并转换为下划线
            for param in command_meta.parameters:
                if param.name == param_name:
                    return param

        # 检查最后一个词是否是命名参数（正在输入值）
        if len(parts) >= 1 and parts[-1].startswith('--'):
            param_name = parts[-1][2:].replace('-', '_')  # 去掉 -- 并转换为下划线
            for param in command_meta.parameters:
                if param.name == param_name:
                    return param

        # 检查位置参数
        # 例如：/show <project> <version>
        # parts: ['/show', 'proj', 'v1']
        # 位置1对应project，位置2对应version
        # parts[0]是命令，parts[1]是第1个位置参数，parts[2]是第2个位置参数
        position = len(parts) - 1  # 减去命令本身
        for param in command_meta.parameters:
            if param.position == position:
                return param

        return None

    def _build_context(self, parts: List[str], command_meta: CommandMeta) -> dict:
        """构建上下文（已输入的参数值）"""
        context = {}

        # 解析位置参数
        # parts[0]是命令，parts[1]是第1个位置参数，parts[2]是第2个位置参数
        for param in command_meta.parameters:
            if param.position and param.position < len(parts):
                value = parts[param.position]
                if not value.startswith('--'):
                    context[param.name] = value

        # 解析命名参数（简化版本）
        for i, part in enumerate(parts):
            if part.startswith('--') and i + 1 < len(parts):
                param_name = part[2:].replace('-', '_')  # 转换为下划线
                context[param_name] = parts[i + 1]

        return context

    def _complete_projects(self, prefix: str, param: ParameterMeta, context: dict):
        """项目名称补全"""
        for proj in self._get_projects():
            if proj.startswith(prefix):
                yield Completion(
                    text=proj,
                    start_position=-len(prefix),
                    display=proj,
                )

    def _complete_versions(self, prefix: str, param: ParameterMeta, context: dict):
        """版本号补全"""
        # 获取依赖的项目名称
        depends_on = param.depends_on
        project_name = context.get(depends_on)

        if not project_name:
            return

        for version in self._get_versions(project_name):
            if version.startswith(prefix):
                yield Completion(
                    text=version,
                    start_position=-len(prefix),
                    display=version,
                )

    def _complete_dimensions(self, prefix: str, param: ParameterMeta, context: dict):
        """维度补全"""
        dimensions = ["complexity", "best_practices", "maintainability"]
        for dim in dimensions:
            if dim.startswith(prefix):
                yield Completion(
                    text=dim,
                    start_position=-len(prefix),
                    display=dim,
                )

    def _get_projects(self) -> List[str]:
        """获取项目列表（带缓存）"""
        now = time.time()
        if self._projects_cache is None or (now - self._cache_time) > self._cache_ttl:
            try:
                from evaluator.core import list_projects
                self._projects_cache = [p.name for p in list_projects()]
                self._cache_time = now
            except Exception:
                self._projects_cache = []
        return self._projects_cache

    def _get_versions(self, project_name: str) -> List[str]:
        """获取项目的版本列表"""
        try:
            return self.storage.list_versions(project_name)
        except Exception:
            return []

    async def get_completions_async(self, document, complete_event):
        """异步方法（保持接口兼容）"""
        for completion in self.get_completions(document, complete_event):
            yield completion


class CommandParser:
    """命令解析器"""
    
    COMMANDS = {
        "analyze": r"^/analyze(?:\s+(?P<type>\w+))?(?:\s+(?P<path>.+))?$",
        "compare": r"^/compare\s+(?P<project_a>[^\s]+)\s+(?P<project_b>[^\s]+)(?:\s+--version-a\s+(?P<version_a>[^\s]+))?(?:\s+--version-b\s+(?P<version_b>[^\s]+))?(?:\s+--dim\s+(?P<dimensions>.+))?$",
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
    _AGENT_SERVER_URL = "http://127.0.0.1:2024"
    _agent_server_available = None  # None=未检测, True=可用, False=不可用

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
        """延迟加载LangGraph实例（带 checkpointer 支持 interrupt/resume）"""
        if self._graph is None:
            from evaluator.core.graphs import create_main_graph
            llm_config = None
            if self.llm_client:
                llm_config = {
                    "api_key": os.getenv("OPENAI_API_KEY"),
                    "base_url": os.getenv("OPENAI_BASE_URL"),
                    "model": getattr(self.llm_client, 'model', None),
                }
            # 本地模式需要 MemorySaver 作为 checkpointer 才能支持 interrupt/resume
            checkpointer = None
            try:
                from langgraph.checkpoint.memory import MemorySaver
                checkpointer = MemorySaver()
            except ImportError:
                pass  # 无 checkpointer 时 interrupt 会失败，但图仍可运行
            self._graph = create_main_graph(llm_config=llm_config, checkpointer=checkpointer)
        return self._graph
    
    def _invoke_graph(self, initial_state: dict) -> dict:
        """执行 graph - 优先通过 langgraph dev server，fallback 到本地执行。

        执行顺序：
        1. 尝试通过 langgraph dev server 执行（Studio 可实时高亮）
        2. 如果 server 不可用，fallback 到本地 graph.invoke
        """
        # 优先尝试通过 server 执行（Studio 实时高亮）
        result = self._try_invoke_via_server(initial_state)
        if result is not None:
            return result

        # fallback: 本地执行（支持 interrupt/resume 循环）
        return self._invoke_local_with_resume(initial_state)

    def _try_invoke_via_server(self, initial_state: dict) -> Optional[dict]:
        """通过 Agent Server 流式执行 run（Studio 实时高亮 + CLI 逐步进度）

        使用 runs.stream(stream_mode="updates") 流式执行：
        - Studio 通过服务端内置 checkpointer 实时高亮每个完成的节点
        - CLI 逐步打印每个完成的节点名
        - 流结束后通过 threads.get_state()["values"] 获取完整最终状态

        如果 langgraph dev 未运行，返回 None，由 _invoke_graph fallback 到本地 invoke。
        """
        # 快速跳过：已确认 langgraph_sdk 不可用（打包场景）
        if self._agent_server_available is False:
            return None

        try:
            from langgraph_sdk import get_sync_client
            import httpx
            import signal

            # 连接超时 5s（快速检测 server 是否在线）
            # 读取超时 1200s（SSE 长连接，每次推送重置超时，覆盖 20 分钟执行场景）
            client = get_sync_client(
                url=self._AGENT_SERVER_URL,
                timeout=httpx.Timeout(connect=5, read=1200, write=5, pool=5),
            )

            # 获取或创建 assistant
            assistants = client.assistants.search(graph_id="evaluator")
            if assistants:
                assistant = assistants[0]
            else:
                assistant = client.assistants.create(graph_id="evaluator")

            # 创建 thread
            thread = client.threads.create()
            thread_id = thread["thread_id"]

            self.output_func("  [Studio] 已连接 langgraph dev，可在 Studio 查看节点高亮")

            run_id = None  # 从 metadata chunk 中提取，用于 Ctrl+C 取消

            def _cancel_remote_run(signum, frame):
                if run_id:
                    try:
                        client.runs.cancel(thread_id=thread_id, run_id=run_id)
                    except Exception:
                        pass

            old_handler = signal.signal(signal.SIGINT, _cancel_remote_run)

            try:
                # 流式执行：updates 推送节点完成事件，debug 推送子图内部节点进度
                for chunk in client.runs.stream(
                    thread_id=thread_id,
                    assistant_id=assistant["assistant_id"],
                    input=initial_state,
                    stream_mode=["updates", "debug", "custom"],
                ):
                    if chunk.event == "metadata":
                        # 第一个 chunk：提取 run_id 用于取消
                        run_id = chunk.data.get("run_id")
                    elif chunk.event == "updates":
                        # 检测 interrupt：updates chunk 中可能包含 __interrupt__
                        if isinstance(chunk.data, dict) and "__interrupt__" in chunk.data:
                            intr_list = chunk.data["__interrupt__"]
                            if intr_list:
                                intr = intr_list[0]
                                payload = intr.get("value", intr.value) if isinstance(intr, dict) else getattr(intr, 'value', {})
                                user_response = self._handle_interrupt(payload)
                                
                                self.output_func(f"  [Studio] 用户选择: {user_response}")
                                
                                # resume：用同一 thread 发起新 run
                                for resume_chunk in client.runs.stream(
                                    thread_id=thread_id,
                                    assistant_id=assistant["assistant_id"],
                                    command={"resume": user_response},
                                    stream_mode=["updates", "debug", "custom"],
                                ):
                                    if resume_chunk.event == "updates":
                                        for node_name in resume_chunk.data:
                                            if node_name != "__interrupt__":
                                                self.output_func(f"  [Studio] ✓ {node_name}")
                                    elif resume_chunk.event == "debug":
                                        try:
                                            debug_data = resume_chunk.data if isinstance(resume_chunk.data, dict) else {}
                                            ns = debug_data.get("ns", [])
                                            debug_type = debug_data.get("type", "")
                                            if debug_type == "task" and len(ns) <= 2:
                                                path_parts = []
                                                for part in ns:
                                                    n = part.split(":")[0] if ":" in part else part
                                                    path_parts.append(n)
                                                if path_parts:
                                                    sub_path = "/".join(path_parts)
                                                    self.output_func(f"  [Studio] → {sub_path}")
                                        except Exception:
                                            pass
                                    elif resume_chunk.event == "custom":
                                        try:
                                            custom_data = resume_chunk.data if isinstance(resume_chunk.data, dict) else {}
                                            step = custom_data.get("step", "")
                                            if step == "multi_round":
                                                current = custom_data.get("current", "?")
                                                total = custom_data.get("total", "?")
                                                self.output_func(f"  [Studio] 🔄 Round {current}/{total}")
                                            elif step == "batch_llm":
                                                total = custom_data.get("total", "?")
                                                completed = custom_data.get("completed", "?")
                                                self.output_func(f"  [Studio] 🔄 LLM batch {completed}/{total}")
                                        except Exception:
                                            pass
                                break  # interrupt 已处理，跳出原始 stream
                        else:
                            # 节点完成：打印进度
                            for node_name in chunk.data:
                                self.output_func(f"  [Studio] ✓ {node_name}")
                    elif chunk.event == "debug":
                        # 子图内部节点进度（debug 事件）
                        # chunk.data 是 DebugStreamPart: {type, ns, data}
                        # ns 是命名空间路径如 ["cicd:xxx", "extract:yyy"]
                        # 只显示深度 <= 2 的子图节点，过滤过深内部细节
                        try:
                            debug_data = chunk.data if isinstance(chunk.data, dict) else {}
                            ns = debug_data.get("ns", [])
                            debug_type = debug_data.get("type", "")
                            # 只处理 task 类事件（节点开始执行），忽略 checkpoint 等冗余事件
                            if debug_type == "task" and len(ns) <= 2:
                                # 从 ns 提取子图路径：["cicd:xxx", "extract:yyy"] → "cicd/extract"
                                path_parts = []
                                for part in ns:
                                    node_name = part.split(":")[0] if ":" in part else part
                                    path_parts.append(node_name)
                                if path_parts:
                                    sub_path = "/".join(path_parts)
                                    # 为 CICD 子图节点添加友好图标
                                    _NODE_ICONS = {
                                        "extract": "📊", "plan": "📝", "invoke": "🔄",
                                        "merge": "🔗", "check": "✅", "retry": "🔁",
                                        "organize": "📋", "report": "📄", "summary": "📝",
                                    }
                                    last_node = path_parts[-1] if path_parts else ""
                                    icon = _NODE_ICONS.get(last_node, "→")
                                    self.output_func(f"  [Studio] {icon} {sub_path}")
                        except Exception:
                            pass  # debug 事件解析失败不影响主流程
                    elif chunk.event == "custom":
                        # 自定义进度事件（来自 get_stream_writer）
                        try:
                            custom_data = chunk.data if isinstance(chunk.data, dict) else {}
                            step = custom_data.get("step", "")
                            if step == "multi_round":
                                current = custom_data.get("current", "?")
                                total = custom_data.get("total", "?")
                                self.output_func(f"  [Studio] 🔄 Round {current}/{total}")
                            elif step == "batch_llm":
                                total = custom_data.get("total", "?")
                                completed = custom_data.get("completed", "?")
                                self.output_func(f"  [Studio] 🔄 LLM batch {completed}/{total}")
                        except Exception:
                            pass  # custom 事件解析失败不影响主流程

                # 流结束：从 thread 获取完整最终状态
                # 用 state["values"] 而非 state.values（后者是 dict 自带的 .values() 方法）
                state_snapshot = client.threads.get_state(thread_id=thread_id)
                result = state_snapshot["values"]

                self.__class__._agent_server_available = True
                return result

            except Exception:
                # run 被取消或流中断
                if interrupt_controller and interrupt_controller.is_interrupted():
                    raise InterruptException("用户按下 Ctrl+C")
                return None
            finally:
                signal.signal(signal.SIGINT, old_handler)

        except ImportError:
            # langgraph_sdk 未安装（PyInstaller 打包场景），永久标记不可用
            self.__class__._agent_server_available = False
            return None
        except Exception:
            # 连接失败或其他错误 — 不缓存失败，下次仍尝试连接
            return None
    
    def _invoke_local_with_resume(self, initial_state: dict) -> dict:
        """本地执行：支持 interrupt/resume 循环
        
        本地模式下 graph.invoke() 遇到 interrupt() 会暂停并返回 __interrupt__。
        此方法循环处理：invoke → 检测 interrupt → 收集输入 → invoke(Command(resume=...))
        """
        from langgraph.types import Command
        from langgraph.graph.state import CompiledStateGraph
        
        # 本地模式需要 checkpointer 才能支持 interrupt/resume
        # 如果图没有 checkpointer，尝试用 MemorySaver
        graph = self.graph
        config = {"configurable": {"thread_id": f"local-{int(time.time())}"}}
        current_input = initial_state
        
        while True:
            result = graph.invoke(current_input, config=config)
            
            # 检测 interrupt
            interrupts = result.get("__interrupt__", []) if isinstance(result, dict) else []
            if not interrupts:
                return result  # 正常结束
            
            # 处理 interrupt
            intr = interrupts[0]
            payload = intr.value if hasattr(intr, 'value') else (intr.get("value", {}) if isinstance(intr, dict) else {})
            user_response = self._handle_interrupt(payload)
            
            # resume：用 Command(resume=...) 继续执行
            self.output_func(f"  [Local] 用户选择: {user_response}")
            current_input = Command(resume=user_response)
    
    def _handle_interrupt(self, payload) -> str:
        """处理 LangGraph interrupt payload，在 CLI 收集用户输入
        
        Args:
            payload: interrupt() 传入的值（应为 dict）
        
        Returns:
            用户选择的值，将传给 Command(resume=...)
        """
        if not isinstance(payload, dict):
            # 非 dict payload，简单文本输入
            try:
                return input(f"\n请输入: ").strip()
            except (EOFError, KeyboardInterrupt):
                return ""
        
        kind = payload.get("kind", "")
        
        if kind == "review_fix_decision":
            question = payload.get("question", "请选择处理方式")
            options = payload.get("options", [])
            default = payload.get("default", "skip")
            data_count = payload.get("data_completion_count", 0)
            content_count = payload.get("content_supplement_count", 0)
            
            self.output_func(f"\n{'='*50}")
            self.output_func(f"  {question}")
            self.output_func(f"{'='*50}")
            if data_count:
                self.output_func(f"  数据补全: {data_count} 个问题（从 CI 数据提取填充）")
            if content_count:
                self.output_func(f"  内容补充: {content_count} 个问题（需要 LLM 生成）")
            self.output_func("")
            for opt in options:
                self.output_func(f"  {opt['label']}")
            
            try:
                choice = input("\n请输入选项: ").strip()
                # 按选项序号匹配
                for i, opt in enumerate(options):
                    if choice == str(i + 1):
                        return opt["value"]
                # 直接输入 value 也可以
                for opt in options:
                    if choice == opt["value"]:
                        return opt["value"]
                self.output_func(f"  无效选项，使用默认: {default}")
                return default
            except (EOFError, KeyboardInterrupt):
                raise  # 让 Ctrl+C 正常传播
            except Exception:
                return default
        
        # 未知 interrupt 类型
        self.output_func(f"\n  [Interrupt] {payload}")
        try:
            return input("请输入: ").strip()
        except (EOFError, KeyboardInterrupt):
            raise
        except Exception:
            return payload.get("default", "")
    
    def _trigger_intelligence_background(self, state: dict):
        """触发后台智能Agent任务（从 reporter 节点解耦至 CLI 层）
        
        后台任务通过 LANGSMITH_TRACING=true 环境变量自动 trace，
        与主流程的其他 agent 被 trace 的方式完全一致。
        """
        try:
            from evaluator.core.background import background
            state_copy = state.copy()
            
            if not state_copy.get("llm") and state_copy.get("llm_config"):
                from evaluator.llm import LLMClient
                try:
                    state_copy["llm"] = LLMClient(**state_copy.get("llm_config", {}))
                except Exception:
                    pass
            
            background.submit_intelligence(state_copy)
            self.output_func(f"  [Background] 智能分析将在后台执行，完成后可使用 /insights 查看结果")
        except Exception as e:
            self.output_func(f"  [Background] 提交智能任务失败: {e}")
    
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
            "interactive_mode": resolve_interactive_mode(studio_mode=False),
        }
        
        self.output_func(f"\n开始分析: {user_input}")
        self.output_func("-" * 50)
        self.output_func("  [使用 LangGraph 工作流]")
        
        if interrupt_controller:
            interrupt_controller.reset()
        
        start_time = time.time()
        
        final_state = None
        try:
            final_state = self._invoke_graph(initial_state)
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
        
        # 主流程完成后，触发后台智能分析（从 reporter 节点解耦至此）
        if final_state and not final_state.get("errors"):
            self._trigger_intelligence_background(final_state)
        
        return False
    
    def _handle_compare(self, args: Dict[str, Any]) -> bool:
        """处理 /compare 命令 - 使用 LangGraph 统一工作流"""
        project_a = args.get("project_a") or ""
        project_b = args.get("project_b") or ""
        version_a = args.get("version_a")
        version_b = args.get("version_b")
        dimensions_str = args.get("dimensions") or ""

        if not project_a or not project_b:
            self.output_func("用法: /compare <project_a> <project_b> [--version-a <v1>] [--version-b <v2>] [--dim <dimensions>]")
            self.output_func("  project_a, project_b: 项目名称（必需）")
            self.output_func("  --version-a: 项目A的版本号（可选，默认最新）")
            self.output_func("  --version-b: 项目B的版本号（可选，默认最新）")
            self.output_func("  --dim: 对比维度，逗号分隔（可选）")
            self.output_func("")
            self.output_func("示例:")
            self.output_func("  /compare proj1 proj2")
            self.output_func("  /compare proj1 proj2 --version-a v1.0 --version-b v2.0")
            self.output_func("  /compare proj1 proj2 --dim complexity,best_practices")
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
                "version_a": version_a,
                "version_b": version_b,
                "dimensions": dimensions,
            },
            "orchestrator_decision": {
                "intent": "compare",
                "params": {
                    "project_a": project_a,
                    "project_b": project_b,
                    "version_a": version_a,
                    "version_b": version_b,
                    "dimensions": dimensions
                },
                "confidence": 1.0,
                "needs_clarification": False,
                "next_step": "compare",
            },
            "llm_config": llm_config or {},
            "known_projects": [p.name for p in list_projects()],
            "context": {"last_project": self.context.last_project},
            "project_a": project_a,
            "project_b": project_b,
            "version_a": version_a,
            "version_b": version_b,
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
        
        final_state = self._invoke_graph(initial_state)
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
        
        final_state = self._invoke_graph(initial_state)
        
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
        
        final_state = self._invoke_graph(initial_state)
        
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
        
        final_state = self._invoke_graph(initial_state)
        
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
        
        final_state = self._invoke_graph(initial_state)
        
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
        
        final_state = self._invoke_graph(initial_state)
        
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
        
        final_state = self._invoke_graph(initial_state)
        
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
        
        final_state = self._invoke_graph(initial_state)
        
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
        
        final_state = self._invoke_graph(initial_state)
        
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
        
        final_state = self._invoke_graph(initial_state)
        
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
        
        final_state = self._invoke_graph(initial_state)
        
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
        
        final_state = self._invoke_graph(initial_state)
        
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
        storage = StorageManager()
        completer = CommandCompleter(commands, storage_manager=storage)
        
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
                else:
                    # 尝试识别部分命令并显示帮助
                    parts = text.split()
                    if len(parts) > 0:
                        potential_cmd = parts[0][1:]  # 去掉 /
                        if potential_cmd in CommandParser.COMMANDS:
                            # 显示该命令的帮助信息
                            handler.handle(potential_cmd, {})
                        else:
                            print(f"未知命令: {potential_cmd}")
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
            else:
                # 尝试识别部分命令并显示帮助
                parts = text.split()
                if len(parts) > 0:
                    potential_cmd = parts[0][1:]  # 去掉 /
                    if potential_cmd in CommandParser.COMMANDS:
                        # 显示该命令的帮助信息
                        handler.handle(potential_cmd, {})
                    else:
                        print(f"未知命令: {potential_cmd}")
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
