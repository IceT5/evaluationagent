# Core 分析函数
# 统一通过 LangGraph 工作流执行

import time
from pathlib import Path
from typing import List, Optional, Dict, Any

from storage import StorageManager, ProjectMetadata, ProjectVersion
from .types import AnalysisResult


def analyze_project(
    path: str,
    types: Optional[List[str]] = None,
    display_name: Optional[str] = None,
    llm_config: Optional[Dict[str, Any]] = None,
) -> AnalysisResult:
    """分析项目 - 统一入口
    
    所有分析通过 LangGraph 工作流执行。
    
    Args:
        path: 项目路径
        types: 分析类型列表，默认 ["cicd"]
        display_name: 显示名称
        llm_config: LLM 配置
    
    Returns:
        AnalysisResult: 分析结果
    """
    start_time = time.time()
    
    types = types or ["cicd"]
    
    project_path = Path(path)
    if not project_path.exists():
        return AnalysisResult(
            success=False,
            project_name=display_name or project_path.name,
            storage_dir="",
            version_id="",
            errors=[f"路径不存在: {path}"],
        )
    
    if not project_path.is_dir():
        return AnalysisResult(
            success=False,
            project_name=display_name or project_path.name,
            storage_dir="",
            version_id="",
            errors=[f"路径不是目录: {path}"],
        )
    
    project_name = display_name or project_path.name
    
    storage = StorageManager()
    index = storage._load_project_index()
    existing_versions = []
    if project_name in index.projects:
        existing_versions = index.projects[project_name].get("versions", [])
    
    version_id = ProjectVersion.generate_version_id(existing_versions)
    version_dir = storage._create_version_dir(project_name, version_id)
    
    version_info = ProjectVersion(
        version_id=version_id,
        analyzed_at="",
        source_path=str(project_path),
        status="analyzing",
        review_status="unknown",
    )
    version_info.display_name = project_name
    storage._save_json(version_dir / "metadata.json", version_info.to_dict())
    
    if project_name not in index.projects:
        project_meta = ProjectMetadata(name=project_name)
        project_meta.display_name = project_name
        project_meta.source_path = str(project_path)
        project_meta.add_version(version_id)
        index.add_project(project_name, project_meta)
    else:
        project_meta = index.get_project(project_name)
        if project_meta:
            project_meta.add_version(version_id)
            index.projects[project_name] = project_meta.to_dict()
    
    storage._save_project_index(index)
    
    errors = []
    stats = {}
    report_path = None
    
    result = _analyze_with_graph(project_path, version_dir, project_name, llm_config)
    
    if result:
        errors.extend(result.get("errors", []))
        stats.update(result.get("stats", {}))
        if result.get("report_path"):
            report_path = result["report_path"]
        
        if result.get("success"):
            version_info.status = "completed"
            version_info.analyzed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")
            storage._save_json(version_dir / "metadata.json", version_info.to_dict())
            storage._create_latest_link(project_name, version_id)
            
            duration = time.time() - start_time
            return AnalysisResult(
                success=True,
                project_name=project_name,
                storage_dir=str(version_dir),
                version_id=version_id,
                report_path=report_path,
                stats=stats,
                errors=[],
                duration_seconds=duration,
            )
    
    version_info.status = "failed" if errors else "completed"
    version_info.analyzed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")
    storage._save_json(version_dir / "metadata.json", version_info.to_dict())
    storage._create_latest_link(project_name, version_id)
    
    duration = time.time() - start_time
    
    return AnalysisResult(
        success=len(errors) == 0,
        project_name=project_name,
        storage_dir=str(version_dir),
        version_id=version_id,
        report_path=report_path,
        stats=stats,
        errors=errors,
        duration_seconds=duration,
    )


def _analyze_with_graph(
    project_path: Path,
    version_dir: Path,
    project_name: str,
    llm_config: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """使用 LangGraph 工作流分析"""
    from evaluator.core.graphs import create_main_graph
    
    graph = create_main_graph(llm_config=llm_config, storage_dir=str(version_dir))
    
    if graph is None:
        return None
    
    initial_state = {
        "user_input": str(project_path),
        "project_path": str(project_path),
        "project_name": project_name,
        "storage_dir": str(version_dir),
        "display_name": project_name,
        "types": ["cicd"],
        "current_step": "",
        "completed_steps": [],
        "errors": [],
        "warnings": [],
        "cicd_analysis": None,
        "cicd_retry_count": 0,
        "cicd_retry_mode": None,
        "cicd_retry_issues": [],
        "cicd_existing_report": None,
        "review_result": None,
        "review_retry_count": 0,
        "report_path": None,
        "html_report_path": None,
    }
    
    result = graph.invoke(initial_state)
    
    cicd_analysis = result.get("cicd_analysis", {})
    
    if cicd_analysis.get("status") == "success":
        ci_data = _load_ci_data(cicd_analysis.get("ci_data_path", ""))
        workflows_count = cicd_analysis.get("workflows_count", 0)
        actions_count = len(ci_data.get("actions", []))
        jobs_count = sum(len(wf.get("jobs", {})) for wf in ci_data.get("workflows", {}).values())
        
        return {
            "success": True,
            "stats": {
                "workflows_count": workflows_count,
                "actions_count": actions_count,
                "jobs_count": jobs_count,
            },
            "report_path": cicd_analysis.get("report_path"),
            "html_report_path": cicd_analysis.get("html_report_path"),
            "errors": result.get("errors", []),
        }
    else:
        return {
            "success": False,
            "errors": [cicd_analysis.get("message", "分析失败")],
        }


def _load_ci_data(ci_data_path: str) -> dict:
    """加载 CI 数据"""
    if not ci_data_path or not Path(ci_data_path).exists():
        return {"workflows": {}}
    with open(ci_data_path, "r", encoding="utf-8") as f:
        import json
        return json.load(f)
