"""对话上下文管理 - 支持多轮对话"""
from typing import List, Optional, Any, Dict
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Turn:
    """单轮对话"""
    user_input: str
    intent: str
    params: Dict[str, Any]
    result: Optional[Any] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class ConversationContext:
    """多轮对话上下文管理器"""
    
    def __init__(self, max_history: int = 10):
        """
        Args:
            max_history: 最大历史记录数
        """
        self.history: List[Turn] = []
        self.max_history = max_history
        self.last_project: Optional[str] = None
        self.last_projects: List[str] = []
        self.last_action: Optional[str] = None
    
    def add_turn(self, user_input: str, intent: str, params: Dict[str, Any], result: Any = None):
        """记录一轮对话
        
        Args:
            user_input: 用户输入
            intent: 识别的意图
            params: 解析的参数
            result: 执行结果
        """
        turn = Turn(
            user_input=user_input,
            intent=intent,
            params=params,
            result=result,
        )
        
        self.history.append(turn)
        
        # 维护最近引用的项目
        if intent == "analyze" and params.get("project"):
            self.last_project = params["project"]
            self._add_to_last_projects(params["project"])
        elif intent == "compare":
            if params.get("project_a"):
                self._add_to_last_projects(params["project_a"])
            if params.get("project_b"):
                self._add_to_last_projects(params["project_b"])
        
        self.last_action = intent
        
        # 限制历史长度
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
    
    def _add_to_last_projects(self, project: str):
        """添加到最近项目列表"""
        if project in self.last_projects:
            self.last_projects.remove(project)
        self.last_projects.insert(0, project)
        if len(self.last_projects) > 5:
            self.last_projects = self.last_projects[:5]
    
    def get_context_for_prompt(self) -> str:
        """生成上下文信息供 LLM 使用
        
        Returns:
            格式化的上下文字符串
        """
        if not self.history:
            return "(无历史对话)"
        
        lines = []
        for i, turn in enumerate(reversed(self.history[:3]), 1):
            lines.append(f"[最近 {i}] {turn.intent}: {turn.user_input}")
            if turn.params:
                lines.append(f"       参数: {turn.params}")
        
        return "\n".join(lines)
    
    def resolve_reference(self, ref: str) -> Optional[str]:
        """解析引用（如 "这个项目"、"它"、"那个仓库"）
        
        Args:
            ref: 引用词
        
        Returns:
            解析后的项目名，或 None
        """
        ref_lower = ref.lower().strip()
        
        # 直接的项目引用
        direct_refs = {
            "这个": "last_project",
            "那个": "last_project",
            "它": "last_project",
            "这个项目": "last_project",
            "那个项目": "last_project",
            "它": "last_project",
            "刚才的": "last_project",
            "上一个": "last_project",
            "最近": "last_project",
        }
        
        if ref_lower in direct_refs:
            return self.last_project
        
        # 最近对比的项目
        if ref_lower in ["第一个", "前一个", "a"]:
            return self.last_projects[0] if self.last_projects else None
        
        if ref_lower in ["第二个", "后一个", "b"]:
            return self.last_projects[1] if len(self.last_projects) > 1 else None
        
        # 数字索引
        if ref_lower.isdigit():
            idx = int(ref_lower) - 1
            if 0 <= idx < len(self.last_projects):
                return self.last_projects[idx]
        
        return None
    
    def get_last_analyze_result(self) -> Optional[Any]:
        """获取最近一次分析结果"""
        for turn in reversed(self.history):
            if turn.intent == "analyze" and turn.result:
                return turn.result
        return None
    
    def get_last_compare_result(self) -> Optional[Any]:
        """获取最近一次对比结果"""
        for turn in reversed(self.history):
            if turn.intent == "compare" and turn.result:
                return turn.result
        return None
    
    def clear(self):
        """清空上下文"""
        self.history.clear()
        self.last_project = None
        self.last_projects.clear()
        self.last_action = None


# 全局上下文实例
_global_context: Optional[ConversationContext] = None


def get_context() -> ConversationContext:
    """获取全局上下文实例"""
    global _global_context
    if _global_context is None:
        _global_context = ConversationContext()
    return _global_context


def reset_context():
    """重置全局上下文"""
    global _global_context
    _global_context = None
