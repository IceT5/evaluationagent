"""全局中断控制器

支持用户在任务执行过程中通过 Ctrl+C 中断任务。

使用方式:
    from evaluator.core.interrupt import interrupt_controller, InterruptException

    # 触发中断
    interrupt_controller.interrupt("用户按下 Ctrl+C")

    # 检查中断（在 Agent 执行前）
    interrupt_controller.check()

    # 注册清理回调（如关闭 HTTP 连接）
    interrupt_controller.register_callback(my_cleanup_fn)
"""
import threading
import time
from typing import Callable, List


class InterruptException(Exception):
    """中断异常"""
    pass


class InterruptController:
    """全局中断控制器（单例）

    职责:
    - 管理全局中断状态
    - 提供中断触发和检查接口
    - 执行清理回调（关闭连接、取消任务等）
    - 追踪执行进度（用于中断后显示）
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

        self._interrupted = False
        self._reason = ""
        self._callbacks: List[Callable] = []
        self._callback_lock = threading.Lock()
        self._current_node = ""
        self._start_time = 0.0
        self._completed_nodes: List[str] = []
        self._initialized = True

    def interrupt(self, reason: str = "用户中断"):
        """触发中断

        设置中断标志，并执行所有清理回调。
        """
        if self._interrupted:
            return

        self._interrupted = True
        self._reason = reason
        self._run_callbacks()

    def check(self):
        """检查中断状态

        如果已中断，抛出 InterruptException。
        """
        if self._interrupted:
            raise InterruptException(self._reason)

    def reset(self):
        """重置中断状态

        在新任务开始时调用。
        """
        self._interrupted = False
        self._reason = ""
        self._current_node = ""
        self._start_time = time.time()
        self._completed_nodes = []

    def register_callback(self, fn: Callable):
        """注册清理回调

        当中断触发时，会调用所有注册的回调函数。
        用于关闭连接、释放资源等。
        """
        with self._callback_lock:
            if fn not in self._callbacks:
                self._callbacks.append(fn)

    def unregister_callback(self, fn: Callable):
        """取消注册清理回调"""
        with self._callback_lock:
            if fn in self._callbacks:
                self._callbacks.remove(fn)

    def set_current_node(self, name: str):
        """设置当前执行的节点"""
        self._current_node = name

    def mark_node_completed(self, name: str):
        """标记节点已完成"""
        if name and name not in self._completed_nodes:
            self._completed_nodes.append(name)

    def get_elapsed_time(self) -> float:
        """获取已运行时间（秒）"""
        if self._start_time == 0:
            return 0.0
        return time.time() - self._start_time

    def get_interrupt_summary(self) -> dict:
        """获取中断摘要（用于显示）"""
        return {
            "reason": self._reason,
            "elapsed_time": self.get_elapsed_time(),
            "current_node": self._current_node,
            "completed_nodes": list(self._completed_nodes),
        }

    def is_interrupted(self) -> bool:
        """检查是否已中断"""
        return self._interrupted

    def _run_callbacks(self):
        """执行所有清理回调"""
        with self._callback_lock:
            callbacks = list(self._callbacks)

        for fn in callbacks:
            try:
                fn()
            except Exception:
                pass


interrupt_controller = InterruptController()
