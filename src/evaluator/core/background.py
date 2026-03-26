"""后台任务管理器 - 异步执行智能Agent

主流程（同步）完成后，自动触发后台任务执行智能Agent链：
reporter完成 → storage → recommendation → reflection

结果保存到 storage_dir/insights.json
"""
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Dict, Any, Optional, Callable
from pathlib import Path
import json
import time
import threading


class InsightsData:
    """智能分析结果数据结构"""
    
    def __init__(
        self,
        similar_projects: list = None,
        comparison_suggestions: list = None,
        recommendations: list = None,
        quick_wins: list = None,
        reflection_result: dict = None,
        generated_at: str = None,
    ):
        self.similar_projects = similar_projects or []
        self.comparison_suggestions = comparison_suggestions or []
        self.recommendations = recommendations or []
        self.quick_wins = quick_wins or []
        self.reflection_result = reflection_result or {}
        self.generated_at = generated_at or time.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "similar_projects": self.similar_projects,
            "comparison_suggestions": self.comparison_suggestions,
            "recommendations": self.recommendations,
            "quick_wins": self.quick_wins,
            "reflection_result": self.reflection_result,
            "generated_at": self.generated_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InsightsData":
        return cls(
            similar_projects=data.get("similar_projects", []),
            comparison_suggestions=data.get("comparison_suggestions", []),
            recommendations=data.get("recommendations", []),
            quick_wins=data.get("quick_wins", []),
            reflection_result=data.get("reflection_result"),
            generated_at=data.get("generated_at"),
        )


class TaskStatus:
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class BackgroundTask:
    """单个后台任务"""
    
    def __init__(
        self,
        project_name: str,
        future: Future,
        submitted_at: float = None,
    ):
        self.project_name = project_name
        self.future = future
        self.submitted_at = submitted_at or time.time()
        self.status = TaskStatus.PENDING
        self.error: Optional[str] = None
        self.result: Optional[Dict[str, Any]] = None


class BackgroundTasks:
    """后台任务管理器（单例）
    
    使用方式:
        from evaluator.core.background import background
        
        # 提交智能分析任务
        background.submit_intelligence(state)
        
        # 检查任务状态
        status = background.get_status(project_name)
        
        # 加载分析结果
        insights = background.load_insights(project_name, storage_dir)
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        try:
            from evaluator.config import config
            max_workers = config.max_background_workers
        except ImportError:
            max_workers = 1
        
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="intelligence_")
        self.tasks: Dict[str, BackgroundTask] = {}
        self._lock = threading.Lock()
        self._initialized = True
        
        self._register_interrupt_callback()
    
    def _register_interrupt_callback(self):
        """注册中断回调，用于取消后台任务"""
        try:
            from evaluator.core.interrupt import interrupt_controller
            interrupt_controller.register_callback(self.cancel_all)
        except ImportError:
            pass
    
    def cancel_all(self):
        """取消所有后台任务"""
        with self._lock:
            for task_name, task in list(self.tasks.items()):
                try:
                    if not task.future.done():
                        cancelled = task.future.cancel()
                        if cancelled:
                            task.status = TaskStatus.FAILED
                            task.error = "Cancelled by user"
                except Exception:
                    pass
            self.tasks.clear()
    
    def submit_intelligence(
        self,
        state: Dict[str, Any],
        on_complete: Optional[Callable[[Dict[str, Any]], None]] = None,
        parent_run_id: Optional[str] = None,
    ) -> BackgroundTask:
        """提交智能分析任务
        
        Args:
            state: 当前状态（必须包含project_name, storage_dir）
            on_complete: 完成回调函数
            parent_run_id: 父 trace run_id，用于关联主流程 trace
        
        Returns:
            BackgroundTask: 任务对象
        """
        project_name = state.get("project_name", "unknown")
        
        with self._lock:
            if project_name in self.tasks:
                existing = self.tasks[project_name]
                if existing.status == TaskStatus.RUNNING:
                    return existing
            
            future = self.executor.submit(
                self._run_intelligence,
                state.copy(),
                on_complete,
                parent_run_id,
            )
            
            task = BackgroundTask(
                project_name=project_name,
                future=future,
            )
            task.status = TaskStatus.RUNNING
            
            self.tasks[project_name] = task
            
            future.add_done_callback(
                lambda f: self._on_task_done(project_name, f)
            )
            
            return task
    
    def _run_intelligence(
        self,
        state: Dict[str, Any],
        on_complete: Optional[Callable[[Dict[str, Any]], None]] = None,
        parent_run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """执行智能Agent链
        
        Args:
            state: 当前状态
            on_complete: 完成回调函数
            parent_run_id: 父 trace run_id，用于关联主流程 trace
        """
        from evaluator.agents import IntelligencePipeline
        
        llm = state.get("llm")
        
        has_langsmith = False
        trace_func = None
        try:
            from langsmith import trace
            has_langsmith = True
            trace_func = trace
        except ImportError:
            pass
        
        try:
            if has_langsmith and trace_func and parent_run_id:
                with trace_func(
                    name="intelligence_pipeline",
                    run_type="chain",
                    parent_run_id=parent_run_id,
                ):
                    pipeline = IntelligencePipeline(llm=llm)
                    current_state = pipeline.run(state)
            else:
                pipeline = IntelligencePipeline(llm=llm)
                current_state = pipeline.run(state)
            
            self._save_insights(current_state)
            
            if on_complete:
                try:
                    on_complete(current_state)
                except Exception as e:
                    print(f"回调执行失败: {e}")
            
            return current_state
            
        except Exception as e:
            print(f"智能Agent执行失败: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def _on_task_done(self, project_name: str, future: Future):
        """任务完成回调"""
        with self._lock:
            task = self.tasks.get(project_name)
            if task:
                try:
                    task.result = future.result()
                    task.status = TaskStatus.COMPLETED
                except Exception as e:
                    task.status = TaskStatus.FAILED
                    task.error = str(e)
    
    def _save_insights(self, state: Dict[str, Any]):
        """保存智能分析结果"""
        storage_dir = state.get("storage_dir")
        if not storage_dir:
            return
        
        insights_data = InsightsData(
            similar_projects=state.get("similar_projects", []),
            comparison_suggestions=state.get("comparison_suggestions", []),
            recommendations=state.get("recommendations", []),
            quick_wins=state.get("quick_wins", []),
            reflection_result=state.get("reflection_result"),
        )
        
        insights_path = Path(storage_dir) / "insights.json"
        insights_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(insights_path, "w", encoding="utf-8") as f:
            json.dump(insights_data.to_dict(), f, ensure_ascii=False, indent=2)
        
        print(f"  [Background] 智能分析结果已保存: {insights_path}")
    
    def get_status(self, project_name: str) -> Optional[Dict[str, Any]]:
        """获取任务状态
        
        Returns:
            {
                "status": str,  # pending/running/completed/failed
                "submitted_at": float,
                "error": str,  # 如果失败
            }
        """
        with self._lock:
            task = self.tasks.get(project_name)
            if task:
                return {
                    "status": task.status,
                    "submitted_at": task.submitted_at,
                    "error": task.error,
                }
            return None
    
    def is_completed(self, project_name: str) -> bool:
        """检查任务是否完成"""
        status = self.get_status(project_name)
        return status is not None and status["status"] == TaskStatus.COMPLETED
    
    def is_running(self, project_name: str) -> bool:
        """检查任务是否运行中"""
        status = self.get_status(project_name)
        return status is not None and status["status"] == TaskStatus.RUNNING
    
    def load_insights(
        self,
        project_name: str,
        storage_dir: Optional[str] = None,
    ) -> Optional[InsightsData]:
        """加载智能分析结果
        
        Args:
            project_name: 项目名称
            storage_dir: 存储目录（可选，不传则自动查找）
        
        Returns:
            InsightsData 或 None
        """
        if storage_dir:
            insights_path = Path(storage_dir) / "insights.json"
        else:
            insights_path = self._find_insights_path(project_name)
        
        if not insights_path or not insights_path.exists():
            return None
        
        try:
            with open(insights_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return InsightsData.from_dict(data)
        except Exception as e:
            print(f"加载智能分析结果失败: {e}")
            return None
    
    def _find_insights_path(self, project_name: str) -> Optional[Path]:
        """查找项目的智能分析结果路径"""
        from storage import StorageManager
        storage = StorageManager()
        
        version_dir = storage.get_latest_version_dir(project_name)
        if not version_dir:
            return None
        
        insights_path = version_dir / "insights.json"
        if insights_path.exists():
            return insights_path
        
        return None
    
    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """获取所有任务状态"""
        with self._lock:
            return {
                name: {
                    "status": task.status,
                    "submitted_at": task.submitted_at,
                    "error": task.error,
                }
                for name, task in self.tasks.items()
            }
    
    def clear_completed(self):
        """清理已完成的任务"""
        with self._lock:
            completed = [
                name for name, task in self.tasks.items()
                if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)
            ]
            for name in completed:
                del self.tasks[name]


# 全局单例
background = BackgroundTasks()
