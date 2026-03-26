"""LangSmith 追踪配置"""
import os
from typing import Optional
from functools import wraps

LANGSMITH_AVAILABLE = False
try:
    from langsmith import Client, traceable
    from langchain_core.callbacks import LangchainCallbackHandler
    LANGSMITH_AVAILABLE = True
except ImportError:
    traceable = None
    LangchainCallbackHandler = None


class TracingConfig:
    """LangSmith 追踪配置"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        project: str = "eval-agent",
        tracing_enabled: bool = False,
    ):
        self.api_key = api_key or os.getenv("LANGSMITH_API_KEY")
        self.project = project or os.getenv("LANGSMITH_PROJECT", "eval-agent")
        self.tracing_enabled = tracing_enabled or os.getenv("LANGCHAIN_TRACING_V2", "").lower() == "true"
        self._client = None
        
        if self.tracing_enabled and self.api_key:
            self._setup()
    
    def _setup(self):
        """设置追踪"""
        if not LANGSMITH_AVAILABLE:
            return
        
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_PROJECT"] = self.project
        
        try:
            self._client = Client(api_key=self.api_key)
        except Exception:
            pass
    
    @property
    def client(self):
        """获取 LangSmith 客户端"""
        return self._client
    
    def is_enabled(self) -> bool:
        """检查是否启用"""
        return self.tracing_enabled and self.api_key and LANGSMITH_AVAILABLE
    
    def get_trace_url(self, run_id: str) -> str:
        """获取追踪 URL"""
        return f"https://smith.langchain.com/o/default/projects/p/{self.project}/r/{run_id}"
    
    def get_project_url(self) -> str:
        """获取项目 URL"""
        return f"https://smith.langchain.com/o/default/projects/p/{self.project}"


# 全局配置实例
_tracing_config: Optional[TracingConfig] = None


def setup_tracing(
    api_key: Optional[str] = None,
    project: str = "eval-agent",
) -> TracingConfig:
    """配置 LangSmith 追踪
    
    Args:
        api_key: LangSmith API Key
        project: 项目名称
    
    Returns:
        TracingConfig 实例
    """
    global _tracing_config
    _tracing_config = TracingConfig(
        api_key=api_key,
        project=project,
        tracing_enabled=True,
    )
    return _tracing_config


def get_tracing_config() -> TracingConfig:
    """获取全局追踪配置"""
    global _tracing_config
    if _tracing_config is None:
        _tracing_config = TracingConfig()
    return _tracing_config


def is_tracing_enabled() -> bool:
    """检查是否启用追踪"""
    return get_tracing_config().is_enabled()


def get_trace_url(run_id: str) -> str:
    """获取追踪 URL"""
    return get_tracing_config().get_trace_url(run_id)


def get_project_url() -> str:
    """获取项目 URL"""
    return get_tracing_config().get_project_url()


def traceable_agent(name: str):
    """Agent 追踪装饰器
    
    用法:
        @traceable_agent("CICDAgent")
        def run(self, state):
            ...
    """
    if not LANGSMITH_AVAILABLE or not traceable:
        def decorator(func):
            return func
        return decorator
    
    return traceable(
        name=name,
        run_type="chain",
        tags=["agent"],
    )


def traceable_tool(name: str):
    """工具追踪装饰器
    
    用法:
        @traceable_tool("extract_ci_data")
        def extract_ci_data(project_path: str):
            ...
    """
    if not LANGSMITH_AVAILABLE or not traceable:
        def decorator(func):
            return func
        return decorator
    
    return traceable(
        name=name,
        run_type="tool",
        tags=["tool"],
    )


def traceable_llm(name: str):
    """LLM 调用追踪装饰器
    
    用法:
        @traceable_llm("generate_analysis")
        def generate_analysis(prompt: str):
            ...
    """
    if not LANGSMITH_AVAILABLE or not traceable:
        def decorator(func):
            return func
        return decorator
    
    return traceable(
        name=name,
        run_type="llm",
        tags=["llm"],
    )


def get_callback_handler():
    """获取 LangChain 回调处理器"""
    if not LANGSMITH_AVAILABLE or LangchainCallbackHandler is None:
        return None
    
    config = get_tracing_config()
    if not config.is_enabled():
        return None
    
    try:
        return LangchainCallbackHandler(
            project_name=config.project,
            client=config.client,
        )
    except Exception:
        return None


def auto_setup():
    """自动从环境变量设置追踪"""
    if os.getenv("LANGCHAIN_TRACING_V2", "").lower() == "true":
        setup_tracing()
