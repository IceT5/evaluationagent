# Core 分析函数

import os
import time
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from storage import StorageManager, ProjectMetadata, ProjectVersion
from .types import AnalysisResult, AnalyzerInfo


@dataclass
class AnalyzeConfig:
    """分析配置"""
    path: str
    types: List[str]
    display_name: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_model: Optional[str] = None


def analyze_project(
    path: str,
    types: Optional[List[str]] = None,
    display_name: Optional[str] = None,
    llm_config: Optional[Dict[str, Any]] = None,
) -> AnalysisResult:
    """
    分析项目
    
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
    
    # 验证路径
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
    
    # 初始化存储
    storage = StorageManager()
    index = storage._load_project_index()
    existing_versions = []
    if project_name in index.projects:
        existing_versions = index.projects[project_name].get("versions", [])
    
    version_id = ProjectVersion.generate_version_id(existing_versions)
    version_dir = storage._create_version_dir(project_name, version_id)
    
    # 创建版本元数据
    version_info = ProjectVersion(
        version_id=version_id,
        analyzed_at="",
        source_path=str(project_path),
        status="analyzing",
        review_status="unknown",
    )
    version_info.display_name = project_name
    storage._save_json(version_dir / "metadata.json", version_info.to_dict())
    
    # 更新项目索引
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
    
    # 执行分析
    errors = []
    stats = {}
    report_path = None
    
    for analyzer_type in types:
        if analyzer_type == "cicd":
            result = _analyze_cicd(project_path, version_dir, llm_config)
            if not result["success"]:
                errors.extend(result.get("errors", []))
            stats.update(result.get("stats", {}))
            if result.get("report_path"):
                report_path = result["report_path"]
    
    # 更新版本元数据
    version_info.status = "completed" if not errors else "failed"
    version_info.analyzed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")
    version_info.workflows_count = stats.get("workflows_count", 0)
    version_info.jobs_count = stats.get("jobs_count", 0)
    storage._save_json(version_dir / "metadata.json", version_info.to_dict())
    
    # 更新 latest 链接
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


def _analyze_cicd(
    project_path: Path,
    version_dir: Path,
    llm_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """执行 CI/CD 分析"""
    from evaluator.agents import CICDAgent, ReporterAgent, ReviewerAgent
    from evaluator.llm import LLMClient
    from storage import StorageManager
    
    try:
        # 初始化 LLM 客户端
        llm = None
        if llm_config:
            api_key = llm_config.get("api_key")
            if api_key:
                kwargs = {"api_key": api_key}
                if llm_config.get("base_url"):
                    kwargs["base_url"] = llm_config["base_url"]
                if llm_config.get("model"):
                    kwargs["model"] = llm_config["model"]
                llm = LLMClient(**kwargs)
        
        # 使用 CICDAgent 执行分析
        cicd_agent = CICDAgent(llm=llm)
        
        state = {
            "project_path": str(project_path),
            "project_name": project_path.name,
            "storage_dir": str(version_dir),
        }
        
        cicd_result = cicd_agent.run(state)
        
        if not cicd_result.get("cicd_analysis", {}).get("status") == "success":
            return {
                "success": False,
                "errors": cicd_result.get("errors", ["CI/CD 分析失败"]),
            }
        
        cicd_analysis = cicd_result["cicd_analysis"]
        workflows_count = cicd_analysis.get("workflows_count", 0)
        actions_count = cicd_analysis.get("actions_count", 0)
        jobs_count = sum(
            len(wf.get("jobs", {})) 
            for wf in _load_ci_data(cicd_analysis.get("ci_data_path", "")).get("workflows", {}).values()
        )
        
        # 使用 ReviewerAgent 验证报告
        print("\n正在验证报告准确性...")
        reviewer_agent = ReviewerAgent(llm=llm)
        
        reviewer_state = {
            "project_name": project_path.name,
            "storage_dir": str(version_dir),
            "cicd_analysis": cicd_analysis,
            "review_retry_count": 0,
        }
        
        reviewer_result = reviewer_agent.run(reviewer_state)
        review_status = reviewer_result.get("review_result", {}).get("status", "unknown")
        
        if review_status in ["passed", "corrected"]:
            print("  ✓ 报告验证通过")
            if reviewer_result.get("corrected_report"):
                corrected_path = version_dir / "CI_ARCHITECTURE.md"
                corrected_path.write_text(reviewer_result["corrected_report"], encoding="utf-8")
                cicd_analysis["report_path"] = str(corrected_path)
        elif review_status in ["critical", "incomplete"]:
            print(f"  ⚠ 报告存在问题: {review_status}，继续生成报告")
        
        # 使用 ReporterAgent 生成 HTML 报告
        print("\n正在生成交互式 HTML 报告...")
        storage = StorageManager()
        reporter_agent = ReporterAgent(storage_manager=storage)
        
        reporter_state = {
            "project_name": project_path.name,
            "project_path": str(project_path),
            "storage_dir": str(version_dir),
            "cicd_analysis": cicd_analysis,
        }
        
        reporter_result = reporter_agent.run(reporter_state)
        html_report_path = reporter_result.get("report_path")
        
        if html_report_path:
            print(f"  HTML 报告已保存: {html_report_path}")
        
        # 验证最终报告
        print("\n正在验证最终报告...")
        try:
            from evaluator.agents import ReviewerAgent
            reviewer = ReviewerAgent(llm=llm)
            md_report_path = cicd_analysis.get("report_path", "")
            validation = reviewer.validate_final_reports(md_report_path, html_report_path or "", _load_ci_data(cicd_analysis.get("ci_data_path", "")))
            
            if not validation["valid"]:
                print("  [WARN] 最终报告验证发现问题:")
                if validation.get("md_issues"):
                    for issue in validation["md_issues"]:
                        print(f"    - Markdown: {issue}")
                if validation.get("html_issues"):
                    for issue in validation["html_issues"]:
                        print(f"    - HTML: {issue}")
            else:
                print("  [OK] 最终报告验证通过")
        except Exception as e:
            print(f"  [WARN] 最终报告验证失败: {e}")
        
        return {
            "success": True,
            "stats": {
                "workflows_count": workflows_count,
                "actions_count": actions_count,
                "jobs_count": jobs_count,
            },
            "report_path": cicd_analysis.get("report_path"),
            "html_report_path": html_report_path,
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "errors": [f"CI/CD 分析失败: {str(e)}"],
        }


def _load_ci_data(ci_data_path: str) -> dict:
    """加载 CI 数据"""
    if not ci_data_path or not Path(ci_data_path).exists():
        return {"workflows": {}}
    with open(ci_data_path, "r", encoding="utf-8") as f:
        return json.load(f)
