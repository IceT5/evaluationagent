"""报告修复 Agent - 分析问题并等待用户决策，然后执行修复

拆分为两个 Agent：
- ReportFixPlanAgent：纯读取 + 分类 + interrupt 等待用户决策
- ReportFixApplyAgent：根据用户选择执行实际修复

拆分原因：
- LangGraph interrupt() 恢复时从节点开头重跑
- 必须确保 interrupt 前无不可重放的副作用
- Plan 节点只做纯读取/纯计算，Apply 节点执行修复
"""
from typing import Dict, Any, List
from pathlib import Path
import json

from evaluator.agents.base_agent import BaseAgent, AgentMeta
from evaluator.fix.coordinator import FixCoordinator
from evaluator.fix.method import DataFixMethod, LLMFixMethod


class ReportFixPlanAgent(BaseAgent):
    """报告修复决策 Agent
    
    职责：分析问题 → 生成选项 → interrupt 等待用户决策
    注意：此节点只做纯读取和纯计算，不做任何修复执行。
    interrupt 前的所有操作必须幂等（resume 时节点会从头重跑）。
    
    输入：
    - review_issues: 问题列表
    - interactive_mode: 是否允许交互
    
    输出：
    - user_fix_choice: 用户选择
    - fix_result: 仅在无需人工决策时直接产出（如 no_issues / retry）
    """
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="ReportFixPlanAgent",
            description="分析修复问题并等待用户决策",
            category="analysis",
            inputs=["review_issues", "interactive_mode"],
            outputs=["user_fix_choice", "fix_result"],
            dependencies=["ReviewerAgent"],
        )
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """分析问题并等待用户决策"""
        issues = state.get("review_issues", [])
        retry_count = state.get("review_retry_count", 0)
        interactive = state.get("interactive_mode", True)
        
        # 无问题
        if not issues:
            print("  无问题需要修复")
            return {"fix_result": {"status": "no_issues"}, "user_fix_choice": None}
        
        # 报告问题（md_issue / html_issue）→ 直接 retry，不经过 interrupt
        report_issues = [i for i in issues if i.get("type") in ("md_issue", "html_issue")]
        if report_issues:
            print(f"  发现 {len(report_issues)} 个报告问题，需要重试整个分析流程")
            for issue in report_issues:
                print(f"    - [{issue.get('type')}] {issue.get('message')}")
            return {
                "fix_result": {"status": "retry"},
                "review_retry_count": retry_count + 1,
                "cicd_retry_mode": "retry",
                "cicd_retry_issues": report_issues,
                "user_fix_choice": "retry",
            }
        
        # 纯分类（幂等）
        data_completion = [i for i in issues if i.get("type") in DataFixMethod.SUPPORTED_TYPES]
        content_supplement = [i for i in issues if i.get("type") in LLMFixMethod.SUPPORTED_TYPES]
        
        has_data = len(data_completion) > 0
        has_content = len(content_supplement) > 0

        # 无可修复的问题
        if not has_data and not has_content:
            return {"fix_result": {"status": "no_issues"}, "user_fix_choice": None}

        # 非交互模式：使用默认选项，不触发 interrupt
        if not interactive:
            default = "fix_and_supplement" if (has_data and has_content) else \
                      "data_only" if has_data else "supplement"
            print(f"  非交互模式，使用默认选项: {default}")
            return {"user_fix_choice": default}
        
        # 构建动态选项
        options = self._build_options(has_data, has_content)
        
        print(f"\n{'='*50}")
        print("  报告修复 - 等待用户决策")
        print(f"{'='*50}")
        print(f"  问题分类: 数据补全={len(data_completion)}, 内容补充={len(content_supplement)}")
        
        # interrupt：等待用户决策
        from langgraph.types import interrupt
        user_choice = interrupt({
            "kind": "review_fix_decision",
            "question": "Review 发现问题，请选择处理方式",
            "options": options,
            "default": options[0]["value"],
            "data_completion_count": len(data_completion),
            "content_supplement_count": len(content_supplement),
            "retry_count": retry_count,
        })
        
        choice = user_choice or options[0]["value"]
        return {"user_fix_choice": choice}
    
    def _build_options(self, has_data: bool, has_content: bool) -> list:
        """根据问题类型动态构建选项"""
        if has_data and has_content:
            return [
                {"value": "fix_and_supplement", "label": "[1] 数据补全 + 内容补充（推荐）"},
                {"value": "data_only",          "label": "[2] 仅数据补全 - 不调用 LLM"},
                {"value": "retry",              "label": "[3] 完全重做 - 重新执行 CICD 分析"},
                {"value": "skip",               "label": "[4] 跳过 - 不做任何修复，直接生成报告"},
            ]
        elif has_data:
            return [
                {"value": "data_only", "label": "[1] 应用数据补全（推荐）"},
                {"value": "retry",     "label": "[2] 完全重做 - 重新执行 CICD 分析"},
                {"value": "skip",      "label": "[3] 跳过 - 不做任何修复，直接生成报告"},
            ]
        else:  # only has_content
            return [
                {"value": "supplement", "label": "[1] 内容补充 - 调用 LLM 补充缺失内容（推荐）"},
                {"value": "retry",      "label": "[2] 完全重做 - 重新执行 CICD 分析"},
                {"value": "skip",       "label": "[3] 跳过 - 继续生成 HTML 报告"},
            ]


class ReportFixApplyAgent(BaseAgent):
    """报告修复执行 Agent
    
    职责：根据用户选择执行实际修复
    注意：所有修复操作都在此节点执行，不存在重入副作用问题。
    
    输入：
    - user_fix_choice: 用户选择（来自 Plan 节点）
    - review_issues: 问题列表
    - report_md / corrected_report: 报告内容
    - ci_data: 项目数据
    - architecture_json: 架构 JSON
    
    输出：
    - corrected_report: 修正后的报告
    - architecture_json: 修正后的架构 JSON
    - fix_result: 修复结果
    - review_retry_count: 更新的重试次数
    """
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="ReportFixApplyAgent",
            description="根据用户决策执行修复",
            category="analysis",
            inputs=["user_fix_choice", "review_issues", "report_md", "ci_data", "architecture_json"],
            outputs=["corrected_report", "architecture_json", "fix_result", "review_retry_count"],
            dependencies=["ReportFixPlanAgent"],
        )
    
    def __init__(self, llm=None):
        super().__init__()
        self.llm = llm
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """根据用户选择执行修复"""
        choice = state.get("user_fix_choice", "skip")
        issues = state.get("review_issues", [])
        report = self._read_report(state)
        ci_data = state.get("ci_data", {})
        assembled_data = state.get("cicd_assembled_data") or {}
        arch = state.get("architecture_json") or assembled_data.get("artifacts", {}).get("architecture_json", {})
        summary = state.get("analysis_summary", {})
        retry_count = state.get("review_retry_count", 0)
        storage_dir = state.get("storage_dir", "")
        
        data_completion = [i for i in issues if i.get("type") in DataFixMethod.SUPPORTED_TYPES]
        content_supplement = [i for i in issues if i.get("type") in LLMFixMethod.SUPPORTED_TYPES]
        
        coordinator = FixCoordinator(ci_data, self.llm)
        
        print(f"\n{'='*50}")
        print(f"  报告修复 - 执行: {choice}")
        print(f"{'='*50}")
        
        # === 根据用户选择执行 ===
        
        if choice == "fix_and_supplement":
            # 数据补全 + 内容补充
            report, arch, summary = self._apply_data_completion(
                coordinator, report, data_completion, arch, summary)
            report, arch, summary, fix_log = self._apply_content_supplement(
                coordinator, report, content_supplement, arch, summary)
            self._save_files(storage_dir, report, arch, summary)
            return {
                "corrected_report": report,
                "architecture_json": arch,
                "analysis_summary": summary,
                "fix_result": {"status": "supplement", "fix_log": fix_log},
                "review_retry_count": retry_count + 1,
                "section_assignment_result": None,
            }
        
        elif choice == "supplement":
            # 仅内容补充（无数据补全问题）
            report, arch, summary, fix_log = self._apply_content_supplement(
                coordinator, report, content_supplement, arch, summary)
            self._save_files(storage_dir, report, arch, summary)
            return {
                "corrected_report": report,
                "architecture_json": arch,
                "analysis_summary": summary,
                "fix_result": {"status": "supplement", "fix_log": fix_log},
                "review_retry_count": retry_count + 1,
            }
        
        elif choice == "data_only":
            # 仅数据补全
            report, arch, summary = self._apply_data_completion(
                coordinator, report, data_completion, arch, summary)
            self._save_files(storage_dir, report, arch, summary)
            return {
                "corrected_report": report,
                "architecture_json": arch,
                "analysis_summary": summary,
                "fix_result": {"status": "fixed", "count": len(data_completion)},
                "review_retry_count": retry_count + 1,
                "section_assignment_result": None,
            }
        
        elif choice == "retry":
            # 完全重做
            return {
                "fix_result": {"status": "retry"},
                "review_retry_count": retry_count + 1,
                "cicd_retry_mode": "retry",
                "cicd_retry_issues": content_supplement,
            }
        
        elif choice == "skip":
            # 跳过
            return {"fix_result": {"status": "skip"}}
        
        # fallback
        return {"fix_result": {"status": "skip"}}
    
    def _read_report(self, state: Dict[str, Any]) -> str:
        """读取报告内容"""
        report = state.get("corrected_report")
        if not report:
            report_path = state.get("report_md", "")
            if report_path and Path(report_path).exists():
                report = Path(report_path).read_text(encoding="utf-8")
            else:
                report = ""
        return report or ""
    
    def _apply_data_completion(self, coordinator, report: str, issues: list,
                               arch: dict, summary: dict) -> tuple:
        """执行数据补全"""
        if not issues:
            return report, arch, summary
        print(f"\n  [数据补全] 执行 {len(issues)} 个补全...")
        result = coordinator.fix(report, issues, arch, summary)
        if result.success:
            for log in result.fix_log:
                print(f"    ✓ {log['type']}: {log['action']}")
            return result.report, result.architecture, result.summary
        return report, arch, summary
    
    def _apply_content_supplement(self, coordinator, report: str, issues: list,
                                  arch: dict, summary: dict) -> tuple:
        """执行内容补充"""
        if not issues:
            return report, arch, summary, []
        print(f"\n  [内容补充] 执行 {len(issues)} 个补充...")
        result = coordinator.fix(report, issues, arch, summary)
        if result.success:
            for log in result.fix_log:
                print(f"    ✓ {log['type']}: {log['action']}")
            return result.report, result.architecture, result.summary, result.fix_log
        return report, arch, summary, []
    
    def _save_files(self, storage_dir: str, report: str, arch: Dict, summary: Dict):
        """保存修正后的文件"""
        if not storage_dir:
            return
        
        storage_path = Path(storage_dir)
        
        try:
            if report:
                is_path_like = (
                    '\n' not in report and 
                    ('\\' in report or '/' in report) and
                    len(report) < 500
                )
                if is_path_like:
                    print(f"  [WARN] report 内容异常（疑似文件路径），跳过保存: {report[:100]}")
                else:
                    report_path = storage_path / "CI_ARCHITECTURE.md"
                    report_path.write_text(report, encoding="utf-8")
            
            if arch:
                arch = self._clean_invalid_connections(arch)
                arch_path = storage_path / "architecture.json"
                with open(arch_path, "w", encoding="utf-8") as f:
                    json.dump(arch, f, ensure_ascii=False, indent=2)
            
            if summary:
                summary_path = storage_path / "analysis_summary.json"
                with open(summary_path, "w", encoding="utf-8") as f:
                    json.dump(summary, f, ensure_ascii=False, indent=2)
        
        except Exception as e:
            print(f"  [WARN] 保存文件失败: {e}")
    
    def _clean_invalid_connections(self, arch: Dict) -> Dict:
        """清理无效连接（指向不存在节点的连接）"""
        if not arch:
            return arch
        
        all_node_ids = set()
        for layer in arch.get("layers", []):
            for node in arch.get("nodes", []):
                node_id = node.get("id")
                if node_id:
                    all_node_ids.add(node_id)
        
        original_connections = arch.get("connections", [])
        valid_connections = [
            c for c in original_connections
            if c.get("source") in all_node_ids and c.get("target") in all_node_ids
        ]
        
        removed_count = len(original_connections) - len(valid_connections)
        if removed_count > 0:
            print(f"  清理了 {removed_count} 个无效连接")
        
        arch["connections"] = valid_connections
        return arch


# 向后兼容别名：保持旧代码中 ReportFixAgent 的引用不立即断裂
# 注意：ReportFixAgent 已拆分为 ReportFixPlanAgent + ReportFixApplyAgent
# 此别名仅用于过渡期，新代码不应使用
ReportFixAgent = ReportFixApplyAgent
