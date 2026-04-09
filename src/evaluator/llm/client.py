"""LLM 客户端 - Agent 的核心组件"""
import os
import time
import logging
from typing import Optional, List, Dict, Any, Tuple
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.callbacks import BaseCallbackHandler
import httpx

from evaluator.llm.tracing import traceable_llm

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "glm-4")


class LLMCallbackHandler(BaseCallbackHandler):
    """LLM 调用回调处理器 - 用于可观测性"""
    
    def __init__(self, agent_name: str = "LLMClient"):
        self.agent_name = agent_name
        self._start_time: Optional[float] = None
        self._token_count: int = 0
    
    def on_llm_start(self, serialized: Dict, prompts: List[str], **kwargs):
        self._start_time = time.time()
        logger.debug(f"[{self.agent_name}] LLM 开始调用")
    
    def on_llm_end(self, response, **kwargs):
        duration = time.time() - self._start_time if self._start_time else 0
        try:
            token_usage = response.response_metadata.get("token_usage", {})
            prompt_tokens = token_usage.get("prompt_tokens", 0)
            completion_tokens = token_usage.get("completion_tokens", 0)
            total_tokens = token_usage.get("total_tokens", 0)
            logger.debug(f"[{self.agent_name}] LLM 调用完成: {duration:.2f}s, tokens: {total_tokens}")
        except Exception:
            logger.debug(f"[{self.agent_name}] LLM 调用完成: {duration:.2f}s")
    
    def on_llm_error(self, error: BaseException, **kwargs):
        logger.error(f"[{self.agent_name}] LLM 调用错误: {error}")


class LLMClient:
    """
    LLM 调用客户端
    
    作为 Agent 的核心组件，提供 LLM 调用能力。
    支持 OpenAI API 及兼容的 API（如 Azure OpenAI, 本地模型等）
    """
    
    def __init__(
        self,
        provider: str = "openai",
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ):
        # 如果没有指定模型，从环境变量读取
        if model is None:
            model = os.getenv("DEFAULT_MODEL", "glm-4")
        """
        初始化 LLM 客户端
        
        Args:
            provider: LLM 提供商 (openai, azure, etc.)
            model: 模型名称
            api_key: API Key（不传则从环境变量读取）
            base_url: API 基础 URL（用于自定义端点）
            temperature: 温度参数
            max_tokens: 最大输出 token 数（None 表示不限制，由模型决定）
        """
        self.provider = provider
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        # 从环境变量获取配置
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL")
        
        if not self.api_key:
            raise ValueError(
                "API Key 未设置。请设置 OPENAI_API_KEY 环境变量，或在初始化时传入 api_key 参数。"
            )
        
        # 创建 LangChain ChatOpenAI 实例
        self._callback_handler = LLMCallbackHandler(self.__class__.__name__)
        
        try:
            from evaluator.config import config
            has_config = True
        except ImportError:
            has_config = False
        
        request_timeout = config.llm_request_timeout if has_config else 300
        default_max_tokens = config.llm_max_tokens if has_config else 131072
        
        # 创建可取消的 HTTP 客户端
        self._httpx_client = httpx.Client(timeout=httpx.Timeout(request_timeout))
        
        client_kwargs = {
            "model": model,
            "api_key": self.api_key,
            "base_url": self.base_url,
            "temperature": temperature,
            "request_timeout": request_timeout,
            "callbacks": [self._callback_handler],
            "http_client": self._httpx_client,
        }
        client_kwargs["max_tokens"] = max_tokens if max_tokens is not None else default_max_tokens
        
        self._client = ChatOpenAI(**client_kwargs)
        
        # 注册中断回调
        self._register_interrupt_callback()
    
    def _register_interrupt_callback(self):
        """注册中断回调，用于关闭 HTTP 连接"""
        try:
            from evaluator.core.interrupt import interrupt_controller, InterruptException
            self._InterruptException = InterruptException
            interrupt_controller.register_callback(self._cancel)
        except ImportError:
            self._InterruptException = Exception
    
    def _cancel(self):
        """中断回调：关闭 HTTP 连接"""
        try:
            self._httpx_client.close()
        except Exception:
            pass
    
    @traceable_llm("chat")
    def chat(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        发送 prompt 并获取响应
        
        Args:
            prompt: 用户输入
            system_prompt: 系统提示（可选）
        
        Returns:
            LLM 的响应文本
        """
        messages = []
        
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        
        messages.append(HumanMessage(content=prompt))
        
        try:
            response = self._client.invoke(messages)
            content = response.content
            if isinstance(content, str):
                return content
            elif isinstance(content, list):
                return "".join(str(item) for item in content)
            return str(content)
        except (httpx.StreamClosed, httpx.CloseError, httpx.ProtocolError):
            raise self._InterruptException("LLM 请求已取消")
        except self._InterruptException:
            raise
        except Exception as e:
            raise RuntimeError(f"LLM 调用失败: {e}")
    
    def chat_with_file(
        self,
        prompt_file: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        从文件读取 prompt 并获取响应
        
        Args:
            prompt_file: prompt 文件路径
            system_prompt: 系统提示（可选）
        
        Returns:
            LLM 的响应文本
        """
        with open(prompt_file, "r", encoding="utf-8") as f:
            prompt = f.read()
        
        return self.chat(prompt, system_prompt)
    
    def chat_with_context(
        self,
        prompt: str,
        context: dict,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        带 context 的对话
        
        Args:
            prompt: 用户输入
            context: 上下文信息（会被格式化到 prompt 中）
            system_prompt: 系统提示
        
        Returns:
            LLM 的响应文本
        """
        # 将 context 格式化到 prompt
        context_str = "\n".join(f"- {k}: {v}" for k, v in context.items())
        full_prompt = f"上下文信息:\n{context_str}\n\n{prompt}"
        
        return self.chat(full_prompt, system_prompt)
    
    @traceable_llm("chat_multi_round")
    def chat_multi_round(
        self,
        rounds: List[str],
        system_prompt: Optional[str] = None,
        timeout: int = 300,
    ) -> Tuple[List[str], List[str]]:
        """
        多轮对话
        
        Args:
            rounds: 每轮的 user message 列表
            system_prompt: 系统提示（可选）
            timeout: 单轮超时时间（秒）
        
        Returns:
            Tuple[List[str], List[str]]: (每轮的响应列表, 每轮的耗时列表)
        
        Raises:
            RuntimeError: 对话失败
        """
        messages = []
        
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        
        responses = []
        durations = []
        
        for i, user_message in enumerate(rounds):
            messages.append(HumanMessage(content=user_message))
            
            try:
                start_time = time.time()
                response = self._invoke_with_timeout(messages, timeout)
                duration = time.time() - start_time
                
                content = response.content
                if isinstance(content, str):
                    response_text = content
                elif isinstance(content, list):
                    response_text = "".join(str(item) for item in content)
                else:
                    response_text = str(content)
                
                messages.append(AIMessage(content=response_text))
                responses.append(response_text)
                durations.append(f"{duration:.1f}s")
                
            except self._InterruptException:
                raise
            except (httpx.StreamClosed, httpx.CloseError, httpx.ProtocolError):
                raise self._InterruptException("LLM 请求已取消")
            except Exception as e:
                raise RuntimeError(f"多轮对话第 {i+1}/{len(rounds)} 轮失败: {e}")
        
        return responses, durations
    
    def _invoke_with_timeout(
        self,
        messages: List,
        timeout: int = 300,
    ) -> Any:
        """
        带超时的 LLM 调用
        
        Args:
            messages: 消息列表
            timeout: 超时时间（秒）
        
        Returns:
            LLM 响应
        
        Raises:
            TimeoutError: 调用超时
            RuntimeError: 调用失败
        """
        import threading
        
        result = {"response": None, "error": None}
        
        def invoke():
            try:
                result["response"] = self._client.invoke(messages)
            except Exception as e:
                result["error"] = e
        
        thread = threading.Thread(target=invoke)
        thread.daemon = True
        thread.start()
        thread.join(timeout=timeout)
        
        if thread.is_alive():
            raise TimeoutError(f"LLM 调用超时 ({timeout}s)")
        
        if result["error"]:
            raise RuntimeError(f"LLM 调用失败: {result['error']}")
        
        if result["response"] is None:
            raise RuntimeError("LLM 调用未返回结果")
        
        return result["response"]


# 默认客户端实例（延迟初始化）
_default_client: Optional[LLMClient] = None


def get_default_client() -> LLMClient:
    """获取默认的 LLM 客户端实例"""
    global _default_client
    
    if _default_client is None:
        model = os.getenv("DEFAULT_MODEL", "gpt-4o-mini")
        _default_client = LLMClient(model=model)
    
    return _default_client


def create_client(
    model: Optional[str] = None,
    **kwargs,
) -> LLMClient:
    """
    创建 LLM 客户端的便捷函数
    
    Args:
        model: 模型名称（None 则从环境变量读取）
        **kwargs: 其他参数传递给 LLMClient
    
    Returns:
        LLMClient 实例
    """
    if model is None:
        model = os.getenv("DEFAULT_MODEL", "gpt-4o-mini")
    return LLMClient(model=model, **kwargs)