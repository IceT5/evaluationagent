# CI/CD 架构对比维度定义

from dataclasses import dataclass
from typing import Optional


COMPARE_DIMENSIONS = {
    "complexity": {
        "name": "架构复杂度",
        "metrics": {
            "workflow_count": {"name": "工作流数量", "unit": "个", "higher_is_better": False},
            "job_count": {"name": "Job 总数", "unit": "个", "higher_is_better": False},
            "avg_jobs_per_workflow": {"name": "平均 Job/工作流", "unit": "个", "higher_is_better": True},
            "dependency_depth": {"name": "依赖深度", "unit": "层", "higher_is_better": False},
            "matrix_usage": {"name": "矩阵构建使用率", "unit": "%", "higher_is_better": True},
            "conditional_steps": {"name": "条件步骤使用", "unit": "个", "higher_is_better": True},
        },
    },
    "best_practices": {
        "name": "最佳实践",
        "metrics": {
            "cache_usage": {"name": "缓存使用率", "unit": "%", "higher_is_better": True},
            "security_scan": {"name": "安全扫描覆盖", "unit": "%", "higher_is_better": True},
            "artifact_reuse": {"name": "Artifact 复用率", "unit": "%", "higher_is_better": True},
            "secret_management": {"name": "密钥管理", "unit": "", "higher_is_better": True},
            "timeout_configured": {"name": "超时配置完整性", "unit": "%", "higher_is_better": True},
            "fail_fast": {"name": "失败快速停止", "unit": "%", "higher_is_better": True},
        },
    },
    "maintainability": {
        "name": "可维护性",
        "metrics": {
            "action_reuse": {"name": "Action 复用率", "unit": "%", "higher_is_better": True},
            "custom_action_ratio": {"name": "自定义 Action 比例", "unit": "%", "higher_is_better": False},
            "script_reuse": {"name": "脚本复用率", "unit": "%", "higher_is_better": True},
            "workflow_call_usage": {"name": "工作流调用使用", "unit": "", "higher_is_better": True},
            "doc_coverage": {"name": "文档覆盖率", "unit": "%", "higher_is_better": True},
            "naming_consistency": {"name": "命名一致性", "unit": "", "higher_is_better": True},
        },
    },
}


@dataclass
class MetricResult:
    name: str
    value_a: Optional[float]
    value_b: Optional[float]
    unit: str
    higher_is_better: bool
    
    @property
    def winner(self) -> str:
        if self.value_a is None or self.value_b is None:
            return "N/A"
        if self.value_a == self.value_b:
            return "tie"
        if self.higher_is_better:
            return "A" if self.value_a > self.value_b else "B"
        else:
            return "A" if self.value_a < self.value_b else "B"
    
    @property
    def difference(self) -> Optional[float]:
        if self.value_a is None or self.value_b is None:
            return None
        return self.value_b - self.value_a


@dataclass
class DimensionResult:
    name: str
    metrics: list[MetricResult]
    score_a: float
    score_b: float
    
    @property
    def winner(self) -> str:
        if self.score_a > self.score_b:
            return "A"
        elif self.score_b > self.score_a:
            return "B"
        return "tie"


@dataclass
class ComparisonResult:
    project_a: str
    project_b: str
    dimensions: list[DimensionResult]
    summary: str
    recommendations: list[str]


class DimensionCalculator:
    @staticmethod
    def calculate_complexity(ci_data: dict) -> dict:
        workflows = ci_data.get("workflows", {})
        job_count = 0
        matrix_count = 0
        conditional_count = 0
        max_depth = 0
        total_dependencies = 0
        
        for wf_name, wf in workflows.items():
            jobs = wf.get("jobs", {})
            job_count += len(jobs)
            
            for job_name, job in jobs.items():
                job_data = job if isinstance(job, dict) else {}
                
                if job_data.get("strategy", {}).get("matrix"):
                    matrix_count += 1
                
                if job_data.get("if"):
                    conditional_count += 1
                
                needs = job_data.get("needs", [])
                if isinstance(needs, list):
                    total_dependencies += len(needs)
                    max_depth = max(max_depth, len(needs))
        
        workflow_count = len(workflows)
        avg_jobs = job_count / workflow_count if workflow_count > 0 else 0
        matrix_usage = (matrix_count / job_count * 100) if job_count > 0 else 0
        
        return {
            "workflow_count": workflow_count,
            "job_count": job_count,
            "avg_jobs_per_workflow": round(avg_jobs, 1),
            "dependency_depth": max_depth,
            "matrix_usage": round(matrix_usage, 1),
            "conditional_steps": conditional_count,
        }
    
    @staticmethod
    def calculate_best_practices(ci_data: dict) -> dict:
        workflows = ci_data.get("workflows", {})
        job_count = 0
        cache_count = 0
        security_count = 0
        artifact_count = 0
        secret_count = 0
        timeout_count = 0
        fail_fast_count = 0
        
        actions = ci_data.get("actions", [])
        action_names = {a.get("name", "").lower() for a in actions}
        
        for wf_name, wf in workflows.items():
            jobs = wf.get("jobs", {})
            
            for job_name, job in jobs.items():
                job_count += 1
                job_data = job if isinstance(job, dict) else {}
                steps = job_data.get("steps", [])
                
                if any("cache" in str(s).lower() for s in steps):
                    cache_count += 1
                
                security_actions = ["snyk", "trivy", "anchore", "aqua", "spectral", "checkov", "trufflehog", "secret"]
                if any(any(sec in str(s).lower() for sec in security_actions) for s in steps):
                    security_count += 1
                
                if any("artifact" in str(s).lower() or "upload" in str(s).lower() for s in steps):
                    artifact_count += 1
                
                env = job_data.get("env", {})
                if env and any("secret" in str(k).lower() or "token" in str(k).lower() for k in env.keys()):
                    secret_count += 1
                
                if job_data.get("timeout-minutes"):
                    timeout_count += 1
                
                if job_data.get("fail-fast") is True or (isinstance(job_data.get("fail-fast"), dict) and job_data.get("fail-fast", {}).get("job")):
                    fail_fast_count += 1
        
        cache_usage = (cache_count / job_count * 100) if job_count > 0 else 0
        security_usage = (security_count / job_count * 100) if job_count > 0 else 0
        artifact_usage = (artifact_count / job_count * 100) if job_count > 0 else 0
        timeout_usage = (timeout_count / job_count * 100) if job_count > 0 else 0
        
        secret_score = 2 if secret_count > 0 else 0
        fail_fast_score = 2 if fail_fast_count > 0 else 0
        
        return {
            "cache_usage": round(cache_usage, 1),
            "security_scan": round(security_usage, 1),
            "artifact_reuse": round(artifact_usage, 1),
            "secret_management": secret_score,
            "timeout_configured": round(timeout_usage, 1),
            "fail_fast": fail_fast_score,
        }
    
    @staticmethod
    def calculate_maintainability(ci_data: dict) -> dict:
        workflows = ci_data.get("workflows", {})
        scripts = ci_data.get("scripts", [])
        actions = ci_data.get("actions", [])
        
        job_count = 0
        reusable_action_count = 0
        custom_action_count = 0
        script_names = {s.get("name", "") for s in scripts}
        script_call_count = 0
        workflow_call_count = 0
        doc_comment_count = 0
        
        relationships = ci_data.get("relationships", {})
        action_usages = relationships.get("action_usages", {})
        
        for wf_name, wf in workflows.items():
            jobs = wf.get("jobs", {})
            
            for job_name, job in jobs.items():
                job_count += 1
                job_data = job if isinstance(job, dict) else {}
                steps = job_data.get("steps", [])
                
                for step in steps:
                    step_str = str(step).lower()
                    if "uses" in step_str:
                        if any(ua in step_str for ua in action_usages.keys()):
                            reusable_action_count += 1
                        if "actions/" in step_str and ("@" not in step_str or step_str.count("@") == 1):
                            custom_action_count += 1
                    
                    if "run:" in step_str:
                        script_call_count += 1
                
                if "workflow_call" in str(job_data):
                    workflow_call_count += 1
                
                job_str = str(job_data)
                if "# " in job_str or "name:" in job_str:
                    doc_comment_count += 1
        
        action_reuse = (reusable_action_count / job_count * 100) if job_count > 0 else 0
        custom_ratio = (custom_action_count / job_count * 100) if job_count > 0 else 0
        script_reuse = min((len(scripts) / max(script_call_count, 1)) * 100, 100)
        doc_coverage = (doc_comment_count / job_count * 100) if job_count > 0 else 0
        
        naming_score = 2 if workflow_call_count > 0 else 1
        
        return {
            "action_reuse": round(action_reuse, 1),
            "custom_action_ratio": round(custom_ratio, 1),
            "script_reuse": round(script_reuse, 1),
            "workflow_call_usage": workflow_call_count,
            "doc_coverage": round(doc_coverage, 1),
            "naming_consistency": naming_score,
        }
    
    def calculate_all(self, ci_data: dict) -> dict:
        return {
            "complexity": self.calculate_complexity(ci_data),
            "best_practices": self.calculate_best_practices(ci_data),
            "maintainability": self.calculate_maintainability(ci_data),
        }
