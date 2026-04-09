"""报告修复 Agent - 修复报告中的问题"""
from typing import Dict, Any, List
from pathlib import Path
import json

from evaluator.agents.base_agent import BaseAgent, AgentMeta
from evaluator.fix.coordinator import FixCoordinator
from evaluator.fix.method import DataFixMethod, LLMFixMethod


class ReportFixAgent(BaseAgent):
    """报告修复 Agent
    
    职责：修复 ReviewerAgent 发现的问题
    - 自动修复：从 ci_data.json 提取数据修复
    - LLM 修复：调用 LLM 生成缺失内容
    
    执行流程：
    1. 分类问题（自动修复 vs LLM 修复）
    2. 执行自动修复（不调用 LLM）
    3. 如果有需要 LLM 修复的问题，询问用户
    4. 执行 LLM 修复（如果用户同意）
    5. 返回修复结果
    
    输入：
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
            name="ReportFixAgent",
            description="修复报告中的问题",
            category="analysis",
            inputs=["review_issues", "report_md", "ci_data", "architecture_json"],
            outputs=["corrected_report", "architecture_json", "fix_result", "review_retry_count"],
            dependencies=["ReviewerAgent"],
        )
    
    def __init__(self, llm=None):
        super().__init__()
        self.llm = llm
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行报告修复"""
        issues = state.get("review_issues", [])
        
        report = state.get("corrected_report")
        if not report:
            report_path = state.get("report_md", "")
            if report_path:
                from pathlib import Path
                if Path(report_path).exists():
                    report = Path(report_path).read_text(encoding="utf-8")
                else:
                    report = ""
        
        ci_data = state.get("ci_data", {})
        arch = state.get("architecture_json", {})
        summary = state.get("analysis_summary", {})
        retry_count = state.get("review_retry_count", 0)
        
        storage_dir = state.get("storage_dir", "")
        
        print(f"\n{'='*50}")
        print("  报告修复")
        print(f"{'='*50}")
        
        if not issues:
            print("  无问题需要修复")
            return {"fix_result": {"status": "no_issues"}}
        
        # 检测报告问题（md_issue / html_issue），需要重试整个分析流程
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
            }
        
        data_fixable = [i for i in issues if i.get("type") in DataFixMethod.SUPPORTED_TYPES]
        llm_fixable = [i for i in issues if i.get("type") in LLMFixMethod.SUPPORTED_TYPES]
        
        print(f"  问题分类: 自动修复={len(data_fixable)}, LLM修复={len(llm_fixable)}")
        
        coordinator = FixCoordinator(ci_data, self.llm)
        
        if data_fixable:
            print(f"\n  [自动修复] 执行 {len(data_fixable)} 个修复...")
            result = coordinator.fix(report, data_fixable, arch, summary)
            
            if result.success:
                report = result.report
                arch = result.architecture
                summary = result.summary
                
                for log in result.fix_log:
                    print(f"    ✓ {log['type']}: {log['action']}")
        
        if llm_fixable:
            print(f"\n  [需要 LLM] {len(llm_fixable)} 个问题需要 LLM 生成内容")
            
            user_choice = self._ask_user_choice(llm_fixable, retry_count)
            
            if user_choice == "supplement":
                print(f"\n  [LLM 修复] 执行补充...")
                result = coordinator.fix(report, llm_fixable, arch, summary)
                
                if result.success:
                    report = result.report
                    arch = result.architecture
                    summary = result.summary
                    
                    for log in result.fix_log:
                        print(f"    ✓ {log['type']}: {log['action']}")
                    
                    self._save_files(storage_dir, report, arch, summary)
                    
                    return {
                        "corrected_report": report,
                        "architecture_json": arch,
                        "analysis_summary": summary,
                        "fix_result": {"status": "supplement", "fix_log": result.fix_log},
                        "review_retry_count": retry_count + 1,
                    }
            
            elif user_choice == "retry":
                return {
                    "fix_result": {"status": "retry"},
                    "review_retry_count": retry_count + 1,
                    "cicd_retry_mode": "retry",
                    "cicd_retry_issues": llm_fixable,
                }
            
            elif user_choice == "skip":
                self._save_files(storage_dir, report, arch, summary)
                return {
                    "corrected_report": report,
                    "architecture_json": arch,
                    "fix_result": {"status": "skip"},
                }
        
        self._save_files(storage_dir, report, arch, summary)
        
        return {
            "corrected_report": report,
            "architecture_json": arch,
            "analysis_summary": summary,
            "fix_result": {"status": "fixed", "count": len(data_fixable)},
        }
    
    def _ask_user_choice(self, issues: List[dict], retry_count: int) -> str:
        """询问用户选择"""
        import sys
        
        print(f"\n=== 请选择处理方式 ===\n")
        print(f"  [1] 补充模式 - 调用 LLM 补充缺失内容 (推荐)")
        print(f"  [2] 完全重做 - 重新执行 CICD 分析")
        print(f"  [3] 跳过验证 - 继续生成 HTML 报告")
        
        if not sys.stdin.isatty():
            print("\n  非交互模式，使用默认选项: [1] 补充模式")
            return "supplement"
        
        try:
            choice = input("\n请输入选项 [1/2/3]: ").strip()
            
            if choice == "1":
                return "supplement"
            elif choice == "2":
                return "retry"
            elif choice == "3":
                return "skip"
            else:
                return "supplement"
        except:
            return "supplement"
    
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
            for node in layer.get("nodes", []):
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