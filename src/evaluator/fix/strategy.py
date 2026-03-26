"""修复策略 - 锚点定位、执行修复、多文件同步"""
import re
from typing import List, Tuple, Dict, Any
from .models import FixPosition, FixInstruction


class AnchorResolver:
    """锚点解析器 - 将锚点转换为具体位置"""
    
    def resolve(self, anchor: Dict, content: str) -> FixPosition:
        """解析锚点，返回位置"""
        anchor_type = anchor.get("type", "")
        
        method_map = {
            "workflow_section": self._resolve_workflow_section,
            "trigger_yaml": self._resolve_trigger_yaml,
            "job_table": self._resolve_job_table,
            "job_row": self._resolve_job_row,
            "stage_section": self._resolve_stage_section,
        }
        
        resolver = method_map.get(anchor_type)
        if resolver:
            return resolver(anchor, content)
        
        return FixPosition.not_found()
    
    def resolve_batch(self, anchors: List[Dict], content: str) -> List[Tuple[FixPosition, Dict]]:
        """批量解析，按位置降序排列（从后向前）"""
        positions = [(self.resolve(a, content), a) for a in anchors]
        valid = [(p, a) for p, a in positions if p.is_valid]
        valid.sort(key=lambda x: x[0].start, reverse=True)
        return valid
    
    def _resolve_workflow_section(self, anchor: Dict, content: str) -> FixPosition:
        """定位工作流章节"""
        wf_name = anchor.get("workflow", "")
        pattern = rf"####\s+\d+\.\d+\s+{re.escape(wf_name)}"
        match = re.search(pattern, content)
        
        if match:
            next_section = re.search(r'\n####\s+\d+\.\d+', content[match.end():])
            if next_section:
                end = match.end() + next_section.start()
            else:
                end = len(content)
            return FixPosition(start=match.start(), end=end, file="report")
        
        return FixPosition.not_found()
    
    def _resolve_trigger_yaml(self, anchor: Dict, content: str) -> FixPosition:
        """定位触发条件 YAML 块（用于插入）"""
        wf_name = anchor.get("workflow", "")
        
        wf_pattern = rf"####\s+\d+\.\d+\s+{re.escape(wf_name)}"
        wf_match = re.search(wf_pattern, content)
        if not wf_match:
            return FixPosition.not_found()
        
        section_start = wf_match.start()
        next_section = re.search(r'\n####\s+\d+\.\d+', content[wf_match.end():])
        section_end = wf_match.end() + next_section.start() if next_section else len(content)
        section = content[section_start:section_end]
        
        yaml_pattern = r'触发条件.*?```yaml(.*?)```'
        yaml_match = re.search(yaml_pattern, section, re.DOTALL)
        
        if yaml_match:
            insert_pos = section_start + yaml_match.end() - 3
            return FixPosition(start=insert_pos, end=insert_pos, file="report")
        
        return FixPosition.not_found()
    
    def _resolve_job_table(self, anchor: Dict, content: str) -> FixPosition:
        """定位 Job 表格（用于插入）"""
        wf_name = anchor.get("workflow", "")
        
        wf_pattern = rf"####\s+\d+\.\d+\s+{re.escape(wf_name)}"
        wf_match = re.search(wf_pattern, content)
        if not wf_match:
            return FixPosition.not_found()
        
        section_start = wf_match.start()
        next_section = re.search(r'\n####\s+\d+\.\d+', content[wf_match.end():])
        section_end = wf_match.end() + next_section.start() if next_section else len(content)
        section = content[section_start:section_end]
        
        table_pattern = r'\|\s*序号\s*\|\s*Job名称\s*\|'
        table_match = re.search(table_pattern, section)
        
        if table_match:
            table_end = section.find('\n\n', table_match.end())
            if table_end < 0:
                table_end = len(section)
            insert_pos = section_start + table_end
            return FixPosition(start=insert_pos, end=insert_pos, file="report")
        
        return FixPosition.not_found()
    
    def _resolve_job_row(self, anchor: Dict, content: str) -> FixPosition:
        """定位 Job 表格行（用于删除）"""
        wf_name = anchor.get("workflow", "")
        job_name = anchor.get("job", "")
        
        wf_pos = self._resolve_workflow_section({"type": "workflow_section", "workflow": wf_name}, content)
        if not wf_pos.is_valid:
            return FixPosition.not_found()
        
        section = content[wf_pos.start:wf_pos.end]
        
        pattern = rf'\|\s*\d+\s*\|\s*{re.escape(job_name)}\s*\|'
        match = re.search(pattern, section)
        
        if match:
            line_start = section.rfind('\n', 0, match.start()) + 1
            line_end = section.find('\n', match.end())
            if line_end < 0:
                line_end = len(section)
            
            return FixPosition(
                start=wf_pos.start + line_start,
                end=wf_pos.start + line_end,
                file="report"
            )
        
        return FixPosition.not_found()
    
    def _resolve_stage_section(self, anchor: Dict, content: str) -> FixPosition:
        """定位阶段章节（用于插入工作流）"""
        stage = anchor.get("stage", "")
        
        stage_pattern = rf"##\s+阶段.*?{re.escape(stage)}" if stage else r"##\s+阶段"
        stage_match = re.search(stage_pattern, content)
        
        if stage_match:
            next_stage = re.search(r'\n##\s+阶段', content[stage_match.end():])
            if next_stage:
                end = stage_match.end() + next_stage.start()
            else:
                next_section = re.search(r'\n##\s+', content[stage_match.end():])
                end = stage_match.end() + next_section.start() if next_section else len(content)
            return FixPosition(start=end, end=end, file="report")
        
        appendix = re.search(r'##\s+附录', content)
        if appendix:
            return FixPosition(start=appendix.start(), end=appendix.start(), file="report")
        
        return FixPosition(start=len(content), end=len(content), file="report")


class FixExecutor:
    """修复执行器 - 执行修复操作"""
    
    def __init__(self):
        self.anchor_resolver = AnchorResolver()
    
    def execute(self, content: str, instruction: FixInstruction, position: FixPosition) -> str:
        """执行单个修复"""
        if instruction.action == "insert":
            return content[:position.start] + instruction.content + content[position.start:]
        elif instruction.action == "delete":
            return content[:position.start] + content[position.end:]
        elif instruction.action == "replace":
            return content[:position.start] + instruction.content + content[position.end:]
        return content
    
    def execute_batch(self, content: str, instructions: List[FixInstruction]) -> Tuple[str, List[FixInstruction]]:
        """批量执行修复（从后向前）"""
        if not instructions:
            return content, []
        
        positions = self.anchor_resolver.resolve_batch(
            [i.anchor for i in instructions], content
        )
        
        result = content
        executed = []
        
        for (pos, anchor), inst in zip(positions, instructions):
            result = self.execute(result, inst, pos)
            executed.append(inst)
        
        return result, executed


class MultiFileSync:
    """多文件同步器 - 同步更新 architecture.json 和 summary.json"""
    
    def sync(self, fix_type: str, sync_data: Dict, 
             arch: Dict, summary: Dict) -> Tuple[Dict, Dict]:
        """同步更新"""
        arch = arch.copy() if arch else {}
        summary = summary.copy() if summary else {}
        
        if fix_type == "trigger_missing":
            arch = self._add_trigger_node(arch, sync_data)
        elif fix_type == "trigger_fabricated":
            arch = self._remove_trigger_node(arch, sync_data)
        elif fix_type == "job_missing":
            arch = self._add_job_node(arch, sync_data)
        elif fix_type == "job_fake":
            arch = self._remove_job_node(arch, sync_data)
        elif fix_type == "workflow_missing":
            arch = self._add_workflow_node(arch, sync_data)
        elif fix_type == "workflow_fake":
            arch = self._remove_workflow_node(arch, sync_data)
        
        summary = self._update_summary(arch, summary)
        return arch, summary
    
    def _add_trigger_node(self, arch: Dict, sync_data: Dict) -> Dict:
        """添加触发节点"""
        trigger = sync_data.get("entity", "")
        if not trigger:
            return arch
        
        layers = arch.get("layers", [])
        trigger_layer = None
        
        for layer in layers:
            if "触发" in layer.get("name", "") or "入口" in layer.get("name", ""):
                trigger_layer = layer
                break
        
        if trigger_layer:
            existing = {n.get("label", "").split(" ")[0] for n in trigger_layer.get("nodes", [])}
            if trigger not in existing:
                trigger_layer.setdefault("nodes", []).append({
                    "id": f"node-trigger-{trigger}",
                    "label": trigger,
                    "description": f"{trigger} 事件触发",
                })
        
        return arch
    
    def _remove_trigger_node(self, arch: Dict, sync_data: Dict) -> Dict:
        """移除触发节点"""
        trigger = sync_data.get("entity", "")
        if not trigger:
            return arch
        
        for layer in arch.get("layers", []):
            if "触发" in layer.get("name", "") or "入口" in layer.get("name", ""):
                nodes = layer.get("nodes", [])
                layer["nodes"] = [n for n in nodes if not n.get("label", "").startswith(trigger)]
        
        return arch
    
    def _add_job_node(self, arch: Dict, sync_data: Dict) -> Dict:
        """添加 Job 节点"""
        return arch
    
    def _remove_job_node(self, arch: Dict, sync_data: Dict) -> Dict:
        """移除 Job 节点"""
        return arch
    
    def _add_workflow_node(self, arch: Dict, sync_data: Dict) -> Dict:
        """添加工作流节点"""
        wf_name = sync_data.get("entity", "")
        if not wf_name:
            return arch
        
        layers = arch.get("layers", [])
        if layers:
            last_layer = layers[-1]
            existing = {n.get("label", "") for n in last_layer.get("nodes", [])}
            if wf_name not in existing:
                last_layer.setdefault("nodes", []).append({
                    "id": f"node-{wf_name}",
                    "label": wf_name,
                    "description": f"工作流 {wf_name}",
                })
        
        return arch
    
    def _remove_workflow_node(self, arch: Dict, sync_data: Dict) -> Dict:
        """移除工作流节点"""
        wf_name = sync_data.get("entity", "")
        if not wf_name:
            return arch
        
        for layer in arch.get("layers", []):
            nodes = layer.get("nodes", [])
            layer["nodes"] = [n for n in nodes if n.get("label", "") != wf_name]
        
        return arch
    
    def _update_summary(self, arch: Dict, summary: Dict) -> Dict:
        """更新统计摘要"""
        layers = arch.get("layers", [])
        workflow_count = 0
        
        for layer in layers:
            for node in layer.get("nodes", []):
                label = node.get("label", "")
                if label.endswith(".yml"):
                    workflow_count += 1
        
        if workflow_count > 0:
            summary["workflow_count"] = workflow_count
        
        return summary