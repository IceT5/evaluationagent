"""Loader Agent - 下载远程项目"""
from pathlib import Path
from evaluator.skills import GitOperations, UrlParser


class LoaderAgent:
    """项目加载 Agent"""

    # 默认下载目录
    DEFAULT_DOWNLOAD_DIR = "./downloaded_projects"

    def __init__(self, download_dir: str | None = None):
        """
        Args:
            download_dir: 下载目录，默认为 ./downloaded_projects
        """
        self.download_dir = download_dir or self.DEFAULT_DOWNLOAD_DIR

    def run(self, state: dict) -> dict:
        """
        职责：
        1. 如果需要下载，执行 git clone
        2. 处理下载结果
        3. 更新状态

        Returns:
            更新后的状态片段
        """
        # 检查是否需要下载
        if not state.get("should_download", False):
            print("\n跳过下载，使用本地项目")
            return {
                "current_step": "loader",
                "clone_status": "skipped",
                "errors": [],
            }

        project_url = state.get("project_url")
        project_name = state.get("project_name", "unknown-project")

        if not project_url:
            return {
                "current_step": "loader",
                "clone_status": "failed",
                "clone_error": "未提供项目 URL",
                "errors": ["未提供项目 URL"],
            }

        # 准备下载目录
        download_path = Path(self.download_dir) / project_name

        print(f"\n准备下载项目到: {download_path}")

        # 执行克隆
        result = GitOperations.clone(project_url, str(download_path))

        if result["success"]:
            print(f"\n✅ 项目下载成功!")
            print(f"   路径: {result['path']}")

            return {
                "project_path": result["path"],
                "clone_status": "success",
                "clone_error": None,
                "current_step": "loader",
                "errors": [],
            }
        else:
            error_msg = result.get("error", "未知错误")
            print(f"\n❌ 项目下载失败: {error_msg}")

            return {
                "project_path": None,
                "clone_status": "failed",
                "clone_error": error_msg,
                "current_step": "loader",
                "errors": [f"克隆失败: {error_msg}"],
            }