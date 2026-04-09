"""修复协调器 - 组合策略和途径"""
from typing import List, Dict, Tuple, Any
from .models import FixInstruction, FixResult
from .strategy import FixExecutor, MultiFileSync
from .method import DataFixMethod, LLMFixMethod


class FixCoordinator:
    """修复协调器 - 组合修复策略和修复途径"""
    
    def __init__(self, ci_data: Dict, llm_client=None):
        self.ci_data = ci_data
        
        self.data_method = DataFixMethod(ci_data)
        self.llm_method = LLMFixMethod(llm_client) if llm_client else None
        
        self.executor = FixExecutor()
        self.file_sync = MultiFileSync()
    
    def fix(self, report: str, issues: List[Dict], 
            arch: Dict, summary: Dict) -> FixResult:
        """执行修复流程"""
        
        fix_log = []
        
        try:
            data_issues = [i for i in issues if self.data_method.can_fix(i.get("type"))]
            llm_issues = [i for i in issues if self.llm_method and self.llm_method.can_fix(i.get("type"))]
            
            if data_issues:
                report, arch, summary, log = self._fix_with_method(
                    report, data_issues, self.data_method, arch, summary
                )
                fix_log.extend(log)
            
            if llm_issues:
                report, arch, summary, log = self._fix_with_method(
                    report, llm_issues, self.llm_method, arch, summary
                )
                fix_log.extend(log)
            
            return FixResult(
                report=report,
                architecture=arch,
                summary=summary,
                fix_log=fix_log,
                success=True,
            )
        
        except Exception as e:
            return FixResult(
                report=report,
                architecture=arch,
                summary=summary,
                fix_log=fix_log,
                success=False,
                message=f"修复失败: {e}。建议重新执行 CICD 分析。",
            )
    
    def _fix_with_method(self, report: str, issues: List[Dict], 
                         method, arch: Dict, summary: Dict) -> Tuple[str, Dict, Dict, List]:
        """使用指定途径执行修复"""
        
        fix_log = []
        
        instructions = []
        for issue in issues:
            content = method.generate_content(issue, {"ci_data": self.ci_data})
            
            instructions.append(FixInstruction(
                type=issue.get("type"),
                severity=issue.get("severity"),
                anchor=self._get_anchor(issue),
                action=self._get_action(issue),
                content=content,
                target_files=["CI_ARCHITECTURE.md", "architecture.json"],
                sync_data=self._get_sync_data(issue),
            ))
        
        report, executed = self.executor.execute_batch(report, instructions)
        
        for inst in executed:
            arch, summary = self.file_sync.sync(inst.type, inst.sync_data, arch, summary)
            fix_log.append({
                "type": inst.type,
                "action": inst.action,
                "status": "fixed",
                "workflow": inst.sync_data.get("workflow") if inst.sync_data else None,
                "entity": inst.sync_data.get("entity") if inst.sync_data else None,
                "message": inst.sync_data.get("message") if inst.sync_data else None,
            })
        
        return report, arch, summary, fix_log
    
    def _get_anchor(self, issue: Dict) -> Dict:
        """获取锚点信息
        
        优先使用 issue 中已有的 anchor（由 ReviewerAgent 在发现问题时记录）
        如果没有，则根据问题类型推断
        """
        # 优先使用 issue 中已有的 anchor
        if issue.get("anchor"):
            return issue["anchor"]
        
        # 降级：根据问题类型推断
        issue_type = issue.get("type")
        wf_name = issue.get("workflow")
        entity = issue.get("entity")
        
        anchor_map = {
            "trigger_missing": {"type": "trigger_yaml", "workflow": wf_name},
            "trigger_fabricated": {"type": "trigger_yaml", "workflow": wf_name},
            "job_fake": {"type": "job_row", "workflow": wf_name, "job": entity},
            "job_missing": {"type": "job_table", "workflow": wf_name},
            "workflow_fake": {"type": "workflow_section", "workflow": entity},
            "workflow_missing": {"type": "stage_section", "workflow": entity},
            "script_fake": {"type": "script_ref", "script": entity},
        }
        
        return anchor_map.get(issue_type, {})
    
    def _get_action(self, issue: Dict) -> str:
        """根据问题类型获取操作类型"""
        issue_type = issue.get("type")
        
        delete_types = {"job_fake", "workflow_fake", "trigger_fabricated"}
        insert_types = {"trigger_missing", "workflow_missing", "job_missing"}
        replace_types = {"script_fake"}
        
        if issue_type in delete_types:
            return "delete"
        elif issue_type in insert_types:
            return "insert"
        elif issue_type in replace_types:
            return "replace"
        
        return "insert"
    
    def _get_sync_data(self, issue: Dict) -> Dict:
        """获取多文件同步数据"""
        return {
            "workflow": issue.get("workflow"),
            "entity": issue.get("entity"),
            "message": issue.get("message"),
        }