# 状态定义 - LangGraph 图中各 Agent 共享的数据
from typing import TypedDict, Optional, Any


class EvaluatorState(TypedDict):
    """全局状态"""

    # === UI 管理 ===
    ui_manager: Optional[Any]           # UI Manager 实例

    # === 输入阶段 ===
    user_input: Optional[str]           # 用户原始输入（路径或URL）
    project_url: Optional[str]          # 代码平台地址
    project_path: Optional[str]         # 本地项目路径
    display_name: Optional[str]         # 显示名称（可覆盖自动提取的项目名）

    # === 存储阶段 ===
    storage_version_id: Optional[str]  # 版本ID (v1_20260319_103000)
    storage_dir: Optional[str]         # 持久化存储路径

    # === 加载阶段 ===
    project_name: Optional[str]         # 项目名称
    clone_status: Optional[str]         # 克隆状态: success / failed / skipped
    clone_error: Optional[str]          # 克隆失败原因

    # === 分析阶段 ===
    cicd_analysis: Optional[dict]       # CI/CD 分析结果

    # === Reviewer 阶段 ===
    review_result: Optional[dict]       # 验证结果 {"status": "passed/corrected/critical/incomplete"}
    review_issues: Optional[list]       # 发现的问题列表
    review_retry_count: int            # 重试次数 (默认0)
    corrected_report: Optional[str]     # 修正后的报告（小错误直接修正时使用）
    cicd_retry_mode: Optional[str]     # "retry" / "supplement" / None
    cicd_retry_issues: Optional[list]   # 需要修正/补充的问题列表
    cicd_existing_report: Optional[str]  # 现有报告（补充模式时使用）

    # === 输出阶段 ===
    html_report: Optional[str]          # HTML 报告内容
    report_path: Optional[str]          # 报告文件路径

    # === 控制流 ===
    should_download: bool               # 是否需要下载
    current_step: str                   # 当前执行步骤
    errors: list[str]                   # 错误列表
