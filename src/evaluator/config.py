"""全局配置模块

配置来源优先级：
1. 系统环境变量（最高优先级）
2. .env 文件（通过 load_dotenv 加载）
3. 默认值（fallback）

使用示例：
    from evaluator.config import config
    max_retries = config.max_retries
"""
import os
from dataclasses import dataclass
from typing import Optional


def parse_bool_env(value: Optional[str]) -> Optional[bool]:
    """解析布尔环境变量。

    返回:
        True/False: 成功解析
        None: 未设置或值非法
    """
    if value is None:
        return None

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def resolve_interactive_mode(*, studio_mode: bool = False) -> bool:
    """统一计算 interactive_mode。

    优先级：
    1. EVAL_INTERACTIVE_MODE 环境变量
    2. Studio 入口默认 False
    3. 其他场景默认 True
    """
    env_override = parse_bool_env(os.getenv("EVAL_INTERACTIVE_MODE"))
    if env_override is not None:
        return env_override

    return not studio_mode


@dataclass
class Config:
    """全局配置"""
    
    # === 重试配置 ===
    # 业务逻辑最大重试次数
    max_retries: int = 3
    # LLM 调用最大重试次数
    llm_max_retries: int = 5
    # LLM 重试基础延迟（秒），实际延迟 = base_delay * attempt
    llm_retry_base_delay: float = 1.0
    
    # === 并发配置 ===
    # 后台任务线程数
    max_background_workers: int = 1
    # Review 并发数
    max_llm_workers: int = 4
    # LLM 并发调用数
    max_concurrent_llm_calls: int = 4
    
    # === 超时配置（秒）===
    # Git 克隆超时
    git_clone_timeout: int = 300
    # LLM HTTP 请求超时
    llm_request_timeout: int = 300
    # LLM 调用超时
    llm_call_timeout: int = 600
    
    # === LLM 配置 ===
    # LLM 最大输出 token
    llm_max_tokens: int = 131072
    
    # === 报告配置 ===
    # 报告最大章节长度
    max_section_length: int = 3000
    # 单次 prompt 最大工作流数（兜底限制）
    max_workflows_single: int = 20
    # 每批工作流数（兜底限制）
    max_workflows_batch: int = 10
    
    # === Prompt 策略配置 ===
    # 单次调用最大 prompt 占比（相对于 llm_max_tokens）
    max_single_prompt_ratio: float = 0.7
    # 每批次最大 prompt 占比
    max_batch_prompt_ratio: float = 0.5
    
    @classmethod
    def from_env(cls) -> "Config":
        """从环境变量加载配置"""
        def get_int(key: str, default: int) -> int:
            try:
                return int(os.getenv(key, str(default)))
            except ValueError:
                return default
        
        def get_float(key: str, default: float) -> float:
            try:
                return float(os.getenv(key, str(default)))
            except ValueError:
                return default
        
        return cls(
            # 重试配置
            max_retries=get_int("EVAL_MAX_RETRIES", 3),
            llm_max_retries=get_int("EVAL_LLM_MAX_RETRIES", 5),
            llm_retry_base_delay=get_float("EVAL_LLM_RETRY_DELAY", 1.0),
            # 并发配置
            max_background_workers=get_int("EVAL_MAX_WORKERS", 1),
            max_llm_workers=get_int("EVAL_LLM_WORKERS", 4),
            max_concurrent_llm_calls=get_int("EVAL_LLM_CONCURRENT", 4),
            # 超时配置
            git_clone_timeout=get_int("EVAL_GIT_TIMEOUT", 300),
            llm_request_timeout=get_int("EVAL_LLM_REQUEST_TIMEOUT", 300),
            llm_call_timeout=get_int("EVAL_LLM_TIMEOUT", 600),
            # LLM 配置
            llm_max_tokens=get_int("EVAL_LLM_MAX_TOKENS", 131072),
            # 报告配置
            max_section_length=get_int("EVAL_MAX_SECTION_LENGTH", 3000),
            max_workflows_single=get_int("EVAL_MAX_WORKFLOWS_SINGLE", 20),
            max_workflows_batch=get_int("EVAL_MAX_WORKFLOWS_BATCH", 10),
            # Prompt 策略配置
            max_single_prompt_ratio=get_float("EVAL_MAX_SINGLE_PROMPT_RATIO", 0.7),
            max_batch_prompt_ratio=get_float("EVAL_MAX_BATCH_PROMPT_RATIO", 0.5),
        )


# 全局配置实例
config = Config.from_env()
