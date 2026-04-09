"""工具选择 Agent - 智能选择使用哪个工具

⚠️ 当前状态：未使用（保留用于未来扩展）

设计意图：
- 动态选择和组合工具
- LLM驱动的工具选择
- 灵活的工作流编排

当前未使用原因：
1. 核心功能编排需要稳定性和可预测性
2. 动态工具选择增加不确定性和复杂度
3. 静态工作流模板（WORKFLOW_TEMPLATES）已满足当前需求
4. 避免不必要的LLM调用开销

未来计划：
- 在附加功能中使用动态工具选择
- 例如：自定义分析流程、插件系统、用户定义工作流
- 届时将添加配置开关：静态模式（默认）/ 动态模式

参考：
- OrchestratorAgent 当前使用 WORKFLOW_TEMPLATES
- ARCHITECTURE.md 未来功能章节

元信息：
- 创建时间：2026-03
- 最后审查：2026-04-06
- 状态：保留未使用
"""
import json
from typing import Optional, List, Dict, Any

try:
    from evaluator.llm import LLMClient
    HAS_LLM = True
except ImportError:
    HAS_LLM = False
    LLMClient = None

from evaluator.agents.base_agent import BaseAgent, AgentMeta


class ToolSelectionAgent(BaseAgent):
    """工具选择 Agent
    
    职责：
    1. 根据任务描述选择合适的工具
    2. 评估工具执行的上下文
    3. 生成工具调用参数
    """
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="ToolSelectionAgent",
            description="智能选择工具组合",
            category="orchestration",
            inputs=["task_description", "context"],
            outputs=["selected_tools", "tool_params"],
            dependencies=["IntentParserAgent"],
        )
    
    def __init__(self, llm: Optional["LLMClient"] = None):
        super().__init__()
        self.llm = llm
    
    TOOLS = {
        "extract_ci_data": {
            "name": "extract_ci_data",
            "description": "提取项目的 CI/CD 配置数据（GitHub Actions 工作流、Jobs、Steps 等）",
            "category": "analysis",
            "input": "project_path",
            "output": "ci_data",
        },
        "clone_repository": {
            "name": "clone_repository",
            "description": "克隆远程 Git 仓库到本地",
            "category": "utility",
            "input": "url, target_dir",
            "output": "local_path",
        },
        "parse_url": {
            "name": "parse_url",
            "description": "解析 Git 仓库 URL，获取项目信息",
            "category": "utility",
            "input": "url",
            "output": "project_info",
        },
        "generate_prompt": {
            "name": "generate_prompt",
            "description": "根据 CI/CD 数据生成分析 Prompt",
            "category": "analysis",
            "input": "ci_data",
            "output": "prompt",
        },
        "list_projects": {
            "name": "list_projects",
            "description": "列出已保存的项目列表",
            "category": "storage",
            "input": "none",
            "output": "project_list",
        },
        "get_project": {
            "name": "get_project",
            "description": "获取项目的详细信息",
            "category": "storage",
            "input": "project_name",
            "output": "project_detail",
        },
    }
    
    TASK_TOOLS = {
        "analyze_local": ["extract_ci_data", "generate_prompt"],
        "analyze_url": ["parse_url", "clone_repository", "extract_ci_data", "generate_prompt"],
        "compare": ["get_project", "get_project"],
        "list": ["list_projects"],
    }
    
    def select_tools(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """选择合适的工具
        
        Args:
            task: 任务描述
            context: 上下文信息
        
        Returns:
            工具配置列表，每个包含 tool_name, params, reason
        """
        context = context or {}
        
        if self.llm:
            return self._select_with_llm(task, context)
        return self._select_with_rules(task, context)
    
    def _select_with_llm(
        self,
        task: str,
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """使用 LLM 选择工具"""
        tools_json = json.dumps(self.TOOLS, ensure_ascii=False, indent=2)
        
        prompt = f"""任务: {task}
上下文: {json.dumps(context, ensure_ascii=False)[:1000]}

可用工具:
{tools_json}

请分析任务和上下文，选择最合适的工具组合。
输出 JSON 数组格式:
[
  {{"tool_name": "工具名", "params": {{"参数"}}, "reason": "选择理由"}},
  ...
]

只输出 JSON，不要其他内容。"""
        
        try:
            response = self.llm.chat(prompt)
            result = json.loads(response)
            
            selected = []
            for item in result:
                tool_name = item.get("tool_name")
                if tool_name in self.TOOLS:
                    selected.append({
                        "tool_name": tool_name,
                        "params": item.get("params", {}),
                        "reason": item.get("reason", ""),
                    })
            
            return selected
        except:
            return self._select_with_rules(task, context)
    
    def _select_with_rules(
        self,
        task: str,
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """使用规则选择工具"""
        task_lower = task.lower()
        selected = []
        
        if "克隆" in task_lower or "clone" in task_lower:
            url = context.get("url", "")
            selected.append({
                "tool_name": "parse_url",
                "params": {"url": url},
                "reason": "解析 URL 获取项目信息",
            })
            selected.append({
                "tool_name": "clone_repository",
                "params": {"url": url},
                "reason": "克隆远程仓库",
            })
        
        if "分析" in task_lower or "analyze" in task_lower:
            project_path = context.get("project_path")
            if project_path:
                selected.append({
                    "tool_name": "extract_ci_data",
                    "params": {"project_path": project_path},
                    "reason": "提取 CI/CD 数据",
                })
        
        if "对比" in task_lower or "compare" in task_lower:
            project_a = context.get("project_a")
            project_b = context.get("project_b")
            if project_a:
                selected.append({
                    "tool_name": "get_project",
                    "params": {"name": project_a},
                    "reason": f"获取项目 {project_a} 信息",
                })
            if project_b:
                selected.append({
                    "tool_name": "get_project",
                    "params": {"name": project_b},
                    "reason": f"获取项目 {project_b} 信息",
                })
        
        if "列表" in task_lower or "list" in task_lower:
            selected.append({
                "tool_name": "list_projects",
                "params": {},
                "reason": "获取项目列表",
            })
        
        return selected
    
    def execute_tool(
        self,
        tool_name: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行工具
        
        Args:
            tool_name: 工具名称
            params: 工具参数
        
        Returns:
            执行结果
        """
        from evaluator.skills import get_tool_by_name
        
        tool = get_tool_by_name(tool_name)
        if tool is None:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
        
        try:
            result = tool.invoke(**params)
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def execute_with_tools(
        self,
        tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """顺序执行多个工具
        
        Args:
            tools: 工具配置列表
        
        Returns:
            执行结果列表
        """
        results = []
        context = {}
        
        for tool_config in tools:
            tool_name = tool_config.get("tool_name")
            params = tool_config.get("params", {})
            
            merged_params = {**params, **context}
            
            result = self.execute_tool(tool_name, merged_params)
            results.append({
                "tool_name": tool_name,
                "result": result,
                "reason": tool_config.get("reason", ""),
            })
            
            if result.get("success"):
                result_data = result.get("result", {})
                if isinstance(result_data, dict):
                    context.update(result_data)
        
        return results
    
    def get_tool_info(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """获取工具信息"""
        return self.TOOLS.get(tool_name)
    
    def list_tools_by_category(self, category: str) -> List[Dict[str, Any]]:
        """按类别列出工具"""
        return [
            {"name": name, **info}
            for name, info in self.TOOLS.items()
            if info.get("category") == category
        ]
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具选择（LangGraph 节点）"""
        task = state.get("task_description", "")
        context = state.get("context", {})
        
        tools = self.select_tools(task, context)
        
        return {**state, "selected_tools": tools}
