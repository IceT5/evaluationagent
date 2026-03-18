# 状态定义 - LangGraph 图中各 Agent 共享的数据
from typing import TypedDict, Optional


class EvaluatorState(TypedDict):
    """全局状态"""

    # === 输入阶段 ===
    user_input: Optional[str]           # 用户原始输入（路径或URL）
    project_url: Optional[str]          # 代码平台地址
    project_path: Optional[str]         # 本地项目路径

    # === 加载阶段 ===
    project_name: Optional[str]         # 项目名称
    clone_status: Optional[str]         # 克隆状态: success / failed / skipped
    clone_error: Optional[str]          # 克隆失败原因

    # === 分析阶段 ===
    cicd_analysis: Optional[dict]       # CI/CD 分析结果
    # 后续可以加更多分析结果
    # build_analysis: Optional[dict]
    # quality_analysis: Optional[dict]

    # === 输出阶段 ===
    html_report: Optional[str]          # HTML 报告内容
    report_path: Optional[str]          # 报告文件路径

    # === 控制流 ===
    should_download: bool               # 是否需要下载
    current_step: str                   # 当前执行步骤
    errors: list[str]                   # 错误列表
