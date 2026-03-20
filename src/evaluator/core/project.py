# Core 项目管理函数

from pathlib import Path
from typing import List, Optional, Dict, Any

from storage import StorageManager
from .types import ProjectInfo, ProjectDetail, AnalyzerInfo, AnalysisResult


_storage: Optional[StorageManager] = None


def _get_storage() -> StorageManager:
    global _storage
    if _storage is None:
        _storage = StorageManager()
    return _storage


def list_projects() -> List[ProjectInfo]:
    """列出所有已保存的项目"""
    storage = _get_storage()
    projects = storage.list_projects()
    
    result = []
    for name in projects:
        versions = storage.list_versions(name)
        metadata = storage.get_project_metadata(name)
        
        result.append(ProjectInfo(
            name=name,
            display_name=metadata.display_name if metadata else name,
            latest_version=versions[-1] if versions else "",
            version_count=len(versions),
            source_url=metadata.source_url if metadata else None,
            source_path=metadata.source_path if metadata else None,
            created_at=metadata.created_at if metadata else None,
            updated_at=metadata.updated_at if metadata else None,
        ))
    
    return result


def get_project(name: str, version: str = None) -> Optional[ProjectDetail]:
    """获取项目详情"""
    storage = _get_storage()
    
    if not storage.project_exists(name):
        return None
    
    metadata = storage.get_project_metadata(name)
    if not metadata:
        return None
    
    versions = storage.list_versions(name)
    version_details = []
    
    for v in versions:
        data = storage.load_project(name, v)
        if data:
            meta = data.get("metadata", {})
            version_details.append({
                "version_id": v,
                "analyzed_at": meta.get("analyzed_at", ""),
                "workflows": meta.get("workflows_count", 0),
                "jobs": meta.get("jobs_count", 0),
            })
    
    return ProjectDetail(
        name=name,
        display_name=metadata.display_name or name,
        versions=version_details,
        source_url=metadata.source_url,
        source_path=metadata.source_path,
        created_at=metadata.created_at,
        updated_at=metadata.updated_at,
    )


def delete_project(name: str, version: str = None) -> bool:
    """删除项目或指定版本"""
    storage = _get_storage()
    return storage.delete_project(name, version)


def list_analyzers() -> List[AnalyzerInfo]:
    """列出可用的分析器"""
    return [
        AnalyzerInfo(
            name="cicd",
            description="CI/CD 架构分析",
            enabled=True,
            requires_llm=True,
        ),
        AnalyzerInfo(
            name="quality",
            description="代码质量分析（规划中）",
            enabled=False,
            requires_llm=True,
        ),
        AnalyzerInfo(
            name="security",
            description="安全漏洞分析（规划中）",
            enabled=False,
            requires_llm=True,
        ),
    ]


def get_storage_info() -> Dict[str, Any]:
    """获取存储信息"""
    storage = _get_storage()
    return storage.get_storage_info()


def get_report(project_name: str, version: str = None) -> Optional[Dict[str, Any]]:
    """获取项目报告"""
    storage = _get_storage()
    data = storage.load_project(project_name, version)
    
    if not data:
        return None
    
    return {
        "metadata": data.get("metadata", {}),
        "report_html": data.get("report_html"),
        "report_md": data.get("report_md"),
        "ci_data": data.get("ci_data"),
        "architecture_json": data.get("architecture_json"),
    }
