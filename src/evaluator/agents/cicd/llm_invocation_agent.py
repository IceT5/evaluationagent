"""LLM 调用 Agent - 执行 LLM 分析"""
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, Future

try:
    from evaluator.llm import LLMClient
    HAS_LLM = True
except ImportError:
    HAS_LLM = False
    LLMClient = None

try:
    from evaluator.config import config
    HAS_CONFIG = True
except ImportError:
    HAS_CONFIG = False
    config = None

from .state import CICDState
from evaluator.agents.base_agent import BaseAgent, AgentMeta

# 导入中断控制器
try:
    from evaluator.core.interrupt import interrupt_controller, InterruptException
    HAS_INTERRUPT = True
except ImportError:
    interrupt_controller = None
    InterruptException = Exception
    HAS_INTERRUPT = False


def _get_concurrent_calls() -> int:
    return config.max_concurrent_llm_calls if config and HAS_CONFIG else 4

def _get_llm_timeout() -> int:
    return config.llm_call_timeout if config and HAS_CONFIG else 600


def validate_round_response(round_num: int, response: str) -> dict:
    """验证单轮响应
    
    复用 ReviewerAgent.validate_llm_response 的部分逻辑
    """
    result = {"valid": True, "warnings": []}
    
    if not response or len(response.strip()) < 20:
        result["valid"] = False
        result["warnings"].append(f"Round {round_num}: 响应过短 ({len(response) if response else 0} 字符)")
        return result
    
    expected_markers = {
        1: ["项目概述", "##"],
        2: ["阶段划分", "##"],
        3: ["scores", "{"],
        4: ["strengths", "{"],
        5: ["weaknesses", "{"],
        6: ["recommendations", "{"],
        7: ["附录", "├", "│"],
        8: ["ARCHITECTURE_JSON", "<!--"],
        9: ["架构图", "┌", "│"],
    }
    
    markers = expected_markers.get(round_num, [])
    found = [m for m in markers if m in response]
    
    if markers and len(found) < len(markers) // 2:
        result["warnings"].append(f"Round {round_num}: 缺少预期标记 {set(markers) - set(found)}")
    
    return result


def parse_multi_round_responses(responses: List[str]) -> dict:
    """从多轮响应中直接提取结构化数据
    
    Returns:
        {
            "overview": str,
            "stage_division": str,
            "architecture_diagram": str,
            "scores": dict,
            "strengths": list,
            "weaknesses": list,
            "recommendations": list,
            "call_tree": str,
            "architecture_json": dict,
            "merged_response": str
        }
    """
    import json
    import re
    
    result = {
        "overview": "",
        "stage_division": "",
        "architecture_diagram": "",
        "scores": {},
        "strengths": [],
        "weaknesses": [],
        "recommendations": [],
        "call_tree": "",
        "architecture_json": {},
        "merged_response": "",
        "parse_warnings": []
    }
    
    for i, resp in enumerate(responses):
        if i == 0:
            continue
        
        resp = resp.strip()
        
        validation = validate_round_response(i, resp)
        if validation["warnings"]:
            result["parse_warnings"].extend(validation["warnings"])
            for w in validation["warnings"]:
                print(f"  [WARN] {w}")
        
        print(f"  [Parse] Round {i}: {len(resp)} 字符")
        
        if i == 1:
            # Round 1: 项目概述
            result["overview"] = resp
        
        elif i == 2:
            # Round 2: 阶段划分
            result["stage_division"] = resp
        
        elif i == 3:
            # Round 3: 架构评分 JSON
            data = extract_json_from_response(resp, i)
            result["scores"] = data.get("scores", {})
            if not result["scores"]:
                result["parse_warnings"].append(f"Round {i}: scores 提取失败")
        
        elif i == 4:
            # Round 4: 优势模式 JSON
            data = extract_json_from_response(resp, i)
            result["strengths"] = data.get("strengths", [])
            if not result["strengths"]:
                result["parse_warnings"].append(f"Round {i}: strengths 提取失败")
        
        elif i == 5:
            # Round 5: 问题 JSON
            data = extract_json_from_response(resp, i)
            result["weaknesses"] = data.get("weaknesses", [])
            if not result["weaknesses"]:
                result["parse_warnings"].append(f"Round {i}: weaknesses 提取失败")
        
        elif i == 6:
            # Round 6: 建议 JSON
            data = extract_json_from_response(resp, i)
            result["recommendations"] = data.get("recommendations", [])
            if not result["recommendations"]:
                result["parse_warnings"].append(f"Round {i}: recommendations 提取失败")
        
        elif i == 7:
            # Round 7: 调用关系树 (附录)
            result["call_tree"] = resp
        
        elif i == 8:
            # Round 8: 架构 JSON 数据
            result["architecture_json"] = extract_architecture_json(resp)
        
        elif i == 9:
            # Round 9: ASCII 架构图
            result["architecture_diagram"] = resp
    
    required = ["overview", "stage_division"]
    for field in required:
        if not result.get(field):
            result["parse_warnings"].append(f"必要字段 '{field}' 为空")
            print(f"  [ERROR] 必要字段 '{field}' 为空")
    
    result["merged_response"] = merge_to_markdown(result)
    
    return result


def extract_json_from_response(response: str, round_num: int) -> dict:
    """从响应中提取 JSON（健壮版）"""
    import json
    import re
    
    match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError as e:
            print(f"  [WARN] Round {round_num}: JSON 解析失败 (```json): {e}")
    
    start = response.find('{')
    end = response.rfind('}')
    if start != -1 and end != -1:
        try:
            return json.loads(response[start:end+1])
        except json.JSONDecodeError as e:
            print(f"  [WARN] Round {round_num}: JSON 解析失败 ({{...}}): {e}")
    
    result = extract_from_markdown_table(response, round_num)
    if result:
        print(f"  [INFO] Round {round_num}: 使用 Markdown 表格回退")
        return result
    
    print(f"  [WARN] Round {round_num}: 无法提取数据，使用默认值")
    return {}


def extract_from_markdown_table(response: str, round_num: int) -> dict:
    """回退：从 Markdown 表格或列表提取数据"""
    import re
    
    if round_num == 4:
        pattern = r'\|\s*(\w+)\s*\|\s*(\d+)\s*\|'
        matches = re.findall(pattern, response)
        if matches:
            scores = {}
            for dimension, score in matches:
                if dimension in ["architecture_design", "best_practices", "security", "maintainability", "scalability"]:
                    scores[dimension] = {"score": int(score), "rationale": ""}
            if scores:
                return {"scores": scores}
    
    elif round_num == 5:
        strengths = []
        pattern = r'####\s*✅\s*模式[_\s]*\d*[:：]\s*(.+?)\n\n([\s\S]*?)(?=####\s*✅|####\s*⚠️|##|$)'
        matches = re.findall(pattern, response)
        for title, desc in matches:
            if title.strip():
                strengths.append({
                    "title": title.strip(),
                    "description": desc.strip()[:200],
                    "evidence": ""
                })
        if not strengths:
            pattern2 = r'####\s*✅\s*(.+?)\n([\s\S]*?)(?=####|$)'
            matches2 = re.findall(pattern2, response)
            for title, desc in matches2:
                if title.strip():
                    strengths.append({
                        "title": title.strip(),
                        "description": desc.strip()[:200],
                        "evidence": ""
                    })
        if strengths:
            return {"strengths": strengths}
    
    elif round_num == 6:
        weaknesses = []
        pattern = r'####\s*⚠️\s*(问题|反模式)[_\s]*\d*[:：]\s*(.+?)\n\n([\s\S]*?)(?=####\s*⚠️|####\s*建议|##|$)'
        matches = re.findall(pattern, response)
        for ptype, title, desc in matches:
            if title.strip():
                weaknesses.append({
                    "title": title.strip(),
                    "description": desc.strip()[:200],
                    "impact": "",
                    "suggestion": ""
                })
        if not weaknesses:
            pattern2 = r'####\s*⚠️\s*(.+?)\n([\s\S]*?)(?=####|$)'
            matches2 = re.findall(pattern2, response)
            for title, desc in matches2:
                if title.strip():
                    weaknesses.append({
                        "title": title.strip(),
                        "description": desc.strip()[:200],
                        "impact": "",
                        "suggestion": ""
                    })
        if weaknesses:
            return {"weaknesses": weaknesses}
    
    elif round_num == 7:
        recommendations = []
        pattern = r'\|\s*(P\d|high|medium|low|🔴|🟡|🟢)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|'
        matches = re.findall(pattern, response)
        priority_map = {"P0": "high", "P1": "medium", "P2": "low", "🔴": "high", "🟡": "medium", "🟢": "low"}
        for priority, content, benefit in matches:
            content = content.strip()
            benefit = benefit.strip()
            if content and content != "建议":
                recommendations.append({
                    "priority": priority_map.get(priority, priority.lower()),
                    "content": content,
                    "expected_benefit": benefit
                })
        if recommendations:
            return {"recommendations": recommendations}
    
    return {}


def extract_architecture_json(response: str) -> dict:
    """从响应中提取 ARCHITECTURE_JSON"""
    import json
    import re
    
    match = re.search(r'<!--\s*ARCHITECTURE_JSON\s*([\s\S]*?)\s*ARCHITECTURE_JSON\s*-->', response)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    
    return {}


def merge_to_markdown(data: dict) -> str:
    """将结构化数据合并为 Markdown"""
    import json
    
    parts = []
    
    if data["overview"]:
        parts.append(data["overview"])
    
    if data["stage_division"]:
        parts.append(data["stage_division"])
    
    if data["architecture_diagram"]:
        parts.append(data["architecture_diagram"])
    
    findings_parts = ["## 关键发现和建议"]
    
    if data["scores"]:
        findings_parts.append("\n### 架构特点总结\n")
        findings_parts.append(_format_scores_table(data["scores"]))
    
    if data["strengths"]:
        findings_parts.append("\n### 优势架构模式\n")
        findings_parts.append(_format_strengths(data["strengths"]))
    
    if data["weaknesses"]:
        findings_parts.append("\n### 架构问题\n")
        findings_parts.append(_format_weaknesses(data["weaknesses"]))
    
    if data["recommendations"]:
        findings_parts.append("\n### 改进建议\n")
        findings_parts.append(_format_recommendations(data["recommendations"]))
    
    parts.append("\n".join(findings_parts))
    
    if data["call_tree"]:
        parts.append(data["call_tree"])
    
    if data["architecture_json"]:
        parts.append("<!-- ARCHITECTURE_JSON\n" + json.dumps(data["architecture_json"], ensure_ascii=False, indent=2) + "\nARCHITECTURE_JSON -->")
    
    return "\n\n---\n\n".join(parts)


def _format_scores_table(scores: dict) -> str:
    """将 scores 格式化为 Markdown 表格"""
    lines = []
    lines.append("| 维度 | 评分 | 说明 |")
    lines.append("|------|------|------|")
    for dim, info in scores.items():
        score = info.get("score", "-")
        rationale = info.get("rationale", "")
        dim_cn = {
            "architecture_design": "架构设计",
            "best_practices": "最佳实践",
            "security": "安全性",
            "maintainability": "可维护性",
            "scalability": "可扩展性"
        }.get(dim, dim)
        lines.append(f"| {dim_cn} | {score} | {rationale} |")
    return "\n".join(lines)


def _format_strengths(strengths: list) -> str:
    """将 strengths 格式化为 Markdown"""
    lines = []
    for i, s in enumerate(strengths, 1):
        title = s.get("title", "")
        desc = s.get("description", "")
        lines.append(f"#### ✅ 模式 {i}: {title}")
        lines.append(desc)
        lines.append("")
    return "\n".join(lines)


def _format_weaknesses(weaknesses: list) -> str:
    """将 weaknesses 格式化为 Markdown"""
    lines = []
    for i, w in enumerate(weaknesses, 1):
        title = w.get("title", "")
        desc = w.get("description", "")
        suggestion = w.get("suggestion", "")
        lines.append(f"#### ⚠️ 问题 {i}: {title}")
        lines.append(desc)
        if suggestion:
            lines.append(f"**建议**: {suggestion}")
        lines.append("")
    return "\n".join(lines)


def _format_recommendations(recommendations: list) -> str:
    """将 recommendations 格式化为 Markdown"""
    lines = []
    lines.append("| 优先级 | 建议 | 预期效果 |")
    lines.append("|--------|------|----------|")
    priority_map = {"high": "🔴 高", "medium": "🟡 中", "low": "🟢 低"}
    for r in recommendations:
        priority = priority_map.get(r.get("priority", ""), r.get("priority", ""))
        content = r.get("content", "")
        benefit = r.get("expected_benefit", "")
        lines.append(f"| {priority} | {content} | {benefit} |")
    return "\n".join(lines)

def _get_llm_max_retries() -> int:
    return config.llm_max_retries if config and HAS_CONFIG else 5

def _get_retry_delay() -> float:
    return config.llm_retry_base_delay if config and HAS_CONFIG else 1.0


class LLMInvocationAgent(BaseAgent):
    """LLM 调用 Agent
    
    职责：根据策略执行 LLM 调用（单次/并发）
    输入：CICDState.prompts, strategy
    输出：CICDState.llm_responses
    """
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="LLMInvocationAgent",
            description="执行 LLM 调用进行分析",
            category="analysis",
            inputs=["prompts", "strategy", "ci_data"],
            outputs=["llm_responses"],
            dependencies=["AnalysisPlanningAgent"],
        )
    
    def __init__(self, llm: Optional["LLMClient"] = None):
        super().__init__()
        self.llm = llm
    
    def run(self, state: CICDState) -> CICDState:
        """执行 LLM 调用"""
        strategy = state.get("strategy")
        prompts = state.get("prompts", [])
        ci_data = state.get("ci_data", {})
        storage_dir = state.get("storage_dir")
        prompt_strategy = state.get("prompt_strategy", "")
        
        if strategy == "skip":
            return {
                **state,
                "llm_responses": [],
                "merged_response": "",
            }
        
        if self.llm is None and HAS_LLM:
            from evaluator.llm import get_default_client
            self.llm = get_default_client()
        
        output_dir = Path(storage_dir) if storage_dir else Path(state.get("project_path", "."))
        
        if strategy == "single":
            responses = self._single_call(prompts)
        elif prompt_strategy == "multi_round":
            responses = self._multi_round_call(state)
        else:
            responses = self._parallel_calls(prompts)
        
        merged_response = self._merge_responses(responses, ci_data, state.get("ci_data_path") or "")
        
        response_path = output_dir / "llm_response.md"
        response_path.write_text(merged_response, encoding="utf-8")
        
        return {
            **state,
            "llm_responses": responses,
            "merged_response": merged_response,
            "retry_count": state.get("retry_count", 0),
        }
    
    def _multi_round_call(self, state: CICDState) -> List[Dict[str, Any]]:
        """多轮对话调用
        
        执行步骤：
        1. 从 state 获取 main_rounds 和 main_system_prompt
        2. 并发执行：main 多轮对话 + batch prompts
        3. 返回合并的 responses
        """
        main_rounds = state.get("main_rounds", [])
        main_system_prompt = state.get("main_system_prompt", "")
        batch_files = state.get("batch_files", [])
        
        results = []
        
        if main_rounds:
            main_response = self._execute_multi_round(main_rounds, main_system_prompt)
            results.append(main_response)
            print(f"  [Multi-Round] main 分析完成")
        
        if batch_files:
            batch_responses = self._parallel_calls(batch_files)
            results.extend(batch_responses)
            print(f"  [LLM] batch 分析完成 ({len(batch_responses)} 个)")
        
        if not results:
            print(f"  [LLM] 警告：没有执行任何 LLM 调用")
        
        return results
    
    def _execute_multi_round(
        self,
        rounds: List[str],
        system_prompt: str = ""
    ) -> Dict[str, Any]:
        """执行多轮对话"""
        print(f"  [Multi-Round] 开始 {len(rounds)} 轮对话...")
        
        # 检查中断
        if HAS_INTERRUPT and interrupt_controller and interrupt_controller.is_interrupted():
            raise InterruptException("用户中断")
        
        try:
            timeout = config.llm_call_timeout if config and HAS_CONFIG else 180
            responses, durations = self.llm.chat_multi_round(
                rounds,
                system_prompt or None,
                timeout=timeout
            )
            
            parsed = parse_multi_round_responses(responses)
            
            print(f"  [Multi-Round] 完成")
            for i, (resp, dur) in enumerate(zip(responses, durations)):
                print(f"    Round {i}: {dur}, {len(resp)} 字符")
            
            return {
                "success": True,
                "prompt_path": "main_multi_round",
                "response": parsed["merged_response"],
                "parsed_data": parsed,
                "round_responses": responses,
                "round_durations": durations,
                "index": 0,
            }
        except InterruptException:
            raise  # 中断异常直接抛出
        except Exception as e:
            print(f"  [Multi-Round] 失败: {e}")
            return {
                "success": False,
                "prompt_path": "main_multi_round",
                "error": str(e),
                "index": 0,
            }
    
    def _single_call(self, prompts: List[str]) -> List[Dict[str, Any]]:
        """单次 LLM 调用"""
        if not prompts:
            return []
        
        # 检查中断
        if HAS_INTERRUPT and interrupt_controller and interrupt_controller.is_interrupted():
            raise InterruptException("用户中断")
        
        prompt_path = prompts[0]
        print(f"  [LLM] 单次调用: {Path(prompt_path).name}")
        
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt_content = f.read()
            
            response = self.llm.chat(prompt_content)
            print(f"  [LLM] 响应完成 ({len(response)} 字符)")
            
            return [{
                "success": True,
                "prompt_path": prompt_path,
                "response": response,
                "index": 0,
            }]
        except InterruptException:
            raise  # 中断异常直接抛出
        except Exception as e:
            return [{
                "success": False,
                "prompt_path": prompt_path,
                "error": str(e),
                "index": 0,
            }]
    
    def _parallel_calls(self, prompt_files: List[str]) -> List[Dict[str, Any]]:
        """并发 LLM 调用
        
        使用 RunnableParallel 实现并发，自动关联 trace。
        """
        prompts = []
        for pf in prompt_files:
            if pf.endswith('.txt') and not pf.endswith('README.txt') and 'main' not in pf:
                try:
                    with open(pf, 'r', encoding='utf-8') as f:
                        prompts.append({
                            'path': pf,
                            'content': f.read()
                        })
                except Exception:
                    continue
        
        if not prompts:
            return []
        
        print(f"  [LLM] 并发调用 {len(prompts)} 个 prompt...")
        
        use_runnable = False
        try:
            from langchain_core.runnables import RunnableParallel, RunnableLambda
            use_runnable = True
        except ImportError:
            pass
        
        if use_runnable:
            return self._parallel_calls_with_runnable(prompts)
        else:
            return self._parallel_calls_with_threadpool(prompts)
    
    def _parallel_calls_with_runnable(self, prompts: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """使用 RunnableParallel 并发调用（自动关联 trace）"""
        from langchain_core.runnables import RunnableParallel, RunnableLambda
        
        def create_callable(prompt_data: Dict[str, str], index: int, total: int):
            def call_fn(_: Any = None) -> Dict[str, Any]:
                return self._call_with_retry(
                    prompt_data['content'],
                    prompt_data['path'],
                    index,
                    total
                )
            return RunnableLambda(call_fn)
        
        runnables = {}
        for i, p in enumerate(prompts):
            key = f"call_{i}"
            runnables[key] = create_callable(p, i + 1, len(prompts))
        
        parallel = RunnableParallel(**runnables)
        results_map = parallel.invoke({})
        
        results = []
        for i in range(len(prompts)):
            key = f"call_{i}"
            results.append(results_map[key])
        
        return results
    
    def _parallel_calls_with_threadpool(self, prompts: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """使用 ThreadPoolExecutor 并发调用（回退方案）"""
        results = []
        max_workers = _get_concurrent_calls()
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures: List[Future] = []
            for i, p in enumerate(prompts):
                future = executor.submit(
                    self._call_with_retry,
                    p['content'],
                    p['path'],
                    i + 1,
                    len(prompts)
                )
                futures.append(future)
            
            for future in futures:
                try:
                    timeout = _get_llm_timeout()
                    result = future.result(timeout=timeout)
                    results.append(result)
                except Exception as e:
                    results.append({
                        'success': False,
                        'error': str(e),
                    })
        
        return results
    
    def _interruptible_sleep(self, seconds: float):
        """可中断的 sleep
        
        每秒检查一次中断状态，如果检测到中断则抛出 InterruptException。
        """
        if not HAS_INTERRUPT or not interrupt_controller:
            time.sleep(seconds)
            return
        
        end_time = time.time() + seconds
        while time.time() < end_time:
            if interrupt_controller.is_interrupted():
                raise InterruptException("用户中断")
            remaining = end_time - time.time()
            time.sleep(min(1.0, remaining))
    
    def _call_with_retry(
        self,
        prompt: str,
        prompt_path: str,
        index: int,
        total: int
    ) -> Dict[str, Any]:
        """带重试的 LLM 调用"""
        max_retries = _get_llm_max_retries()
        retry_delay_base = _get_retry_delay()
        
        for attempt in range(max_retries):
            # 检查中断
            if HAS_INTERRUPT and interrupt_controller and interrupt_controller.is_interrupted():
                raise InterruptException("用户中断")
            
            try:
                print(f"  [LLM-{index}/{total}] 处理 {Path(prompt_path).name}...")
                response = self.llm.chat(prompt)
                print(f"  [LLM-{index}/{total}] 完成 ({len(response)} 字符)")
                return {
                    'success': True,
                    'prompt_path': prompt_path,
                    'response': response,
                    'index': index
                }
            except InterruptException:
                raise  # 中断异常直接抛出
            except Exception as e:
                if attempt < max_retries - 1:
                    delay = retry_delay_base * 10 * (attempt + 1)
                    print(f"  [LLM-{index}/{total}] 失败，{delay}s 后重试 {attempt + 2}/{max_retries}...")
                    # 分段 sleep，每秒检查中断
                    self._interruptible_sleep(delay)
                else:
                    raise e
        
        return {'success': False, 'error': 'max retries exceeded'}
    
    def _merge_responses(
        self,
        responses: List[Dict[str, Any]],
        ci_data: dict,
        ci_data_path: str = ""
    ) -> str:
        """合并多个 LLM 响应
        
        注意: 此方法保留用于结果合并，但合并逻辑已移至 ResultMergingAgent。
        CICDOrchestrator 负责编排 ResultMergingAgent，不在此 Agent 内直接调用。
        """
        successful = [r for r in responses if r.get("success")]
        if not successful:
            print("  [ERROR] 所有 LLM 调用都失败")
            return ""
        
        print(f"  [Merge] 成功响应数: {len(successful)}")
        
        merged_parts = []
        for r in successful:
            response = r.get("response", "")
            if response:
                response = self._clean_trailing_headers(response)
                merged_parts.append(response)
                prompt_name = Path(r.get('prompt_path', 'unknown')).name
                print(f"    - {prompt_name}: {len(response)} 字符")
        
        result = "\n\n---\n\n".join(merged_parts)
        print(f"  [Merge] 合并后长度: {len(result)} 字符")
        
        return result
    
    def _clean_trailing_headers(self, content: str) -> str:
        """清理响应末尾的残留标题
        
        删除批次响应末尾的空标题：
        - ### 触发条件
        - - xxx
        - ### 工作流详情
        - （后面没有 #### 工作流标题）
        
        这些残留标题会在合并时与下一批次的开头拼接，导致触发条件与工作流不匹配。
        """
        import re
        
        pattern = r'### 触发条件\s*\n(?:-.*\n|\s*\n)*### 工作流详情\s*\n\s*$'
        cleaned = re.sub(pattern, '', content)
        
        if len(cleaned) != len(content):
            print(f"    [Clean] 清理了 {len(content) - len(cleaned)} 字符的残留标题")
        
        return cleaned
