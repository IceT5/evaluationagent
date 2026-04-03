"""LangGraph 路由函数 - 条件分支定义"""
from typing import Literal, Dict, Any
from langsmith import traceable

from evaluator.state import EvaluatorState


@traceable()
def route_by_orchestrator(state: EvaluatorState) -> Literal["input", "loader", "cicd", "reviewer", "reporter", "end"]:
    """基于 OrchestratorAgent 决策的路由
    
    Args:
        state: 当前状态，包含 orchestrator_decision
    
    Returns:
        下一个节点名称
    """
    decision = state.get("orchestrator_decision", {})
    
    next_step = decision.get("next_step", "end")
    
    return next_step


@traceable()
def route_after_input(state: EvaluatorState) -> Literal["loader", "error_handler", "skip", "orchestrator"]:
    """输入后的路由
    
    Returns:
        loader: 继续加载
        error_handler: 处理错误
        skip: 跳过（无需下载）
        orchestrator: 正常完成，返回编排器
    """
    if state.get("errors"):
        return "error_handler"
    if state.get("should_download", False):
        return "orchestrator"
    return "skip"


@traceable()
def route_after_loader(state: EvaluatorState) -> Literal["cicd", "error_handler", "skip", "orchestrator"]:
    """加载后的路由
    
    Returns:
        cicd: 继续 CI/CD 分析
        error_handler: 处理错误
        skip: 跳过（无有效数据）
        orchestrator: 正常完成，返回编排器
    """
    if state.get("errors"):
        return "error_handler"
    
    project_path = state.get("project_path")
    if not project_path:
        return "skip"
    
    return "orchestrator"


@traceable()
def route_after_cicd(state: EvaluatorState) -> Literal["reviewer", "error_handler", "skip", "cicd", "orchestrator"]:
    """CI/CD 分析后的路由
    
    Returns:
        reviewer: 继续验证
        error_handler: 处理错误
        skip: 跳过（无 CI/CD 数据）
        cicd: 重试 CI/CD 分析
        orchestrator: 正常完成，返回编排器
    """
    cicd_analysis = state.get("cicd_analysis", {})
    status = cicd_analysis.get("status")
    
    if status == "no_cicd":
        return "skip"
    
    if status == "failed":
        retry_count = state.get("cicd_retry_count", 0)
        if retry_count < 3:
            return "cicd"
        return "error_handler"
    
    if status == "success":
        return "orchestrator"
    
    return "orchestrator"


@traceable()
def route_after_review(state: EvaluatorState) -> Literal["reporter", "cicd", "error_handler", "orchestrator"]:
    """验证后的路由
    
    注意: 此函数只返回路由决策，不修改状态。
    状态修改由对应的 Agent 节点负责。
    
    Returns:
        reporter: 继续生成报告
        cicd: 重做分析
        error_handler: 处理错误
        orchestrator: 正常完成，返回编排器
    """
    review_result = state.get("review_result", {})
    status = review_result.get("status", "unknown")
    
    if status in ["passed", "corrected"]:
        return "orchestrator"
    
    if status == "critical" or status == "incomplete":
        retry_count = state.get("cicd_retry_count", 0)
        if retry_count < 3:
            return "cicd"
        return "reporter"
    
    return "orchestrator"


@traceable()
def route_after_reporter(state: EvaluatorState) -> Literal["success", "error_handler"]:
    """报告生成后的路由
    
    Returns:
        success: 完成
        error_handler: 处理错误
    """
    if state.get("errors"):
        return "error_handler"
    return "success"


@traceable()
def should_skip_review(state: EvaluatorState) -> bool:
    """判断是否应该跳过 review 步骤
    
    Returns:
        True: 跳过 review
        False: 不跳过
    """
    if state.get("skip_review", False):
        return True
    
    cicd_analysis = state.get("cicd_analysis", {})
    workflow_count = cicd_analysis.get("workflows_count", 0)
    
    if workflow_count <= 5:
        return True
    
    return False


@traceable()
def should_use_parallel(state: EvaluatorState) -> bool:
    """判断是否应该使用并行分析
    
    Returns:
        True: 使用并行
        False: 使用串行
    """
    cicd_analysis = state.get("cicd_analysis", {})
    workflow_count = cicd_analysis.get("workflows_count", 0)
    
    if workflow_count > 30:
        return True
    
    return False


@traceable()
def evaluate_quality(state: EvaluatorState) -> Dict[str, Any]:
    """评估结果质量
    
    Returns:
        质量评估结果，包含 score, passed, message
    """
    errors = state.get("errors", [])
    
    if errors:
        error_count = len(errors)
        score = max(0, 1.0 - error_count * 0.1)
        return {
            "score": score,
            "passed": score >= 0.7,
            "message": f"存在 {error_count} 个错误",
        }
    
    cicd_analysis = state.get("cicd_analysis", {})
    status = cicd_analysis.get("status")
    
    if status == "success":
        return {
            "score": 0.95,
            "passed": True,
            "message": "分析成功",
        }
    elif status == "no_cicd":
        return {
            "score": 0.5,
            "passed": True,
            "message": "无 CI/CD 数据",
        }
    else:
        return {
            "score": 0.3,
            "passed": False,
            "message": f"状态异常: {status}",
        }


@traceable()
def decide_next_action(state: EvaluatorState) -> str:
    """决定下一步操作
    
    Returns:
        下一个节点名称
    """
    completed_steps = state.get("completed_steps", [])
    
    workflow = ["input", "loader", "cicd", "reviewer", "reporter"]
    
    for step in workflow:
        if step not in completed_steps:
            return step
    
    return "END"


@traceable()
def prepare_cicd_retry(state: EvaluatorState) -> Dict[str, Any]:
    """准备 CI/CD 重试的状态更新
    
    由 CICDAgent 在重试前调用，更新重试相关状态。
    统一字段名供 CICDOrchestrator 和 RetryHandlingAgent 使用。
    
    Returns:
        状态更新字典
    """
    retry_mode = state["cicd_retry_mode"]
    retry_count = state.get("cicd_retry_count", 0) + 1
    retry_issues = state.get("cicd_retry_issues", [])
    existing_report = state.get("cicd_existing_report")
    
    return {
        "retry_mode": retry_mode,
        "retry_issues": retry_issues,
        "cicd_existing_report": existing_report,
        "cicd_retry_mode": retry_mode,
        "cicd_retry_count": retry_count,
    }


INTENT_WORKFLOWS = {
    "analyze": ["input", "loader", "cicd", "reviewer", "reporter"],
    "compare": ["compare"],
    "list": ["list_handler"],
    "info": ["info_handler"],
    "delete": ["delete_handler"],
    "help": ["help_handler"],
    "unknown": [],
}


@traceable()
def route_intent(state: EvaluatorState) -> Literal[
    "input", "loader", "cicd", "reviewer", "reporter",
    "compare", "list_handler", "info_handler", "delete_handler",
    "help_handler", "end"
]:
    """基于意图的路由 - OrchestratorAgent 决策后调用
    
    Args:
        state: 当前状态，包含 intent, orchestrator_decision
    
    Returns:
        下一个节点名称
    """
    intent = state.get("intent", "unknown")
    orchestrator_decision = state.get("orchestrator_decision", {})
    
    if orchestrator_decision.get("needs_clarification"):
        return "end"
    
    next_step = orchestrator_decision.get("next_step")
    if next_step:
        return next_step
    
    workflow = INTENT_WORKFLOWS.get(intent, INTENT_WORKFLOWS["unknown"])
    
    if not workflow:
        return "end"
    
    completed_steps = state.get("completed_steps", [])
    
    for step in workflow:
        if step not in completed_steps:
            return step
    
    return "end"


@traceable()
def route_error(state: EvaluatorState) -> Literal["retry", "recover", "end"]:
    """错误处理后的路由
    
    根据错误类型决定下一步：
    - retry: 可恢复错误，返回上一步重试
    - recover: 错误已处理，继续执行
    - end: 致命错误，终止流程
    
    Args:
        state: 当前状态，包含 errors, error_recoverable
    
    Returns:
        下一个节点名称
    """
    errors = state.get("errors", [])
    error_recoverable = state.get("error_recoverable", False)
    
    if not errors:
        return "recover"
    
    fatal_errors = [e for e in errors if _is_fatal_error(e)]
    
    if fatal_errors:
        return "end"
    
    if error_recoverable:
        return "retry"
    
    return "end"


def _is_fatal_error(error: str) -> bool:
    """判断是否为致命错误
    
    Args:
        error: 错误信息
    
    Returns:
        True: 致命错误，False: 可恢复错误
    """
    fatal_patterns = [
        "authentication failed",
        "permission denied",
        "invalid api key",
        "not found: project",
        "timeout: exceeded",
    ]
    
    error_lower = error.lower()
    return any(pattern in error_lower for pattern in fatal_patterns)


@traceable()
def route_after_validate(state: EvaluatorState) -> Literal["input", "orchestrator", "end"]:
    """验证后的路由
    
    Returns:
        input: 验证失败，需要修正输入
        orchestrator: 验证通过，继续执行
        end: 致命错误，终止流程
    """
    validation_result = state.get("validation_result")
    
    if not validation_result:
        return "orchestrator"
    
    valid = validation_result.get("valid", True)
    issues = validation_result.get("issues", [])
    
    if not valid:
        critical_issues = [i for i in issues if "missing" in i.lower() or "required" in i.lower()]
        if critical_issues:
            return "end"
        return "input"
    
    return "orchestrator"


@traceable()
def route_after_reviewer(state: EvaluatorState) -> Literal["report_fix", "reporter", "orchestrator"]:
    """ReviewerAgent 后的路由
    
    Returns:
        report_fix: 发现问题，需要修复
        reporter: 无问题，继续生成报告
        orchestrator: 正常完成，返回编排器
    """
    review_result = state.get("review_result", {})
    status = review_result.get("status", "unknown")
    
    if status == "passed":
        return "orchestrator"
    
    if status == "issues_found":
        return "report_fix"
    
    return "orchestrator"


@traceable()
def route_after_report_fix(state: EvaluatorState) -> Literal["reviewer", "reporter", "cicd", "orchestrator"]:
    """ReportFixAgent 后的路由
    
    Returns:
        reviewer: 修复完成，重新验证
        reporter: 跳过或达到重试上限
        cicd: 用户选择重试
        orchestrator: 正常完成，返回编排器
    """
    fix_result = state.get("fix_result", {})
    review_retry_count = state.get("review_retry_count", 0)
    max_retries = state.get("max_review_retries", 3)
    
    if review_retry_count >= max_retries:
        print("  ⚠️ 验证重试次数已达上限，继续生成报告")
        return "reporter"
    
    fix_status = fix_result.get("status", "")
    
    if fix_status == "fixed":
        print("  🔄 自动修复完成，重新验证")
        return "reviewer"
    
    if fix_status == "supplement":
        print("  🔄 LLM 补充完成，重新验证")
        return "reviewer"
    
    if fix_status == "retry":
        print("  🔄 用户选择重试，重新执行 CICD")
        return "cicd"
    
    if fix_status == "skip":
        return "reporter"
    
    if fix_status == "no_issues":
        return "orchestrator"
    
    return "reporter"
