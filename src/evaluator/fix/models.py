"""修复模块数据模型"""
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any


@dataclass
class FixPosition:
    """修复位置"""
    start: int
    end: int
    file: str = ""
    
    @classmethod
    def not_found(cls) -> 'FixPosition':
        return cls(start=-1, end=-1, file="")
    
    @property
    def is_valid(self) -> bool:
        return self.start >= 0


@dataclass
class FixInstruction:
    """修复指令"""
    type: str
    severity: str
    anchor: Dict[str, Any]
    action: str
    content: str
    target_files: List[str]
    sync_data: Optional[Dict] = None


@dataclass
class FixResult:
    """修复结果"""
    report: str
    architecture: Dict
    summary: Dict
    fix_log: List[Dict]
    success: bool
    message: str = ""