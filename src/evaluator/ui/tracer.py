# LangSmith 追踪器

import os
from typing import Optional, Any
from contextlib import contextmanager


class LangSmithTracer:
    def __init__(self):
        self.enabled = os.getenv("LANGCHAIN_TRACING_V2", "").lower() == "true"
        self.project = os.getenv("LANGCHAIN_PROJECT", "ci-evaluator")
        self.current_run = None
        
        if self.enabled:
            try:
                from langsmith.run_trees import RunTree
                self._run_tree_class = RunTree
            except ImportError:
                self.enabled = False
    
    def _create_run(self, name: str, inputs: dict, run_type: str = "chain") -> Optional[Any]:
        if not self.enabled:
            return None
        
        try:
            from langsmith.run_trees import RunTree
            return RunTree(
                name=name,
                inputs=inputs,
                run_type=run_type,
                project_name=self.project,
            )
        except Exception:
            return None
    
    def _end_run(self, run: Any, outputs: dict = None, error: str = None):
        if not run:
            return
        
        try:
            if error:
                run.end(error=error)
            else:
                run.end(outputs=outputs or {})
        except Exception:
            pass
    
    @contextmanager
    def trace_node(self, node_name: str, inputs: dict = None):
        run = self._create_run(node_name, inputs or {}, "chain")
        self.current_run = run
        
        try:
            result = yield run
            self._end_run(run, outputs={"result": result})
        except Exception as e:
            self._end_run(run, error=str(e))
            raise
        finally:
            self.current_run = None
    
    @contextmanager
    def trace_llm(self, prompt: str, model: str = None):
        run = self._create_run(
            f"LLM: {model or 'default'}",
            {"prompt_length": len(prompt)},
            "llm"
        )
        
        try:
            result = yield run
            self._end_run(run, outputs={"response_length": len(str(result)), "model": model})
        except Exception as e:
            self._end_run(run, error=str(e))
            raise
    
    def log_event(self, name: str, data: dict):
        if not self.enabled or not self.current_run:
            return
        
        try:
            self.current_run.add_event({
                "name": name,
                "data": data,
            })
        except Exception:
            pass
    
    def update_run(self, run_id: str, status: str, metadata: dict = None):
        pass


_tracer_instance: Optional[LangSmithTracer] = None


def get_tracer() -> LangSmithTracer:
    global _tracer_instance
    if _tracer_instance is None:
        _tracer_instance = LangSmithTracer()
    return _tracer_instance


def init_tracer() -> LangSmithTracer:
    global _tracer_instance
    _tracer_instance = LangSmithTracer()
    return _tracer_instance
