# 存储管理器 - 项目数据持久化

import os
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv

from .models import (
    ProjectMetadata,
    ProjectVersion,
    ProjectIndex,
    ComparisonMetadata,
    ComparisonIndex,
)


class StorageManager:
    DEFAULT_DATA_DIR = "data"
    PROJECTS_DIR = "projects"
    COMPARISONS_DIR = "comparisons"
    INDEX_FILE = "index.json"

    def __init__(self, data_dir: Optional[str] = None):
        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            load_dotenv()
            env_data_dir = os.getenv("EVAL_DATA_DIR")
            if env_data_dir:
                self.data_dir = Path(env_data_dir)
            else:
                # 2. 用户目录
                if os.name == 'nt':  # Windows
                    app_data = os.getenv('APPDATA') or os.getenv('LOCALAPPDATA')
                    if app_data:
                        self.data_dir = Path(app_data) / "eval-agent" / "data"
                    else:
                        self.data_dir = Path.home() / ".eval-agent" / "data"
                else:  # Linux/Mac
                    self.data_dir = Path.home() / ".eval-agent" / "data"
                
                # 3. 开发环境（仅在用户目录不存在时）
                if not self.data_dir.exists():
                    project_root = Path(__file__).parent.parent.parent
                    dist_data = project_root / "dist" / "eval-agent" / "data"
                    if dist_data.exists():
                        self.data_dir = dist_data
                    else:
                        # 4. 项目根目录
                        self.data_dir = project_root / self.DEFAULT_DATA_DIR

        self.projects_dir = self.data_dir / self.PROJECTS_DIR
        self.comparisons_dir = self.data_dir / self.COMPARISONS_DIR
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.comparisons_dir.mkdir(parents=True, exist_ok=True)

    def _get_project_dir(self, project_name: str) -> Path:
        safe_name = self._sanitize_name(project_name)
        return self.projects_dir / safe_name

    def _get_version_dir(self, project_name: str, version_id: Optional[str] = None) -> Path:
        project_dir = self._get_project_dir(project_name)
        if version_id is None:
            latest_link = project_dir / "latest"
            if latest_link.is_symlink():
                return latest_link.resolve()
            versions = self._list_versions(project_name)
            if not versions:
                raise ValueError(f"No versions found for project: {project_name}")
            version_id = versions[-1]
        return project_dir / version_id

    def _get_comparison_dir(self, comparison_id: str) -> Path:
        safe_name = self._sanitize_name(comparison_id)
        return self.comparisons_dir / safe_name

    @staticmethod
    def _sanitize_name(name: str) -> str:
        return "".join(c if c.isalnum() or c in "._-" else "_" for c in name)

    def _load_index(self, dir_path: Path) -> dict:
        index_file = dir_path / self.INDEX_FILE
        if index_file.exists():
            with open(index_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_index(self, dir_path: Path, index: dict) -> None:
        index_file = dir_path / self.INDEX_FILE
        with open(index_file, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)

    def _load_project_index(self) -> ProjectIndex:
        index_data = self._load_index(self.projects_dir)
        if not index_data:
            return ProjectIndex()
        return ProjectIndex.from_dict(index_data)

    def _save_project_index(self, index: ProjectIndex) -> None:
        self._save_index(self.projects_dir, index.to_dict())

    def _load_comparison_index(self) -> ComparisonIndex:
        index_data = self._load_index(self.comparisons_dir)
        if not index_data:
            return ComparisonIndex()
        return ComparisonIndex.from_dict(index_data)

    def _save_comparison_index(self, index: ComparisonIndex) -> None:
        self._save_index(self.comparisons_dir, index.to_dict())

    # ========== Project Operations ==========

    def list_projects(self) -> list[str]:
        index = self._load_project_index()
        return list(index.projects.keys())

    def project_exists(self, name: str) -> bool:
        index = self._load_project_index()
        return name in index.projects

    def get_project_metadata(self, name: str) -> Optional[ProjectMetadata]:
        index = self._load_project_index()
        return index.get_project(name)
    
    def get_latest_version_dir(self, project_name: str) -> Optional[Path]:
        """获取项目的最新版本目录
        
        Returns:
            Path 或 None（如果项目不存在）
        """
        return self.get_version_dir(project_name, None)
    
    def get_version_dir(self, project_name: str, version: Optional[str] = None) -> Optional[Path]:
        """获取项目的指定版本目录
        
        Args:
            project_name: 项目名称
            version: 版本号，None 表示最新版本
        
        Returns:
            Path 或 None（如果项目不存在或版本不存在）
        """
        if not self.project_exists(project_name):
            return None
        try:
            return self._get_version_dir(project_name, version)
        except ValueError:
            return None
    
    def _list_versions(self, project_name: str) -> list[str]:
        project_dir = self._get_project_dir(project_name)
        if not project_dir.exists():
            return []
        versions = [
            d.name for d in project_dir.iterdir()
            if d.is_dir() and d.name.startswith("v") and d.name != "latest"
        ]
        versions.sort()
        return versions

    def list_versions(self, project_name: str) -> list[str]:
        index = self._load_project_index()
        metadata = index.get_project(project_name)
        if metadata:
            return metadata.versions
        return self._list_versions(project_name)

    def _create_version_dir(self, project_name: str, version_id: str) -> Path:
        project_dir = self._get_project_dir(project_name)
        project_dir.mkdir(parents=True, exist_ok=True)
        version_dir = project_dir / version_id
        version_dir.mkdir(exist_ok=True)
        return version_dir

    def _create_latest_link(self, project_name: str, version_id: str) -> None:
        project_dir = self._get_project_dir(project_name)
        latest_link = project_dir / "latest"
        old_link = project_dir / "old_latest"
        if latest_link.is_symlink() or latest_link.exists():
            if latest_link.is_symlink():
                latest_link.unlink()
            else:
                import shutil
                if old_link.exists():
                    shutil.rmtree(old_link)
                latest_link.rename(old_link)
        try:
            latest_link.symlink_to(version_id, target_is_directory=True)
        except OSError:
            import sys
            if sys.platform == "win32":
                import shutil
                if latest_link.exists():
                    shutil.rmtree(latest_link)
                shutil.copytree(project_dir / version_id, latest_link)
            else:
                raise

    def save_project(
        self,
        project_name: str,
        ci_data: dict,
        report_md: str,
        report_html: str,
        architecture_json: Optional[dict] = None,
        metadata: Optional[dict] = None,
        display_name: Optional[str] = None,
    ) -> str:
        index = self._load_project_index()
        project_dir = self._get_project_dir(project_name)

        if project_name in index.projects:
            existing_versions = index.projects[project_name].get("versions", [])
        else:
            existing_versions = []
            index.add_project(project_name, ProjectMetadata(name=project_name))

        version_id = ProjectVersion.generate_version_id(existing_versions)
        version_dir = self._create_version_dir(project_name, version_id)

        version_info = ProjectVersion(
            version_id=version_id,
            analyzed_at=datetime.now().isoformat(),
            source_url=metadata.get("source_url") if metadata else None,
            source_path=metadata.get("source_path") if metadata else None,
            branch=metadata.get("branch") if metadata else None,
            commit=metadata.get("commit") if metadata else None,
            status=metadata.get("status", "completed") if metadata else "completed",
            review_status=metadata.get("review_status", "passed") if metadata else "passed",
        )

        project_meta = index.get_project(project_name)
        if project_meta:
            project_meta.add_version(version_id)
            if display_name:
                project_meta.display_name = display_name
            if metadata:
                if metadata.get("source_url"):
                    project_meta.source_url = metadata["source_url"]
                if metadata.get("source_path"):
                    project_meta.source_path = metadata["source_path"]
            index.projects[project_name] = project_meta.to_dict()

        metadata_json = version_info.to_dict()
        metadata_json["display_name"] = display_name or project_name

        self._save_json(version_dir / "metadata.json", metadata_json)
        self._save_json(version_dir / "ci_data.json", ci_data)
        self._save_text(version_dir / "report.md", report_md)
        self._save_text(version_dir / "report.html", report_html)
        if architecture_json:
            self._save_json(version_dir / "architecture.json", architecture_json)

        self._save_project_index(index)
        self._create_latest_link(project_name, version_id)

        return version_id

    def load_project(
        self,
        project_name: str,
        version_id: Optional[str] = None,
    ) -> Optional[dict]:
        try:
            version_dir = self._get_version_dir(project_name, version_id)
        except ValueError:
            return None

        if not version_dir.exists():
            return None

        return {
            "metadata": self._load_json(version_dir / "metadata.json") or {},
            "ci_data": self._load_json(version_dir / "ci_data.json") or {},
            "report_md": self._load_text(version_dir / "report.md") or "",
            "report_html": self._load_text(version_dir / "report.html") or "",
            "architecture_json": self._load_json(version_dir / "architecture.json") or {},
        }

    def delete_project(self, project_name: str, version_id: Optional[str] = None) -> bool:
        index = self._load_project_index()
        project_dir = self._get_project_dir(project_name)

        if version_id:
            version_dir = project_dir / version_id
            if version_dir.exists():
                shutil.rmtree(version_dir)
                if project_name in index.projects:
                    versions = index.projects[project_name].get("versions", [])
                    if version_id in versions:
                        versions.remove(version_id)
                        index.projects[project_name]["versions"] = versions
                        if index.projects[project_name].get("latest_version") == version_id:
                            if versions:
                                index.projects[project_name]["latest_version"] = versions[-1]
                                self._create_latest_link(project_name, versions[-1])
                            else:
                                del index.projects[project_name]
                                latest_link = project_dir / "latest"
                                if latest_link.is_symlink():
                                    latest_link.unlink()
                        self._save_project_index(index)
                return True
        else:
            if project_dir.exists():
                shutil.rmtree(project_dir)
                index.remove_project(project_name)
                self._save_project_index(index)
                return True
        return False

    # ========== Comparison Operations ==========

    def list_comparisons(self) -> list[dict]:
        index = self._load_comparison_index()
        return [
            {
                "comparison_id": c.get("comparison_id"),
                "project_a": c.get("project_a"),
                "project_b": c.get("project_b"),
                "created_at": c.get("created_at"),
            }
            for c in index.comparisons
        ]

    def save_comparison(
        self,
        project_a: str,
        project_b: str,
        version_a: Optional[str],
        version_b: Optional[str],
        compare_md: str,
        compare_html: str,
        dimensions: list[str],
    ) -> str:
        index = self._load_comparison_index()
        existing_ids = [c.get("comparison_id") for c in index.comparisons]

        comparison_id = ComparisonMetadata.generate_comparison_id(project_a, project_b, existing_ids)

        metadata = ComparisonMetadata(
            comparison_id=comparison_id,
            project_a=project_a,
            project_b=project_b,
            version_a=version_a,
            version_b=version_b,
            dimensions=dimensions,
        )

        comp_dir = self._get_comparison_dir(comparison_id)
        comp_dir.mkdir(parents=True, exist_ok=True)

        self._save_json(comp_dir / "metadata.json", metadata.to_dict())
        self._save_text(comp_dir / "compare.md", compare_md)
        self._save_text(comp_dir / "compare.html", compare_html)

        index.add_comparison(metadata)
        self._save_comparison_index(index)

        return comparison_id

    def load_comparison(self, comparison_id: str) -> Optional[dict]:
        comp_dir = self._get_comparison_dir(comparison_id)
        if not comp_dir.exists():
            return None

        return {
            "metadata": self._load_json(comp_dir / "metadata.json"),
            "compare_md": self._load_text(comp_dir / "compare.md"),
            "compare_html": self._load_text(comp_dir / "compare.html"),
        }

    def delete_comparison(self, comparison_id: str) -> bool:
        index = self._load_comparison_index()
        comp_dir = self._get_comparison_dir(comparison_id)

        if comp_dir.exists():
            shutil.rmtree(comp_dir)
            index.remove_comparison(comparison_id)
            self._save_comparison_index(index)
            return True
        return False

    # ========== File Operations ==========

    def _load_json(self, file_path: Path) -> Optional[dict]:
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def _save_json(self, file_path: Path, data: dict) -> None:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _load_text(self, file_path: Path) -> Optional[str]:
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        return None

    def _save_text(self, file_path: Path, content: str) -> None:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

    # ========== Utility Methods ==========

    def get_storage_info(self) -> dict:
        projects = self.list_projects()
        comparisons = self.list_comparisons()

        total_size = 0
        for project_name in projects:
            try:
                for version in self.list_versions(project_name):
                    version_dir = self._get_version_dir(project_name, version)
                    total_size += self._dir_size(version_dir)
            except Exception:
                pass

        return {
            "data_dir": str(self.data_dir),
            "project_count": len(projects),
            "comparison_count": len(comparisons),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
        }

    @staticmethod
    def _dir_size(path: Path) -> int:
        total = 0
        for item in path.rglob("*"):
            if item.is_file():
                total += item.stat().st_size
        return total
