# 数据模型 - 持久化存储

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional
import json
import re


@dataclass
class ProjectVersion:
    version_id: str
    analyzed_at: str
    source_url: Optional[str] = None
    source_path: Optional[str] = None
    branch: Optional[str] = None
    commit: Optional[str] = None
    status: str = "completed"
    review_status: str = "passed"
    display_name: Optional[str] = None

    @staticmethod
    def generate_version_id(existing_versions: list[str]) -> str:
        max_version = 0
        for v in existing_versions:
            match = re.match(r'v(\d+)_', v)
            if match:
                max_version = max(max_version, int(match.group(1)))
        
        version_num = max_version + 1
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"v{version_num}_{timestamp}"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectVersion":
        return cls(**data)


@dataclass
class ProjectMetadata:
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    latest_version: Optional[str] = None
    versions: list[str] = field(default_factory=list)
    source_url: Optional[str] = None
    source_path: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def add_version(self, version_id: str) -> None:
        if version_id not in self.versions:
            self.versions.append(version_id)
        self.latest_version = version_id
        self.updated_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectMetadata":
        return cls(**data)


@dataclass
class ProjectIndex:
    projects: dict[str, dict] = field(default_factory=dict)
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())

    def add_project(self, name: str, metadata: ProjectMetadata) -> None:
        self.projects[name] = metadata.to_dict()
        self.last_updated = datetime.now().isoformat()

    def get_project(self, name: str) -> Optional[ProjectMetadata]:
        if name not in self.projects:
            return None
        return ProjectMetadata.from_dict(self.projects[name])

    def remove_project(self, name: str) -> bool:
        if name in self.projects:
            del self.projects[name]
            self.last_updated = datetime.now().isoformat()
            return True
        return False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectIndex":
        return cls(**data)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "ProjectIndex":
        return cls.from_dict(json.loads(json_str))


@dataclass
class ComparisonMetadata:
    comparison_id: str
    project_a: str
    project_b: str
    version_a: Optional[str] = None
    version_b: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    dimensions: list[str] = field(default_factory=list)

    @staticmethod
    def generate_comparison_id(project_a: str, project_b: str, existing_ids: list[str]) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = f"{project_a}_vs_{project_b}_{timestamp}"
        return base_name

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ComparisonMetadata":
        return cls(**data)


@dataclass
class ComparisonIndex:
    comparisons: list[dict] = field(default_factory=list)
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())

    def add_comparison(self, metadata: ComparisonMetadata) -> None:
        self.comparisons.append(metadata.to_dict())
        self.last_updated = datetime.now().isoformat()

    def get_comparison(self, comparison_id: str) -> Optional[ComparisonMetadata]:
        for comp in self.comparisons:
            if comp.get("comparison_id") == comparison_id:
                return ComparisonMetadata.from_dict(comp)
        return None

    def remove_comparison(self, comparison_id: str) -> bool:
        self.comparisons = [c for c in self.comparisons if c.get("comparison_id") != comparison_id]
        self.last_updated = datetime.now().isoformat()
        return True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ComparisonIndex":
        return cls(**data)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "ComparisonIndex":
        return cls.from_dict(json.loads(json_str))
