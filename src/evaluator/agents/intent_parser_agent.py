# Intent Parser Agent - 解析用户自然语言输入

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

try:
    from evaluator.llm import LLMClient
    HAS_LLM = True
except ImportError:
    HAS_LLM = False

from .base_agent import BaseAgent, AgentMeta


class Intent(Enum):
    """用户意图类型"""
    ANALYZE = "analyze"
    COMPARE = "compare"
    LIST = "list"
    INFO = "info"
    HELP = "help"
    DELETE = "delete"
    UNKNOWN = "unknown"


class ParsedIntent(BaseModel):
    """解析后的意图"""
    intent: Intent
    params: Dict[str, Any]
    confidence: float
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    raw_input: str


INTENT_PARSER_PROMPT = """你是一个 CLI 命令解析器。

## 支持的命令

1. **analyze** - 分析项目的 CI/CD 架构
2. **compare** - 对比两个项目的 CI/CD 架构
3. **list** - 列出已分析的项目
4. **info** - 查看项目详情
5. **help** - 获取帮助
6. **delete** - 删除项目

## 已知项目列表

{known_projects}

## 用户输入

{user_input}

## 输出要求

只输出 JSON，不要输出任何其他文字。不要使用代码块。JSON 必须是单行。

格式: {{"intent":"xxx","params":{{"project":"xxx"}},"confidence":0.0,"needs_clarification":false,"clarification_question":null}}

JSON:
"""


class IntentParserAgent(BaseAgent):
    """意图解析 Agent - 支持 LangGraph 节点接口"""

    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="IntentParserAgent",
            description="解析用户自然语言输入，识别意图和参数",
            category="entry",
            inputs=["user_input"],
            outputs=["intent", "params", "orchestrator_decision", "needs_clarification"],
            dependencies=[],
        )

    def __init__(self, llm: Optional["LLMClient"] = None):
        super().__init__()
        self.llm = llm

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行意图解析 - LangGraph 节点接口
        
        如果 intent 和 orchestrator_decision 已存在，跳过解析直接返回。
        这允许 CLI 直接设置意图而不重复解析。
        
        Args:
            state: 包含以下字段:
                - user_input: 用户输入文本（可选）
                - known_projects: 已知项目列表（可选）
                - context: 上下文信息（可选）
                - intent: 已解析的意图（可选，若存在则跳过解析）
                - orchestrator_decision: 已有的编排决策（可选）
        
        Returns:
            更新后的状态，包含:
                - intent: 意图类型
                - params: 意图参数
                - orchestrator_decision: 编排决策
                - clarification_question: 澄清问题（如果需要）
        """
        existing_intent = state.get("intent")
        existing_decision = state.get("orchestrator_decision", {})
        
        if existing_intent and existing_decision.get("next_step"):
            print(f"[DEBUG] IntentParser: 意图已解析 ({existing_intent})，跳过")
            return state
        
        user_input = state.get("user_input", "")
        known_projects = state.get("known_projects", [])
        context = state.get("context", {})
        
        parsed = self._parse(user_input, known_projects, context)
        
        orchestrator_decision = {
            "intent": parsed.intent.value,
            "params": parsed.params,
            "confidence": parsed.confidence,
            "needs_clarification": parsed.needs_clarification,
            "clarification_question": parsed.clarification_question,
            "next_step": self._get_next_step(parsed),
        }
        
        return {
            **state,
            "intent": parsed.intent.value,
            "params": parsed.params,
            "orchestrator_decision": orchestrator_decision,
            "clarification_question": parsed.clarification_question,
            "needs_clarification": parsed.needs_clarification,
        }
    
    def _get_next_step(self, parsed: ParsedIntent) -> str:
        """根据解析结果获取下一步
        
        Args:
            parsed: 解析结果
        
        Returns:
            下一个节点名称
        """
        if parsed.needs_clarification:
            return "end"
        
        intent_to_step = {
            "analyze": "input",
            "compare": "compare",
            "list": "list_handler",
            "info": "info_handler",
            "delete": "delete_handler",
            "help": "help_handler",
        }
        
        return intent_to_step.get(parsed.intent.value, "end")
    
    def _parse(self, user_input: str, known_projects: List[str], context: Optional[dict] = None) -> ParsedIntent:
        """解析用户输入 - 内部实现
        
        Args:
            user_input: 用户输入文本
            known_projects: 已知项目列表
            context: 可选的上下文信息
        
        Returns:
            ParsedIntent: 解析后的意图
        """
        if user_input.startswith('/'):
            return self._parse_traditional(user_input)
        
        return self._parse_natural(user_input, known_projects, context)
    
    def parse(self, user_input: str, known_projects: List[str], context: Optional[dict] = None) -> ParsedIntent:
        """解析用户输入 - 兼容旧接口
        
        Args:
            user_input: 用户输入文本
            known_projects: 已知项目列表
            context: 可选的上下文信息
        
        Returns:
            ParsedIntent: 解析后的意图
        """
        return self._parse(user_input, known_projects, context)
    
    def _parse_traditional(self, user_input: str) -> ParsedIntent:
        """解析传统命令格式
        
        支持格式:
            /analyze path
            /compare project_a project_b
            /list
            /info project
            /help
            /delete project
        """
        parts = user_input[1:].split()
        if not parts:
            return ParsedIntent(
                intent=Intent.UNKNOWN,
                params={},
                confidence=0.0,
                needs_clarification=True,
                clarification_question="请输入有效的命令",
                raw_input=user_input,
            )
        
        command = parts[0].lower()
        params = {}
        
        if command == "analyze" and len(parts) >= 2:
            return ParsedIntent(
                intent=Intent.ANALYZE,
                params={"project": " ".join(parts[1:])},
                confidence=1.0,
                raw_input=user_input,
            )
        
        elif command == "compare" and len(parts) >= 3:
            return ParsedIntent(
                intent=Intent.COMPARE,
                params={"project_a": parts[1], "project_b": parts[2]},
                confidence=1.0,
                raw_input=user_input,
            )
        
        elif command == "list":
            return ParsedIntent(
                intent=Intent.LIST,
                params={},
                confidence=1.0,
                raw_input=user_input,
            )
        
        elif command == "info" and len(parts) >= 2:
            return ParsedIntent(
                intent=Intent.INFO,
                params={"project": " ".join(parts[1:])},
                confidence=1.0,
                raw_input=user_input,
            )
        
        elif command == "help":
            return ParsedIntent(
                intent=Intent.HELP,
                params={},
                confidence=1.0,
                raw_input=user_input,
            )
        
        elif command == "delete" and len(parts) >= 2:
            return ParsedIntent(
                intent=Intent.DELETE,
                params={"project": " ".join(parts[1:])},
                confidence=1.0,
                raw_input=user_input,
            )
        
        return ParsedIntent(
            intent=Intent.UNKNOWN,
            params={},
            confidence=0.0,
            needs_clarification=True,
            clarification_question=f"无法识别的命令: {command}",
            raw_input=user_input,
        )
    
    def _parse_natural(self, user_input: str, known_projects: List[str], context: Optional[dict] = None) -> ParsedIntent:
        """使用 LLM 解析自然语言"""
        if not self.llm or not HAS_LLM:
            print("[DEBUG] IntentParser: 无 LLM，使用 _simple_parse")
            return self._simple_parse(user_input, known_projects, context)
        
        try:
            context_str = ""
            if context and context.get("last_project"):
                context_str = f"\n\n## 上下文\n最近分析的项目: {context['last_project']}"
            
            prompt = INTENT_PARSER_PROMPT.format(
                known_projects="\n".join(f"- {p}" for p in known_projects) or "(无)",
                user_input=user_input,
            ) + context_str
            
            print(f"[DEBUG] IntentParser: 调用 LLM 解析: {user_input[:50]}...")
            response = self.llm.chat(prompt)
            print(f"[DEBUG] IntentParser: LLM 响应: {response[:100]}...")
            return self._parse_llm_response(response, user_input)
        
        except Exception as e:
            print(f"[DEBUG] IntentParser: LLM 调用失败: {e}，使用 _simple_parse")
            return self._simple_parse(user_input, known_projects, context)
    
    def _parse_llm_response(self, response: str, raw_input: str) -> ParsedIntent:
        """解析 LLM 返回的 JSON"""
        import json
        import re
        
        json_str = None
        
        # 方法1: 提取 ```json ... ``` 代码块
        code_block_match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
        if code_block_match:
            json_str = code_block_match.group(1).strip()
        
        # 方法2: 找第一个 { 到最后一个 } 之间的内容
        if not json_str:
            start = response.find('{')
            end = response.rfind('}')
            if start != -1 and end != -1 and end > start:
                json_str = response[start:end+1]
        
        if not json_str:
            return self._simple_parse(raw_input, [], None)
        
        try:
            data = json.loads(json_str)
            
            intent_str = data.get("intent", "unknown").lower()
            intent = Intent(intent_str) if intent_str in [i.value for i in Intent] else Intent.UNKNOWN
            
            return ParsedIntent(
                intent=intent,
                params=data.get("params", {}),
                confidence=float(data.get("confidence", 0.5)),
                needs_clarification=data.get("needs_clarification", False),
                clarification_question=data.get("clarification_question"),
                raw_input=raw_input,
            )
        except (json.JSONDecodeError, ValueError):
            return self._simple_parse(raw_input, [], None)
    
    def _simple_parse(self, user_input: str, known_projects: List[str], context: Optional[dict] = None) -> ParsedIntent:
        """简单的规则匹配解析 - 意图优先检测"""
        import re
        user_lower = user_input.lower().strip()
        
        last_project = context.get("last_project") if context else None
        
        help_keywords = ["帮助", "help", "怎么用", "使用", "使用说明", 
                        "你是做什么的", "你是谁", "介绍", "功能", "能做什么", "有什么用", "什么工具"]
        
        if any(word in user_lower for word in help_keywords):
            return ParsedIntent(
                intent=Intent.HELP,
                params={},
                confidence=0.9,
                raw_input=user_input,
            )
        
        analyze_keywords = ["分析", "analyze", "看看", "查看", "检视", "看一下"]
        if any(word in user_lower for word in analyze_keywords):
            project = self._extract_project_name(user_input, known_projects)
            if project:
                return ParsedIntent(
                    intent=Intent.ANALYZE,
                    params={"project": project},
                    confidence=0.85,
                    raw_input=user_input,
                )
            return ParsedIntent(
                intent=Intent.ANALYZE,
                params={},
                confidence=0.5,
                needs_clarification=True,
                clarification_question="请指定要分析的项目路径、URL 或名称",
                raw_input=user_input,
            )
        
        compare_keywords = ["对比", "比较", "compare"]
        if any(word in user_lower for word in compare_keywords):
            projects = self._extract_two_projects(user_input, known_projects)
            if projects["project_a"]:
                return ParsedIntent(
                    intent=Intent.COMPARE,
                    params=projects,
                    confidence=0.85,
                    raw_input=user_input,
                )
            return ParsedIntent(
                intent=Intent.COMPARE,
                params={},
                confidence=0.5,
                needs_clarification=True,
                clarification_question="请指定要对比的两个项目名称或路径",
                raw_input=user_input,
            )
        
        list_keywords = ["有哪些", "列表", "list", "显示", "查看"]
        if any(word in user_lower for word in list_keywords):
            if "项目" in user_lower or "project" in user_lower:
                return ParsedIntent(
                    intent=Intent.LIST,
                    params={},
                    confidence=0.9,
                    raw_input=user_input,
                )
        
        info_keywords = ["详情", "信息", "详细", "info"]
        if any(word in user_lower for word in info_keywords):
            project = self._extract_project_name(user_input, known_projects) or last_project
            if project:
                return ParsedIntent(
                    intent=Intent.INFO,
                    params={"project": project},
                    confidence=0.85,
                    raw_input=user_input,
                )
        
        delete_keywords = ["删除", "remove", "移除"]
        if any(word in user_lower for word in delete_keywords):
            project = self._extract_project_name(user_input, known_projects)
            if project:
                return ParsedIntent(
                    intent=Intent.DELETE,
                    params={"project": project},
                    confidence=0.85,
                    raw_input=user_input,
                )
        
        if "github.com" in user_lower or "gitlab.com" in user_lower:
            from evaluator.skills import UrlParser
            if UrlParser.is_url(user_input.strip()):
                parsed = UrlParser.parse(user_input.strip())
                project_name = UrlParser.get_project_name(parsed)
                return ParsedIntent(
                    intent=Intent.ANALYZE,
                    params={"url": user_input.strip(), "project": project_name},
                    confidence=0.95,
                    raw_input=user_input,
                )
        
        if context and context.get("last_project"):
            reference_words = ["这个", "它", "这个项目", "那个", "刚才", "上一个"]
            for ref in reference_words:
                if ref in user_lower:
                    return ParsedIntent(
                        intent=Intent.UNKNOWN,
                        params={"project": context["last_project"]},
                        confidence=0.3,
                        needs_clarification=True,
                        clarification_question=f"您是指 '{context['last_project']}' 这个项目吗？请明确操作（分析、对比、查看详情）",
                        raw_input=user_input,
                    )
        
        return ParsedIntent(
            intent=Intent.UNKNOWN,
            params={},
            confidence=0.0,
            needs_clarification=True,
            clarification_question="我无法理解您的输入。请尝试：\n  - /analyze <项目路径或URL>\n  - /compare <项目A> <项目B>\n  - /list\n  - /help",
            raw_input=user_input,
        )
    
    def _extract_project_name(self, user_input: str, known_projects: List[str]) -> Optional[str]:
        """从自然语言中提取项目名称"""
        import re
        user_lower = user_input.lower()
        
        for project in known_projects:
            if project.lower() in user_lower:
                return project
        
        path_patterns = [
            r'([A-Za-z]:\\[^\s]+)',  # Windows: F:\code\cccl
            r'(/[^\s/]+)+',          # Unix: /home/user/project
            r'(https?://[^\s]+)',     # URL
        ]
        for pattern in path_patterns:
            match = re.search(pattern, user_input)
            if match:
                return match.group(1)
        
        project_match = re.search(r'([^\s]+)\s*项目', user_input)
        if project_match:
            return project_match.group(1)
        
        for project in known_projects:
            words = user_input.split()
            for word in words:
                if project.lower() in word.lower() or word.lower() in project.lower():
                    return project
        
        words = user_input.split()
        for i, word in enumerate(words):
            if '项目' in word:
                if i > 0:
                    return words[i-1]
                for j in range(i-1, -1, -1):
                    if words[j] not in ['分析', '看看', '查看', '对比', '比较']:
                        return words[j]
        
        return None
    
    def _extract_two_projects(self, user_input: str, known_projects: List[str]) -> Dict[str, Optional[str]]:
        """从自然语言中提取两个项目名称"""
        project_a = None
        project_b = None
        
        found_projects = []
        for project in known_projects:
            if project.lower() in user_input.lower():
                found_projects.append(project)
        
        if len(found_projects) >= 2:
            return {"project_a": found_projects[0], "project_b": found_projects[1]}
        
        if len(found_projects) == 1:
            project_a = found_projects[0]
        
        import re
        path_patterns = [
            r'([A-Za-z]:\\[^\s]+)',
            r'(/[^\s/]+)+',
        ]
        paths = []
        for pattern in path_patterns:
            matches = re.findall(pattern, user_input)
            paths.extend(matches)
        
        if len(paths) >= 2:
            return {"project_a": paths[0], "project_b": paths[1]}
        
        if len(paths) == 1:
            if project_a is None:
                project_a = paths[0]
            else:
                project_b = paths[0]
        
        return {"project_a": project_a, "project_b": project_b}
