"""Loader Agent - 下载远程项目"""
from pathlib import Path
from evaluator.skills import GitOperations, UrlParser
from storage import StorageManager, ProjectMetadata


class LoaderAgent:
    """项目加载 Agent"""

    DEFAULT_DOWNLOAD_DIR = "./downloaded_projects"

    def __init__(self, download_dir: str | None = None, storage_manager: StorageManager | None = None):
        self.download_dir = download_dir or self.DEFAULT_DOWNLOAD_DIR
        self.storage = storage_manager or StorageManager()

    def _init_storage(self, project_name: str, project_url: str | None = None, project_path: str | None = None) -> dict:
        """初始化存储，创建版本目录"""
        display_name = self.storage._sanitize_name(project_name) if project_name else "unknown"

        index = self.storage._load_project_index()
        existing_versions = []
        if display_name in index.projects:
            existing_versions = index.projects[display_name].get("versions", [])

        from storage.models import ProjectVersion
        version_id = ProjectVersion.generate_version_id(existing_versions)

        metadata = {
            "name": display_name,
            "display_name": display_name,
            "source_url": project_url,
            "source_path": project_path,
            "status": "analyzing",
        }

        version_dir = self.storage._create_version_dir(display_name, version_id)

        version_info = ProjectVersion(
            version_id=version_id,
            analyzed_at="",
            source_url=project_url,
            source_path=project_path,
            status="analyzing",
            review_status="unknown",
        )

        version_info.display_name = display_name
        self.storage._save_json(version_dir / "metadata.json", version_info.to_dict())

        if display_name not in index.projects:
            project_meta = ProjectMetadata(name=display_name)
            project_meta.source_url = project_url
            project_meta.source_path = project_path
            project_meta.add_version(version_id)
            index.add_project(display_name, project_meta)
        else:
            project_meta = index.get_project(display_name)
            if project_meta:
                project_meta.add_version(version_id)
                if project_url:
                    project_meta.source_url = project_url
                if project_path:
                    project_meta.source_path = project_path
                index.projects[display_name] = project_meta.to_dict()

        self.storage._save_project_index(index)

        return {
            "storage_version_id": version_id,
            "storage_dir": str(version_dir),
        }

    def run(self, state: dict) -> dict:
        project_url = state.get("project_url")
        project_name = state.get("project_name", "unknown-project")
        project_path = state.get("project_path")

        storage_info = self._init_storage(project_name, project_url, project_path)

        if not state.get("should_download", False):
            print("\n跳过下载，使用本地项目")
            return {
                "current_step": "loader",
                "clone_status": "skipped",
                "errors": [],
                **storage_info,
            }

        if not project_url:
            return {
                "current_step": "loader",
                "clone_status": "failed",
                "clone_error": "未提供项目 URL",
                "errors": ["未提供项目 URL"],
                **storage_info,
            }

        download_path = Path(self.download_dir) / project_name
        print(f"\n准备下载项目到: {download_path}")

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
                **storage_info,
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
                **storage_info,
            }