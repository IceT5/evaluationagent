"""Loader Agent - 下载远程项目"""
from pathlib import Path
from typing import Any, Dict
from evaluator.skills import GitOperations
from storage import StorageManager, ProjectMetadata
from .base_agent import BaseAgent, AgentMeta


class LoaderAgent(BaseAgent):
    """项目加载 Agent"""

    DEFAULT_DOWNLOAD_DIR = "./downloaded_projects"

    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="LoaderAgent",
            description="下载/克隆远程项目，初始化存储目录",
            category="entry",
            inputs=["project_name", "project_url", "project_path", "should_download"],
            outputs=["project_path", "clone_status", "storage_version_id", "storage_dir"],
            dependencies=["InputAgent"],
        )

    def __init__(self, download_dir: str | None = None, storage_manager: StorageManager | None = None):
        super().__init__()
        self.download_dir = download_dir or self.DEFAULT_DOWNLOAD_DIR
        self.storage = storage_manager or StorageManager()

    def _init_storage(self, project_name: str, project_url: str | None = None, project_path: str | None = None) -> dict:
        display_name = self.storage._sanitize_name(project_name) if project_name else "unknown"

        index = self.storage._load_project_index()
        existing_versions = []
        if display_name in index.projects:
            existing_versions = index.projects[display_name].get("versions", [])

        from storage.models import ProjectVersion
        version_id = ProjectVersion.generate_version_id(existing_versions)

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
            "display_name": display_name,
        }

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        project_url = state.get("project_url")
        project_name = state.get("project_name", "unknown-project")
        project_path = state.get("project_path")
        errors = state.get("errors", [])

        storage_info = self._init_storage(project_name, project_url, project_path)

        if not state.get("should_download", False):
            return {
                **state,
                "current_step": "loader",
                "clone_status": "skipped",
                **storage_info,
            }

        if not project_url:
            return {
                **state,
                "current_step": "loader",
                "clone_status": "failed",
                "clone_error": "未提供项目 URL",
                "errors": errors + ["未提供项目 URL"],
                **storage_info,
            }

        download_path = Path(self.download_dir) / project_name

        result = GitOperations.clone(project_url, str(download_path))

        if result["success"]:
            return {
                **state,
                "project_path": result["path"],
                "clone_status": "success",
                "clone_error": None,
                "current_step": "loader",
                **storage_info,
            }
        else:
            error_msg = result.get("error", "未知错误")
            return {
                **state,
                "project_path": None,
                "clone_status": "failed",
                "clone_error": error_msg,
                "current_step": "loader",
                "errors": errors + [f"克隆失败: {error_msg}"],
                **storage_info,
            }