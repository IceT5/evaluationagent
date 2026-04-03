"""CIC/D Agent 状态定义"""
from typing import TypedDict, Optional, List, Dict, Any


CICD_STATE_FIELDS = {
    "input": ["project_path", "display_name", "storage_dir"],
    "loader": ["loader_result", "project_name"],
    "data": ["ci_data", "ci_data_path", "workflow_count"],
    "planning": ["strategy", "prompts", "prompt_strategy", "batch_files", "main_rounds", "main_system_prompt"],
    "execution": ["llm_responses", "merged_response", "key_configs"],
    "quality": ["validation_result", "retry_count", "max_retries"],
    "retry": ["retry_mode", "retry_issues", "cicd_existing_report"],
    "architecture": ["architecture_json_path"],
    "report": ["report_md", "report_html", "architecture_json", "cicd_analysis"],
    "output": ["analysis_summary"],
    "control": ["errors", "warnings"],
}

ALL_CICD_FIELDS = [f for fields in CICD_STATE_FIELDS.values() for f in fields]

OUTPUT_FIELDS = [
    "ci_data", "ci_data_path", "workflow_count", "strategy",
    "llm_responses", "merged_response", "key_configs", "validation_result",
    "report_md", "report_html", "architecture_json", "analysis_summary",
    "errors", "warnings",
]


def to_cicd_state(state: Dict[str, Any]) -> "CICDState":
    """从 EvaluatorState 提取 CICDState 所需字段
    
    使用字段分组简化映射。
    
    Args:
        state: EvaluatorState 或其子集
    
    Returns:
        CICDState 所需字段
    """
    result = {}
    for field in ALL_CICD_FIELDS:
        if field in state:
            result[field] = state[field]
    
    result["architecture_json_path"] = None
    
    return result


def from_cicd_state(state: Dict[str, Any], cicd_state: Dict[str, Any]) -> Dict[str, Any]:
    """将 CICDState 结果合并回 EvaluatorState
    
    只复制输出字段，避免覆盖其他Agent的输出。
    
    Args:
        state: 原始 EvaluatorState
        cicd_state: CICDOrchestrator 返回的状态
    
    Returns:
        合并后的状态
    """
    result = {**state}
    
    for field in OUTPUT_FIELDS:
        if field in cicd_state:
            result[field] = cicd_state[field]
    
    return result


class CICDState(TypedDict, total=False):
    """CI/CD 分析工作流状态"""
    
    # 输入
    project_path: str
    display_name: Optional[str]
    storage_dir: Optional[str]
    
    # 加载阶段
    loader_result: Optional[Dict[str, Any]]
    project_name: Optional[str]
    
    # 数据提取阶段
    ci_data: Optional[Dict[str, Any]]
    ci_data_path: Optional[str]
    workflow_count: int
    
    # 规划阶段
    strategy: str
    prompts: List[str]
    prompt_strategy: str
    batch_files: List[str]
    main_rounds: List[str]
    main_system_prompt: str
    
    # 执行阶段
    llm_responses: List[Dict[str, Any]]
    merged_response: str
    key_configs: List[Dict[str, str]]
    
    # 质量检查阶段
    validation_result: Optional[Dict[str, Any]]
    retry_count: int
    max_retries: int
    
    # 重试相关
    retry_mode: Optional[str]  # retry/supplement
    retry_issues: List[Dict[str, Any]]
    cicd_existing_report: Optional[str]
    
    # 架构验证
    architecture_json_path: Optional[str]
    
    # 报告阶段
    report_md: Optional[str]
    report_html: Optional[str]
    architecture_json: Optional[Dict[str, Any]]
    cicd_analysis: Optional[Dict[str, Any]]
    
    # 输出
    analysis_summary: Optional[Dict[str, Any]]
    errors: List[str]
    warnings: List[str]
