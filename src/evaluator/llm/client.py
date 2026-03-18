"""LLM 客户端 - Agent 的核心组件"""
import os
from typing import Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage


class LLMClient:
    """
    LLM 调用客户端
    
    作为 Agent 的核心组件，提供 LLM 调用能力。
    支持 OpenAI API 及兼容的 API（如 Azure OpenAI, 本地模型等）
    """
    
    def __init__(
        self,
        provider: str = "openai",
        model: str = "gpt-4o-mini",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ):
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
        client_kwargs = {
            "model": model,
            "api_key": self.api_key,
            "base_url": self.base_url,
            "temperature": temperature,
        }
        
        # 设置 max_tokens：None 时使用 131072（128K），确保不会被截断
        client_kwargs["max_tokens"] = max_tokens if max_tokens is not None else 131072
        
        self._client = ChatOpenAI(**client_kwargs)
    
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