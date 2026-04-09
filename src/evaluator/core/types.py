# Core 类型定义

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime


@dataclass
class AnalysisResult:
    """分析结果"""
    success: bool
    project_name: str
    storage_dir: str
    version_id: str
    report_path: Optional[str] = None
    stats: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "project_name": self.project_name,
            "storage_dir": self.storage_dir,
            "version_id": self.version_id,
            "report_path": self.report_path,
            "stats": self.stats,
            "errors": self.errors,
            "duration_seconds": self.duration_seconds,
        }


@dataclass
class ComparisonResult:
    """对比结果"""
    success: bool
    comparison_id: str
    project_a: str
    project_b: str
    version_a: Optional[str] = None
    version_b: Optional[str] = None
    dimensions: List[Dict[str, Any]] = field(default_factory=list)
    semantic_diff: Optional[str] = None
    summary: str = ""
    recommendations: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "comparison_id": self.comparison_id,
            "project_a": self.project_a,
            "project_b": self.project_b,
            "version_a": self.version_a,
            "version_b": self.version_b,
            "dimensions": self.dimensions,
            "semantic_diff": self.semantic_diff,
            "summary": self.summary,
            "recommendations": self.recommendations,
            "duration_seconds": self.duration_seconds,
        }


@dataclass
class ProjectInfo:
    """项目信息"""
    name: str
    display_name: str
    latest_version: str
    version_count: int
    source_url: Optional[str] = None
    source_path: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "latest_version": self.latest_version,
            "version_count": self.version_count,
            "source_url": self.source_url,
            "source_path": self.source_path,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class ProjectDetail:
    """项目详情"""
    name: str
    display_name: str
    versions: List[Dict[str, Any]] = field(default_factory=list)
    source_url: Optional[str] = None
    source_path: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "versions": self.versions,
            "source_url": self.source_url,
            "source_path": self.source_path,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class AnalyzerInfo:
    """分析器信息"""
    name: str
    description: str
    enabled: bool = True
    requires_llm: bool = True

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "requires_llm": self.requires_llm,
        }
