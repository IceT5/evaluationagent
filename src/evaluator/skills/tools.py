"""LangChain Tools for CI/CD analysis

将 Skills 转换为 LangChain Tools，支持 LangSmith 追踪。
"""
from typing import Optional, Dict, Any, List
from functools import partial

try:
    from langchain_core.tools import tool, BaseTool
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    tool = None
    BaseTool = object


from evaluator.llm.tracing import traceable_tool


class ExtractCIDataTool:
    """提取 CI/CD 数据工具"""
    
    name = "extract_ci_data"
    description = """
    提取项目的 CI/CD 数据，包括：
    - GitHub Actions 工作流配置
    - Jobs 和 Steps 定义
    - Trigger 触发条件
    - Action 使用情况
    
    Args:
        project_path: 项目根目录路径
    
    Returns:
        包含 workflows, jobs, triggers 等信息的字典
    """
    
    def __init__(self):
        self._func = None
    
    @property
    def func(self):
        if self._func is None:
            from evaluator.skills import CIAnalyzer
            analyzer = CIAnalyzer()
            self._func = analyzer.extract_data
        return self._func
    
    @traceable_tool("extract_ci_data")
    def invoke(self, project_path: str) -> Dict[str, Any]:
        """同步调用"""
        return self.func(project_path)
    
    async def ainvoke(self, project_path: str) -> Dict[str, Any]:
        """异步调用"""
        return self.invoke(project_path)


class CloneRepositoryTool:
    """克隆远程仓库工具"""
    
    name = "clone_repository"
    description = """
    克隆远程 Git 仓库到本地目录。
    
    Args:
        url: Git 仓库 URL (GitHub/GitLab)
        target_dir: 目标目录（可选，默认自动生成）
        branch: 指定分支（可选）
    
    Returns:
        {
            "success": bool,
            "path": str,  # 克隆到的本地路径
            "error": str,  # 失败原因
        }
    """
    
    def __init__(self):
        self._func = None
    
    @property
    def func(self):
        if self._func is None:
            from evaluator.skills import GitOperations
            self._func = GitOperations.clone
        return self._func
    
    @traceable_tool("clone_repository")
    def invoke(self, url: str, target_dir: Optional[str] = None, branch: Optional[str] = None) -> Dict[str, Any]:
        """同步调用"""
        if target_dir:
            return self.func(url, target_dir, branch)
        return self.func(url, "", branch)
    
    async def ainvoke(self, url: str, target_dir: Optional[str] = None, branch: Optional[str] = None) -> Dict[str, Any]:
        """异步调用"""
        return self.invoke(url, target_dir, branch)


class ParseURLTool:
    """解析 URL 工具"""
    
    name = "parse_url"
    description = """
    解析 Git 仓库 URL，获取项目信息。
    
    Args:
        url: Git 仓库 URL
    
    Returns:
        {
            "platform": str,  # github/gitlab
            "owner": str,
            "repo": str,
            "project_name": str,
        }
    """
    
    def __init__(self):
        self._func = None
    
    @property
    def func(self):
        if self._func is None:
            from evaluator.skills import UrlParser
            self._func = UrlParser.parse
        return self._func
    
    @traceable_tool("parse_url")
    def invoke(self, url: str) -> Dict[str, Any]:
        """同步调用"""
        return self.func(url)
    
    async def ainvoke(self, url: str) -> Dict[str, Any]:
        """异步调用"""
        return self.invoke(url)


class GeneratePromptTool:
    """生成分析 Prompt 工具"""
    
    name = "generate_ci_prompt"
    description = """
    生成 CI/CD 分析的 LLM Prompt。
    
    Args:
        ci_data: CI/CD 数据字典或 JSON 字符串
        output_file: 输出文件路径（可选）
    
    Returns:
        生成的 prompt 文本
    """
    
    def __init__(self):
        self._func = None
    
    @property
    def func(self):
        if self._func is None:
            from evaluator.skills import CIAnalyzer
            analyzer = CIAnalyzer()
            self._func = analyzer.generate_prompt
        return self._func
    
    @traceable_tool("generate_ci_prompt")
    def invoke(self, ci_data: Dict[str, Any], output_file: Optional[str] = None) -> str:
        """同步调用"""
        return self.func(ci_data, output_file)
    
    async def ainvoke(self, ci_data: Dict[str, Any], output_file: Optional[str] = None) -> str:
        """异步调用"""
        return self.invoke(ci_data, output_file)


class ListProjectsTool:
    """列出已分析项目工具"""
    
    name = "list_projects"
    description = """
    列出已保存的项目列表。
    
    Returns:
        项目信息列表
    """
    
    @traceable_tool("list_projects")
    def invoke(self) -> List[Dict[str, Any]]:
        """同步调用"""
        from evaluator.core import list_projects
        projects = list_projects()
        return [
            {
                "name": p.name,
                "display_name": p.display_name,
                "latest_version": p.latest_version,
            }
            for p in projects
        ]
    
    async def ainvoke(self) -> List[Dict[str, Any]]:
        """异步调用"""
        return self.invoke()


class GetProjectTool:
    """获取项目详情工具"""
    
    name = "get_project"
    description = """
    获取项目的详细信息。
    
    Args:
        name: 项目名称
    
    Returns:
        项目详情
    """
    
    @traceable_tool("get_project")
    def invoke(self, name: str) -> Optional[Dict[str, Any]]:
        """同步调用"""
        from evaluator.core import get_project
        project = get_project(name)
        if project:
            return {
                "name": project.name,
                "display_name": project.display_name,
                "source_url": project.source_url,
                "versions": project.versions,
            }
        return None
    
    async def ainvoke(self, name: str) -> Optional[Dict[str, Any]]:
        """异步调用"""
        return self.invoke(name)


def get_all_tools() -> List:
    """获取所有 LangChain Tools
    
    Returns:
        工具列表
    """
    return [
        ExtractCIDataTool(),
        CloneRepositoryTool(),
        ParseURLTool(),
        GeneratePromptTool(),
        ListProjectsTool(),
        GetProjectTool(),
    ]


def get_tool_by_name(name: str):
    """根据名称获取工具"""
    tools = {t.name: t for t in get_all_tools()}
    return tools.get(name)
