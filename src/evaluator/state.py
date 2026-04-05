"""统一状态定义 - LangGraph图中各Agent共享的数据

设计原则:
1. 所有字段都有明确的类型
2. 可变集合使用Reducer自动合并
3. 字段按功能分组

Reducer使用:
- errors: Annotated[List[str], merge_errors]  # 多节点追加错误
- completed_steps: Annotated[List[str], merge_steps]  # 多节点去重合并
- warnings: Annotated[List[str], merge_warnings]  # 多节点追加警告
"""
from typing import TypedDict, Optional, Any, List, Dict, Annotated


# === Reducer函数 ===
def merge_errors(left: List[str], right: List[str]) -> List[str]:
    """错误列表reducer - 追加合并
    
    用于多节点返回错误时自动合并。
    """
    return left + right


def merge_steps(left: List[str], right: List[str]) -> List[str]:
    """完成步骤reducer - 去重合并（保持顺序）
    
    用于多节点返回completed_steps时去重。
    """
    return list(dict.fromkeys(left + right))


def merge_warnings(left: List[str], right: List[str]) -> List[str]:
    """警告列表reducer - 追加合并
    
    用于多节点追加警告。
    """
    return left + right


def merge_lists(left: list, right: list) -> list:
    """通用列表reducer - 追加合并"""
    return left + right


class EvaluatorState(TypedDict, total=False):
    """统一状态定义 - 合并原EvaluatorState和CICDState
    
    使用Reducer的字段会在多节点更新时自动合并。
    """
    
    # ========== UI管理 ==========
    ui_manager: Optional[Any]
    
    # ========== 用户输入 ==========
    user_input: Optional[str]
    intent: Optional[str]
    params: Dict[str, Any]
    
    # ========== 上下文信息 ==========
    known_projects: List[str]
    context: Dict[str, Any]
    
    # ========== 项目信息 ==========
    project_name: Optional[str]
    project_path: Optional[str]
    project_url: Optional[str]
    display_name: Optional[str]
    
    # ========== 存储信息 ==========
    storage_version_id: Optional[str]
    storage_dir: Optional[str]
    
    # ========== 加载阶段 ==========
    clone_status: Optional[str]
    clone_error: Optional[str]
    
    # ========== CI/CD数据 (合并CICDState) ==========
    ci_data: Optional[Dict]
    ci_data_path: Optional[str]
    workflow_count: int
    actions_count: int
    
    # ========== 分析策略 ==========
    strategy: Optional[str]  # single/parallel/skip
    prompts: List[str]
    llm_responses: List[str]
    merged_response: Optional[str]
    
    # ========== 分析结果 ==========
    cicd_analysis: Optional[Dict]
    validation_result: Optional[Dict]
    report_md: Optional[str]
    report_html: Optional[str]
    architecture_json: Optional[Dict]
    analysis_summary: Optional[Dict]
    
    # ========== Review结果 ==========
    review_result: Optional[Dict]
    review_issues: List[Dict]
    corrected_report: Optional[str]
    fix_result: Optional[Dict]
    
    # ========== 智能Agent输出 ==========
    similar_projects: List[Dict]
    comparison_suggestions: List[Dict]
    project_trends: Optional[Dict]
    recommendations: List[Dict]
    quick_wins: List[Dict]
    reflection_result: Optional[Dict]
    best_practices: List[Dict]  # RecommendationAgent 输出的最佳实践列表
    
    # ========== 处理器输出 ==========
    list_result: Optional[Dict]
    info_result: Optional[Dict]
    delete_result: Optional[Dict]
    help_result: Optional[Dict]
    
    # ========== 控制流 ==========
    should_download: Optional[bool]
    skip_review: bool
    current_step: Optional[str]
    orchestrator_decision: Optional[Dict]
    
    # ========== 完成步骤 (使用Reducer) ==========
    completed_steps: Annotated[List[str], merge_steps]
    
    # ========== 重试控制 ==========
    retry_count: int
    retry_mode: Optional[str]  # retry/supplement
    retry_issues: List[Dict]
    
    # ========== CI/CD 重试控制 (兼容字段) ==========
    cicd_retry_mode: Optional[str]
    cicd_retry_issues: List[Dict]
    cicd_retry_count: int
    cicd_existing_report: Optional[str]
    
    # ========== Review 重试控制 ==========
    review_retry_count: int
    
    # ========== 错误和警告 (使用Reducer) ==========
    errors: Annotated[List[str], merge_errors]
    warnings: Annotated[List[str], merge_warnings]
    
    # ========== 对比功能 ==========
    project_a: Optional[str]
    project_b: Optional[str]
    version_a: Optional[str]
    version_b: Optional[str]
    dimensions: Optional[List[str]]
    comparison_result: Optional[Dict]
    comparison_dir: Optional[str]  # CompareAgent 输出的对比结果目录路径
    
    # ========== LLM配置 ==========
    llm: Optional[Any]
    llm_config: Dict[str, Any]


# === 向后兼容别名 ===
# 保留旧的字段名作为别名，便于逐步迁移
EvaluatorStateAlias = EvaluatorState
