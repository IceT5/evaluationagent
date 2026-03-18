"""Input Agent - 交互式获取用户输入"""
from pathlib import Path
from evaluator.skills import UrlParser


class InputAgent:
    """输入处理 Agent"""

    def __init__(self, user_input: str | None = None):
        """
        Args:
            user_input: 可选，直接传入输入（用于测试或程序化调用）
        """
        self.user_input = user_input

    def run(self, state: dict) -> dict:
        """
        职责：
        1. 获取用户输入（项目路径或 URL）
        2. 判断输入类型
        3. 更新状态

        Returns:
            更新后的状态片段
        """
        print("\n" + "=" * 50)
        print("  开源项目工程能力评估器")
        print("=" * 50)

        # 获取输入
        if self.user_input:
            user_input = self.user_input
        else:
            print("\n请输入项目路径或代码仓库地址：")
            print("  示例：")
            print("    - 本地路径: F:/projects/my-project")
            print("    - GitHub:   https://github.com/owner/repo")
            print("    - GitLab:   https://gitlab.com/owner/repo")
            print()
            user_input = input(">>> ").strip()

        # 去除引号（用户可能复制路径时带了引号）
        user_input = user_input.strip("\"'").strip()

        if not user_input:
            return {
                "current_step": "input",
                "errors": ["输入不能为空"],
            }

        # 判断是 URL 还是本地路径
        if UrlParser.is_url(user_input):
            return self._handle_url(user_input)
        else:
            return self._handle_local_path(user_input)

    def _handle_url(self, url: str) -> dict:
        """处理 URL 输入"""
        print(f"\n检测到代码仓库地址: {url}")

        # 解析 URL
        parsed = UrlParser.parse(url)
        project_name = UrlParser.get_project_name(parsed)

        print(f"  平台: {parsed['platform']}")
        print(f"  项目: {project_name}")

        return {
            "user_input": url,
            "project_url": url,
            "project_name": project_name,
            "should_download": True,
            "current_step": "input",
            "errors": [],
        }

    def _handle_local_path(self, path: str) -> dict:
        """处理本地路径输入"""
        project_path = Path(path).resolve()

        if not project_path.exists():
            return {
                "user_input": path,
                "project_path": None,
                "should_download": False,
                "current_step": "input",
                "errors": [f"路径不存在: {project_path}"],
            }

        if not project_path.is_dir():
            return {
                "user_input": path,
                "project_path": None,
                "should_download": False,
                "current_step": "input",
                "errors": [f"路径不是目录: {project_path}"],
            }

        print(f"\n检测到本地项目: {project_path}")
        project_name = project_path.name

        return {
            "user_input": path,
            "project_path": str(project_path),
            "project_name": project_name,
            "should_download": False,
            "current_step": "input",
            "errors": [],
        }