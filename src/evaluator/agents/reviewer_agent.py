"""报告验证 Agent - 检视 CI/CD 报告的准确性和完整性（通用化实现）"""
import re
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, List, Set, Any
from evaluator.utils import parallel_execute
from evaluator.llm import LLMClient
from .base_agent import BaseAgent, AgentMeta


@dataclass
class GroundTruth:
    """从 ci_data.json 提取的真实数据"""
    workflows: Set[str] = field(default_factory=set)
    jobs: Dict[str, Set[str]] = field(default_factory=dict)
    triggers: Dict[str, Set[str]] = field(default_factory=dict)
    scripts: Set[str] = field(default_factory=set)
    actions: Set[str] = field(default_factory=set)
    total_steps: int = 0


@dataclass
class ClaimedEntities:
    """从报告中提取的声称数据"""
    workflows: Set[str] = field(default_factory=set)
    jobs: Dict[str, Set[str]] = field(default_factory=dict)
    triggers: Dict[str, Set[str]] = field(default_factory=dict)
    scripts: Set[str] = field(default_factory=set)
    actions: Set[str] = field(default_factory=set)


# 配置常量

try:
    from evaluator.config import config
    HAS_CONFIG = True
except ImportError:
    HAS_CONFIG = False
    config = None

def _get_llm_workers() -> int:
    return config.max_llm_workers if config and HAS_CONFIG else 4

def _get_llm_timeout() -> int:
    return config.llm_call_timeout if config and HAS_CONFIG else 60

def _get_max_retries() -> int:
    return config.max_retries if config and HAS_CONFIG else 3

def _get_retry_delay() -> float:
    return config.llm_retry_base_delay if config and HAS_CONFIG else 1.0


class ReviewerAgent(BaseAgent):
    """报告验证 Agent - 确保报告准确且完整"""

    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="ReviewerAgent",
            description="验证报告的准确性和完整性，决定是否需要重试",
            category="analysis",
            inputs=["cicd_analysis", "project_path", "report_md"],
            outputs=["review_result", "review_issues", "corrected_report"],
            dependencies=["CICDAgent"],
        )

    def __init__(self, llm: Optional[LLMClient] = None):
        super().__init__()
        self.llm = llm
    
    # 常见非 Job 关键词（用于过滤）
    NON_JOB_KEYWORDS = {
        'the', 'and', 'for', 'use', 'using', 'with', 'this', 'that', 'from', 'into',
        'run', 'runs', 'running', 'start', 'starts', 'started', 'starting',
        'end', 'ends', 'ending', 'finished', 'finish', 'completes', 'complete', 'completed',
        'check', 'checks', 'checking', 'create', 'creates', 'created', 'creating',
        'build', 'builds', 'building', 'built', 'install', 'installs', 'installed',
        'setup', 'setups', 'configured', 'configure', 'configures',
        'clone', 'clones', 'cloned', 'checkout', 'checkouts', 'fetches', 'fetch',
        'upload', 'uploads', 'uploaded', 'download', 'downloads', 'downloaded',
        'generate', 'generates', 'generated', 'output', 'outputs', 'input', 'inputs',
        'error', 'errors', 'warning', 'warnings', 'success', 'failure', 'fail', 'failed',
        'info', 'information', 'debug', 'verbose', 'trace', 'silent',
        'action', 'actions', 'workflow', 'workflows', 'job', 'jobs', 'step', 'steps',
        'trigger', 'triggers', 'triggered', 'dispatch', 'dispatched',
        'schedule', 'scheduled', 'cron', 'manual', 'manually',
        'github', 'secrets', 'token', 'tokens', 'credentials',
        'name', 'type', 'types', 'path', 'file', 'files', 'directory', 'directories',
        'folder', 'folders', 'dir', 'dirs', 'root', 'base',
        'config', 'configuration', 'settings', 'options', 'option', 'arguments', 'args',
        'version', 'versions', 'tag', 'tags', 'branch', 'branches',
        'yes', 'no', 'true', 'false', 'null', 'none', 'default', 'custom', 'customize',
        'test', 'tests', 'testing', 'suite', 'suites', 'unit', 'integration', 'e2e',
        'main', 'master', 'develop', 'developing', 'feature', 'features',
        'release', 'releases', 'published', 'publish', 'deploy', 'deployment',
        'python', 'node', 'npm', 'pip', 'conda', 'apt', 'yum', 'brew',
        'linux', 'macos', 'windows', 'ubuntu', 'centos',
        'gh', 'cli', 'command', 'commands', 'script', 'scripts',
    }
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        cicd_analysis = state.get("cicd_analysis") or {}
        project_path = state.get("project_path") or ""
        errors = state.get("errors", [])
        
        ci_data_path = cicd_analysis.get("ci_data_path")
        if not ci_data_path:
            ci_data_path = str(Path(project_path) / "ci_data.json")
        
        report_path = cicd_analysis.get("report_path")
        if not report_path:
            report_path = str(Path(project_path) / "CI_ARCHITECTURE.md")
        
        arch_json_path = cicd_analysis.get("architecture_json_path")
        if not arch_json_path:
            arch_json_path = str(Path(project_path) / "architecture.json")
        
        print(f"\n{'='*50}")
        print("  报告验证")
        print(f"{'='*50}")
        
        if not Path(report_path).exists():
            print(f"  ⚠️ 未找到报告文件: {report_path}")
            return {
                **state,
                "review_result": {"status": "error", "message": "报告文件不存在"},
                "review_issues": [],
                "errors": errors + ["报告文件不存在"],
            }
        
        try:
            print("\n[1/6] 加载数据...")
            ci_data = self._load_ci_data(ci_data_path)
            report = self._load_report(report_path)
            arch_data = self._load_architecture(arch_json_path)
            
            if not ci_data:
                return {
                    **state,
                    "review_result": {"status": "error", "message": "无法加载 CI 数据"},
                    "review_issues": [],
                    "errors": errors + ["CI 数据加载失败"],
                }
            
            print(f"  工作流数: {len(ci_data.get('workflows', {}))}")
            print(f"  脚本数: {len(ci_data.get('scripts', []))}")
            
            print("\n[2/6] 构建真实数据集合...")
            ground_truth = self._build_ground_truth(ci_data)
            print(f"  真实工作流: {len(ground_truth.workflows)}")
            print(f"  真实 Job: {sum(len(j) for j in ground_truth.jobs.values())}")
            
            # 动态获取触发类型
            valid_triggers = self._extract_valid_triggers(ci_data)
            print(f"  触发类型: {', '.join(sorted(valid_triggers))}")
            
            print("\n[3/6] 提取报告中的实体...")
            claimed = self._extract_claimed(report, ground_truth, ci_data)
            print(f"  声称工作流: {len(claimed.workflows)}")
            print(f"  声称 Job: {sum(len(j) for j in claimed.jobs.values())}")
            print(f"  (使用正则统计，不依赖 LLM)")
            
            print("\n[4/7] 双向验证...")
            accuracy_issues = self._bidirectional_validate(ground_truth, claimed, report)
            print(f"  发现 {len(accuracy_issues)} 个准确性问题")
            
            print("\n[5/7] 完整性检查...")
            completeness_issues = self._validate_completeness(report, ground_truth, claimed)
            print(f"  发现 {len(completeness_issues)} 个完整性问题")
            
            print("\n[6/7] 验证最终报告...")
            report_md = state.get("report_md") or str(Path(project_path) / "CI_ARCHITECTURE.md")
            report_html = state.get("report_html") or str(Path(project_path) / "report.html")
            
            if Path(report_html).exists():
                final_report_result = self.validate_final_reports(report_md, report_html, ci_data)
                if not final_report_result["valid"]:
                    print(f"  发现 {len(final_report_result['md_issues']) + len(final_report_result['html_issues'])} 个报告问题")
                    for issue in final_report_result["md_issues"]:
                        print(f"    [MD] {issue}")
                        completeness_issues.append({"severity": "incomplete", "type": "md_issue", "message": issue})
                    for issue in final_report_result["html_issues"]:
                        print(f"    [HTML] {issue}")
                        completeness_issues.append({"severity": "incomplete", "type": "html_issue", "message": issue})
                else:
                    print(f"  最终报告验证通过")
            else:
                print(f"  HTML 报告不存在，跳过验证")
            
            print("\n[7/7] 分类处理...")
            all_issues = accuracy_issues + completeness_issues
            
            result = self._classify_and_process(
                all_issues, report, ci_data, state.get("review_retry_count", 0), state
            )
            
            print(f"\n{'='*50}")
            print(f"  验证结果: {result.get('review_result', {}).get('status', 'unknown')}")
            print(f"{'='*50}")
            
            return {**state, **result}
            
        except Exception as e:
            print(f"  ❌ 验证过程出错: {e}")
            import traceback
            traceback.print_exc()
            return {
                **state,
                "review_result": {"status": "error", "message": str(e)},
                "review_issues": [],
                "errors": errors + [f"验证过程出错: {str(e)}"],
            }
    
    def _load_ci_data(self, path: str) -> dict:
        """加载 CI 数据"""
        try:
            if Path(path).exists():
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"  ⚠️ 加载 CI 数据失败: {e}")
        return {}
    
    def _load_report(self, path: str) -> str:
        """加载报告内容"""
        try:
            return Path(path).read_text(encoding="utf-8")
        except Exception as e:
            print(f"  ⚠️ 加载报告失败: {e}")
        return ""
    
    def _load_architecture(self, path: str) -> dict:
        """加载架构图数据"""
        try:
            if Path(path).exists():
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"  ⚠️ 加载架构图失败: {e}")
        return {}
    
    def _build_ground_truth(self, ci_data: dict) -> GroundTruth:
        """从 ci_data.json 构建真实实体集合"""
        
        workflows = set(ci_data.get("workflows", {}).keys())
        
        jobs = {}
        triggers = {}
        for wf_name, wf_data in ci_data.get("workflows", {}).items():
            jobs[wf_name] = set(wf_data.get("jobs", {}).keys())
            triggers[wf_name] = set(wf_data.get("triggers", []))
        
        scripts = set()
        for script in ci_data.get("scripts", []):
            path = script.get("path", "")
            if path:
                scripts.add(path)
        
        actions = set()
        total_steps = 0
        for wf_data in ci_data.get("workflows", {}).values():
            for job_data in wf_data.get("jobs", {}).values():
                steps = job_data.get("steps", [])
                total_steps += len(steps)
                for step in steps:
                    uses = step.get("uses", "")
                    if uses and "@" in uses:
                        action = uses.split("@")[0]
                        actions.add(action)
        
        return GroundTruth(
            workflows=workflows,
            jobs=jobs,
            triggers=triggers,
            scripts=scripts,
            actions=actions,
            total_steps=total_steps
        )
    
    def _extract_valid_triggers(self, ci_data: Dict) -> Set[str]:
        """从 ci_data 中提取项目实际使用的触发类型"""
        triggers = set()
        for wf_data in ci_data.get("workflows", {}).values():
            triggers.update(wf_data.get("triggers", []))
        return triggers
    
    def _count_workflows_by_regex(self, report: str) -> int:
        """用正则统计工作流详细描述数量"""
        pattern = r'####\s+\d+\.\d+\s+[\w-]+\.yml'
        return len(re.findall(pattern, report))
    
    def _count_job_tables_by_regex(self, report: str) -> int:
        """用正则统计 Job 表格数量"""
        pattern = r'\|\s*序号\s*\|\s*Job名称\s*\|'
        return len(re.findall(pattern, report))
    
    def _count_step_details_by_regex(self, report: str) -> int:
        """用正则统计步骤详情数量"""
        pattern = r'步骤\d+:'
        return len(re.findall(pattern, report))
    
    def _extract_workflow_names_by_regex(self, report: str) -> Set[str]:
        """用正则提取工作流名称列表"""
        pattern = r'####\s+\d+\.\d+\s+([\w-]+\.yml)'
        return set(re.findall(pattern, report))
    
    def _extract_claimed(self, report: str, ground_truth: GroundTruth, ci_data: Dict) -> ClaimedEntities:
        """从报告中提取声称的实体（使用正则统计，不依赖 LLM）"""
        
        # 动态获取项目实际使用的触发类型
        valid_triggers = self._extract_valid_triggers(ci_data)
        
        claimed_workflows = self._extract_workflow_names_by_regex(report)
        
        if not claimed_workflows:
            for wf in ground_truth.workflows:
                if wf in report:
                    claimed_workflows.add(wf)
        
        claimed_triggers = {}
        for wf in claimed_workflows:
            wf_triggers = set()
            
            yaml_blocks = self._extract_yaml_blocks_for_workflow(report, wf)
            for yaml_content in yaml_blocks:
                for trigger in valid_triggers:
                    pattern = rf'^\s*{re.escape(trigger)}\s*:'
                    if re.search(pattern, yaml_content, re.MULTILINE):
                        wf_triggers.add(trigger)
            
            wf_section = self._extract_workflow_section(report, wf)
            for trigger in valid_triggers:
                pattern = rf'`{re.escape(trigger)}`'
                if re.search(pattern, wf_section):
                    wf_triggers.add(trigger)
            
            for trigger in valid_triggers:
                pattern = rf'^###\s+{re.escape(trigger)}(\s*\(|\s*$)'
                if re.search(pattern, wf_section, re.MULTILINE):
                    wf_triggers.add(trigger)
            
            claimed_triggers[wf] = wf_triggers
        
        claimed_jobs = {}
        for wf in claimed_workflows:
            section = self._extract_workflow_section(report, wf)
            known_jobs = ground_truth.jobs.get(wf, set())
            claimed_jobs[wf] = self._extract_jobs_by_code(section, known_jobs)
        
        claimed_scripts = set()
        script_patterns = [
            r'[\w./\\-]+\.py\b',
            r'[\w./\\-]+\.sh\b',
            r'[\w./\\-]+\.bash\b',
        ]
        for pattern in script_patterns:
            claimed_scripts.update(re.findall(pattern, report))
        
        claimed_actions = set()
        potential_actions = re.findall(r'\b[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+\b', report)
        for a in potential_actions:
            if not any(x in a.lower() for x in ['http', 'https', 'www', 'file:', 'path:', 'url:']):
                claimed_actions.add(a)
        
        return ClaimedEntities(
            workflows=claimed_workflows,
            jobs=claimed_jobs,
            triggers=claimed_triggers,
            scripts=claimed_scripts,
            actions=claimed_actions
        )
    
    def _extract_jobs_smart(
        self, 
        report: str, 
        claimed_workflows: Set[str],
        ground_truth: GroundTruth
    ) -> Dict[str, Set[str]]:
        """智能提取 Job 名称（LLM 辅助 + 代码兜底）"""
        
        claimed_jobs = {}
        
        # 按工作流切分报告
        workflow_sections = {}
        for wf in claimed_workflows:
            section = self._extract_workflow_section(report, wf)
            if section:
                workflow_sections[wf] = section
        
        if not workflow_sections:
            return claimed_jobs
        
        # 如果没有 LLM，使用代码提取兜底
        if not self.llm:
            print("  ⚠️ 未配置 LLM，使用代码提取 Job")
            for wf, section in workflow_sections.items():
                known_jobs = ground_truth.jobs.get(wf, set())
                claimed_jobs[wf] = self._extract_jobs_by_code(section, known_jobs)
            return claimed_jobs
        
        # 并发 LLM 提取（使用统一并发工具）
        max_workers = _get_llm_workers()
        print(f"  使用 LLM 提取 Job（并发数: {max_workers}）...")
        
        # 创建任务列表（保留重试和降级逻辑）
        def create_extract_task(wf_name: str):
            def task():
                try:
                    section = workflow_sections.get(wf_name, "")
                    known_jobs = ground_truth.jobs.get(wf_name, set())
                    # 调用_extract_jobs_with_llm（内部有重试机制）
                    jobs = self._extract_jobs_with_llm(section, wf_name, known_jobs)
                    return (wf_name, jobs, None)
                except Exception as e:
                    # 重试全部失败后，降级到代码提取
                    section = workflow_sections.get(wf_name, "")
                    known_jobs = ground_truth.jobs.get(wf_name, set())
                    jobs = self._extract_jobs_by_code(section, known_jobs)
                    return (wf_name, jobs, str(e))
            return task
        
        tasks = [create_extract_task(wf) for wf in workflow_sections.keys()]
        
        try:
            # 使用统一并发工具执行（自动关联LangSmith trace）
            results = parallel_execute(tasks, max_concurrent=max_workers)
            
            # 处理结果
            for wf_name, jobs, error in results:
                claimed_jobs[wf_name] = jobs
                if error:
                    print(f"    ✗ {wf_name}: {error}（已降级）")
                else:
                    print(f"    ✓ {wf_name}: {len(jobs)} jobs")
        except Exception as e:
            print(f"  ⚠️ 并发提取失败: {e}，使用代码提取")
            for wf, section in workflow_sections.items():
                known_jobs = ground_truth.jobs.get(wf, set())
                claimed_jobs[wf] = self._extract_jobs_by_code(section, known_jobs)
        
        return claimed_jobs
    
    def _extract_workflow_section(
        self, 
        report: str, 
        wf_name: str, 
        max_length: Optional[int] = None
    ) -> str:
        """提取单个工作流的上下文（限制长度）"""
        if max_length is None:
            max_length = config.max_section_length if config and HAS_CONFIG else 3000
        
        # 找到工作流名称的所有位置
        pattern = re.escape(wf_name)
        matches = list(re.finditer(pattern, report))
        
        if not matches:
            return ""
        
        # 策略1：找到 "#### X.X wf_name" 或 "### wf_name" 格式的标题位置
        title_pattern = rf'(?:####\s+\d+\.\d+\s+|###\s+){re.escape(wf_name)}'
        title_match = re.search(title_pattern, report)
        
        if title_match:
            start = title_match.start()
            # 找到下一个同级或更高级标题
            next_title = re.search(r'\n(?:####\s+\d+\.\d+|###|##\s+)', report[start+10:])
            if next_title:
                end = start + 10 + next_title.start()
            else:
                end = len(report)
            
            section = report[start:end]
        else:
            # 策略2：取最长匹配位置附近的内容
            best_match = max(matches, key=lambda m: m.end() - m.start())
            start = max(0, best_match.start() - 200)
            end = min(len(report), best_match.end() + max_length)
            section = report[start:end]
        
        # 限制长度
        if len(section) > max_length:
            section = section[:max_length]
        
        return section
    
    def _get_wf_context(self, report: str, wf_name: str) -> str:
        """获取工作流的上下文（短版本，用于触发条件提取）"""
        return self._extract_workflow_section(report, wf_name, max_length=1500)
    
    def _extract_yaml_blocks_for_workflow(self, report: str, wf_name: str) -> List[str]:
        """提取工作流相关的 YAML 代码块"""
        blocks = []
        
        # 找到工作流标题位置
        title_pattern = rf'(?:####\s+\d+\.\d+\s+|###\s+){re.escape(wf_name)}'
        title_match = re.search(title_pattern, report)
        
        if not title_match:
            return blocks
        
        # 获取工作流段落（从标题到下一个标题）
        start = title_match.start()
        next_title = re.search(r'\n(?:####\s+\d+\.\d+|###|##\s+)', report[start+10:])
        end = start + 10 + next_title.start() if next_title else len(report)
        section = report[start:end]
        
        # 在段落中提取所有 YAML 代码块
        yaml_pattern = r'```yaml\s*\n(.*?)```'
        for match in re.finditer(yaml_pattern, section, re.DOTALL):
            yaml_content = match.group(1)
            blocks.append(yaml_content)
        
        return blocks
    
    def _extract_jobs_with_llm(
        self, 
        section: str, 
        wf_name: str, 
        known_jobs: Set[str]
    ) -> Set[str]:
        """使用 LLM 从单个工作流段落中提取 Job 名称（带重试）"""
        
        if not section:
            return known_jobs
        
        if self.llm is None:
            return known_jobs
        
        prompt = f"""从以下关于工作流 '{wf_name}' 的描述中，提取所有提及的 Job 名称。

该工作流的实际 Job 名称（供参考）：{list(known_jobs) if known_jobs else '未知'}

内容：
{section}

要求：
1. 提取所有在内容中明确提及的 Job 名称
2. Job 名称通常是英文单词，可能包含下划线或连字符
3. 只输出 Job 名称，每行一个，不要其他内容
4. 如果没有找到任何 Job，输出 "无"

输出："""
        
        max_retries = _get_max_retries()
        retry_delay = _get_retry_delay()
        
        for attempt in range(max_retries):
            try:
                response = self.llm.chat(prompt)
                
                # 解析响应
                jobs = set()
                for line in response.strip().split('\n'):
                    line = line.strip()
                    if line and line != "无":
                        # 清理格式
                        job = re.sub(r'^[-\d.*]\s*', '', line)
                        job = job.strip('`\'"')
                        if job and len(job) > 1:
                            jobs.add(job)
                
                return jobs
            except Exception as e:
                if attempt < max_retries - 1:
                    delay = retry_delay * (attempt + 1)
                    print(f"    ⚠️ LLM 提取失败: {e}，{delay}s 后重试 ({attempt + 2}/{max_retries})")
                    import time
                    time.sleep(delay)
                else:
                    print(f"    ⚠️ LLM 提取失败: {e}")
                    raise
        
        return set()
    
    def _extract_jobs_by_code(self, section: str, known_jobs: Set[str]) -> Set[str]:
        """代码提取 Job（降级方案）- 保守策略"""
        
        found = set()
        
        # 方法1：搜索已知 Job 名称（最可靠）
        for job in known_jobs:
            if job in section:
                found.add(job)
        
        # 方法2：搜索包含在表格或列表中的 Job 名称
        # 通常 Job 名称出现在表格的第2列
        # 表格格式: | 序号 | Job名称 | 运行环境 | 目的 |
        # 需要匹配第2列：| 序号 | job_name | 运行环境 |
        table_jobs = re.findall(r'\|\s*\d+\s*\|\s*([a-z][a-z0-9_-]{2,30})\s*\|', section)
        for job in table_jobs:
            # 过滤明显不是 Job 的词
            if job.lower() not in self.NON_JOB_KEYWORDS:
                found.add(job)
        
        # 方法3：搜索 Markdown 列表格式中的 Job (- job_name 或 * job_name)
        list_jobs = re.findall(r'^[-\*]\s+([a-z][a-z0-9_-]{2,30})\s*$', section, re.MULTILINE)
        for job in list_jobs:
            if job.lower() not in self.NON_JOB_KEYWORDS:
                found.add(job)
        
        return found
    
    def _bidirectional_validate(
        self, 
        ground_truth: GroundTruth, 
        claimed: ClaimedEntities,
        report: str = ""
    ) -> List[dict]:
        """双向验证
        
        在发现问题时，同时记录锚点信息，避免修复时重新搜索
        """
        issues = []
        
        # === 正向验证：检查遗漏（真实存在但报告中未提及）===
        
        # 工作流遗漏
        missing_workflows = ground_truth.workflows - claimed.workflows
        for wf in missing_workflows:
            issues.append({
                "severity": "incomplete",
                "type": "workflow_missing",
                "entity": wf,
                "message": f"工作流 '{wf}' 未在报告中提及",
                "anchor": {"type": "stage_section", "workflow": wf},
            })
        
        # Job 遗漏
        for wf, real_jobs in ground_truth.jobs.items():
            claimed_jobs = claimed.jobs.get(wf, set())
            missing_jobs = real_jobs - claimed_jobs
            for job in missing_jobs:
                issues.append({
                    "severity": "incomplete",
                    "type": "job_missing",
                    "workflow": wf,
                    "entity": job,
                    "message": f"工作流 '{wf}' 的 Job '{job}' 未在报告中提及",
                    "anchor": {"type": "job_table", "workflow": wf},
                })
        
        # 触发条件遗漏
        for wf, real_triggers in ground_truth.triggers.items():
            claimed_triggers = claimed.triggers.get(wf, set())
            missing_triggers = real_triggers - claimed_triggers
            for trigger in missing_triggers:
                issues.append({
                    "severity": "incomplete",
                    "type": "trigger_missing",
                    "workflow": wf,
                    "entity": trigger,
                    "message": f"工作流 '{wf}' 的触发条件 '{trigger}' 未在报告中提及",
                    "anchor": {"type": "trigger_yaml", "workflow": wf},
                })
        
        # === 反向验证：检查虚构（报告中提及但真实不存在）===
        
        # 工作流虚构
        fake_workflows = claimed.workflows - ground_truth.workflows
        for wf in fake_workflows:
            issues.append({
                "severity": "critical",
                "type": "workflow_fake",
                "entity": wf,
                "message": f"工作流 '{wf}' 不存在于项目中（虚构）",
                "anchor": {"type": "workflow_section", "workflow": wf},
            })
        
        # Job 虚构（只检查有对应工作流的情况）
        for wf, claimed_jobs in claimed.jobs.items():
            if wf in ground_truth.jobs:
                real_jobs = ground_truth.jobs[wf]
                fake_jobs = claimed_jobs - real_jobs
                for job in fake_jobs:
                    issues.append({
                        "severity": "critical",
                        "type": "job_fake",
                        "workflow": wf,
                        "entity": job,
                        "message": f"工作流 '{wf}' 的 Job '{job}' 不存在（虚构）",
                        "anchor": {"type": "job_row", "workflow": wf, "job": job},
                    })
        
        # 触发条件虚构
        for wf, claimed_triggers in claimed.triggers.items():
            if wf in ground_truth.triggers:
                real_triggers = ground_truth.triggers[wf]
                fake_triggers = claimed_triggers - real_triggers
                for trigger in fake_triggers:
                    issues.append({
                        "severity": "critical",
                        "type": "trigger_fabricated",
                        "workflow": wf,
                        "entity": trigger,
                        "message": f"工作流 '{wf}' 不存在触发条件 '{trigger}'（虚构）",
                        "anchor": {"type": "trigger_yaml", "workflow": wf},
                    })
        
        return issues
    
    def _validate_completeness(
        self, 
        report: str, 
        ground_truth: GroundTruth,
        claimed: ClaimedEntities
    ) -> List[dict]:
        """完整性检查（使用正则统计 + 规则对比，不依赖 LLM）"""
        issues = []
        
        reported_wf_count = self._count_workflows_by_regex(report)
        actual_wf_count = len(ground_truth.workflows)
        
        reported_job_count = self._count_job_tables_by_regex(report)
        actual_job_count = sum(len(jobs) for jobs in ground_truth.jobs.values())
        
        reported_step_count = self._count_step_details_by_regex(report)
        
        print(f"  工作流: 报告={reported_wf_count}, 实际={actual_wf_count}")
        print(f"  Job表格: 报告={reported_job_count}, 实际={actual_job_count}")
        print(f"  步骤详情: 报告={reported_step_count}, 实际={ground_truth.total_steps}")
        
        if reported_wf_count < actual_wf_count:
            missing_count = actual_wf_count - reported_wf_count
            issues.append({
                "severity": "incomplete",
                "type": "missing_workflow_detail",
                "message": f"报告声称已分析 {actual_wf_count} 个工作流，但仅详细展示了 {reported_wf_count} 个工作流的分析内容，缺少剩余 {missing_count} 个工作流的分析。"
            })
        
        if reported_job_count < reported_wf_count:
            issues.append({
                "severity": "incomplete",
                "type": "missing_job_table",
                "message": f"有 {reported_wf_count} 个工作流，但只有 {reported_job_count} 个 Job 表格，部分工作流缺少 Job 详细分析。"
            })
        
        actual_step_count = ground_truth.total_steps
        if actual_step_count > 0:
            coverage_ratio = reported_step_count / actual_step_count
        else:
            coverage_ratio = 1.0
        
        if coverage_ratio < 0.8:
            issues.append({
                "severity": "incomplete",
                "type": "weak_analysis",
                "message": f"步骤详情覆盖率仅 {coverage_ratio*100:.1f}%（{reported_step_count}/{actual_step_count}），建议补充更多步骤分析。"
            })
        
        return issues
    
    def _classify_and_process(
        self, 
        all_issues: List[dict], 
        report: str, 
        ci_data: dict,
        retry_count: int,
        state: Optional[Dict[str, Any]] = None
    ) -> dict:
        """分类问题并决定处理方式
        
        简化版：只负责发现问题，修复由 ReportFixAgent 处理
        """
        
        if not all_issues:
            print("  ✅ 所有验证通过")
            return {
                "review_result": {"status": "passed"},
                "review_issues": [],
                "review_retry_count": retry_count,
            }
        
        minor_issues = [i for i in all_issues if i.get("severity") == "minor"]
        critical_issues = [i for i in all_issues if i.get("severity") == "critical"]
        incomplete_issues = [i for i in all_issues if i.get("severity") == "incomplete"]
        
        print(f"  问题分类: critical={len(critical_issues)}, incomplete={len(incomplete_issues)}, minor={len(minor_issues)}")
        
        self._print_issues_detail(all_issues)
        
        print(f"\n  发现 {len(all_issues)} 个问题，需要修复")
        return {
            "review_result": {"status": "issues_found", "issues_count": len(all_issues)},
            "review_issues": all_issues,
            "review_retry_count": retry_count,
        }
    
    def _print_issues_detail(self, issues: List[dict]) -> None:
        """详细输出问题列表，按严重级别分组"""
        if not issues:
            return
        
        critical_issues = [i for i in issues if i.get("severity") == "critical"]
        incomplete_issues = [i for i in issues if i.get("severity") == "incomplete"]
        minor_issues = [i for i in issues if i.get("severity") == "minor"]
        
        print("\n=== 问题详情 ===\n")
        
        if critical_issues:
            print(f"【Critical 问题】({len(critical_issues)} 个)")
            for i, issue in enumerate(critical_issues, 1):
                msg = issue.get("message", str(issue))
                print(f"  [{i}] {issue.get('type', 'unknown')}: {msg}")
            print()
        
        if incomplete_issues:
            print(f"【Incomplete 问题】({len(incomplete_issues)} 个)")
            for i, issue in enumerate(incomplete_issues, 1):
                msg = issue.get("message", str(issue))
                print(f"  [{i}] {issue.get('type', 'unknown')}: {msg}")
            print()
        
        if minor_issues:
            print(f"【Minor 问题】({len(minor_issues)} 个)")
            for i, issue in enumerate(minor_issues, 1):
                msg = issue.get("message", str(issue))
                print(f"  [{i}] {issue.get('type', 'unknown')}: {msg}")
            print()
    
    def _extract_section_by_lines(self, content: str, title_pattern: str) -> str:
        """使用行解析提取章节，不依赖正则"""
        lines = content.split('\n')
        result = []
        in_section = False
        
        for line in lines:
            if line.startswith('## ') and title_pattern in line:
                in_section = True
                result.append(line)
                continue
            
            if in_section and line.startswith('## '):
                break
            
            if in_section:
                result.append(line)
        
        return '\n'.join(result)
    
    def _check_section_empty(self, report: str, section_title: str) -> bool:
        """检查指定章节是否为空或缺失"""
        section = self._extract_section_by_lines(report, section_title)
        if not section:
            return True
        
        lines = section.split('\n')
        content_lines = [l for l in lines[1:] if l.strip()]
        return len(content_lines) == 0
    
    def validate_llm_response(
        self,
        llm_response: str,
        ci_data: dict,
    ) -> Dict[str, Any]:
        """检视 LLM 响应是否满足关键要求
        
        Args:
            llm_response: LLM 的响应内容
            ci_data: CI 数据（用于对比验证）
        
        Returns:
            {
                "valid": bool,
                "missing_workflows": List[str],
                "missing_jobs": Dict[str, List[str]],
                "missing_sections": List[str],
                "missing_json": List[str],
                "suggestions": List[str]
            }
        """
        result = {
            "valid": True,
            "missing_workflows": [],
            "missing_jobs": {},
            "missing_sections": [],
            "missing_json": [],
            "suggestions": []
        }
        
        # 1. 检查工作流完整性
        expected_workflows = set(ci_data.get("workflows", {}).keys())
        found_workflows = set(re.findall(r'####\s+\d+\.\d+\s+([\w-]+\.yml)', llm_response))
        result["missing_workflows"] = list(expected_workflows - found_workflows)
        
        if result["missing_workflows"]:
            result["valid"] = False
            result["suggestions"].append(f"缺失工作流: {result['missing_workflows']}")
        
        # 2. 检查 Job 完整性（抽样检查）
        sample_workflows = list(expected_workflows)[:5]
        for wf_name in sample_workflows:
            wf = ci_data.get("workflows", {}).get(wf_name, {})
            expected_jobs = set(wf.get("jobs", {}).keys())
            if not expected_jobs:
                continue
            
            # 在响应中查找该工作流的 Job
            wf_section_match = re.search(
                rf'####\s+\d+\.\d+\s+{re.escape(wf_name)}\s*\n(.*?)(?=####\s+\d+\.\d+|##\s+|$)',
                llm_response, re.DOTALL
            )
            if wf_section_match:
                wf_section = wf_section_match.group(1)
                found_jobs = set(re.findall(r'\|\s*\d+\s*\|\s*([\w-]+)\s*\|', wf_section))
                missing = expected_jobs - found_jobs
                if missing:
                    result["missing_jobs"][wf_name] = list(missing)
                    result["valid"] = False
        
        # 3. 检查必要章节
        required_sections = ["项目概述", "架构图", "附录", "发现", "建议"]
        for section in required_sections:
            if not re.search(rf'^##\s+.*{section}', llm_response, re.MULTILINE):
                result["missing_sections"].append(section)
        
        if result["missing_sections"]:
            result["valid"] = False
            result["suggestions"].append(f"缺失章节: {result['missing_sections']}")
        
        # 4. 检查 JSON 标记
        if not re.search(r'<!--\s*ARCHITECTURE_JSON\s+.*?\s*ARCHITECTURE_JSON\s*-->', llm_response, re.DOTALL):
            result["missing_json"].append("ARCHITECTURE_JSON")
        
        if not re.search(r'<!--\s*ANALYSIS_SUMMARY\s+.*?\s*ANALYSIS_SUMMARY\s*-->', llm_response, re.DOTALL):
            result["missing_json"].append("ANALYSIS_SUMMARY")
        
        if result["missing_json"]:
            result["valid"] = False
            result["suggestions"].append(f"缺失 JSON: {result['missing_json']}")
        
        return result
    
    def validate_stage_organization(
        self,
        llm_response: str,
        architecture_data: dict
    ) -> Dict[str, Any]:
        """检视阶段划分是否与架构图匹配
        
        Args:
            llm_response: LLM 响应内容
            architecture_data: 架构图 JSON 数据
        
        Returns:
            {
                "valid": bool,
                "expected_stages": List[str],
                "found_stages": List[str],
                "missing_stages": List[str],
                "workflow_coverage": float
            }
        """
        layers = architecture_data.get("layers", [])
        expected_stages = [layer.get("name", "") for layer in layers]
        
        found_stages = re.findall(r'^##\s+(.+?)\s*$', llm_response, re.MULTILINE)
        
        missing_stages = []
        for stage in expected_stages:
            if not any(stage in found for found in found_stages):
                missing_stages.append(stage)
        
        expected_workflows = set()
        for layer in layers:
            for node in layer.get("nodes", []):
                label = node.get("label", "")
                if label.endswith(".yml"):
                    expected_workflows.add(label)
        
        found_workflows = set(re.findall(r'####\s+\d+\.\d+\s+([\w-]+\.yml)', llm_response))
        coverage = len(found_workflows & expected_workflows) / len(expected_workflows) if expected_workflows else 0
        
        return {
            "valid": len(missing_stages) == 0 and coverage >= 0.8,
            "expected_stages": expected_stages,
            "found_stages": list(found_stages),
            "missing_stages": missing_stages,
            "workflow_coverage": coverage
        }
    
    def validate_final_reports(
        self,
        md_report_path: str,
        html_report_path: str,
        ci_data: dict,
    ) -> Dict[str, Any]:
        """验证最终报告（Markdown 和 HTML）
        
        Args:
            md_report_path: Markdown 报告路径
            html_report_path: HTML 报告路径
            ci_data: CI 数据
        
        Returns:
            {
                "valid": bool,
                "md_issues": List[str],
                "html_issues": List[str],
            }
        """
        result = {
            "valid": True,
            "md_issues": [],
            "html_issues": [],
        }
        
        # 1. 验证 Markdown 报告
        if Path(md_report_path).exists():
            md_content = Path(md_report_path).read_text(encoding="utf-8")
            
            # 1.1 检查必要章节存在且内容非空
            required_sections = {
                "项目概述": r'^##\s+项目概述\s*$(.*?)(?=^##\s+|^<!--|\Z)',
                "架构图": r'^##\s+.*架构图\s*$(.*?)(?=^##\s+|^<!--|\Z)',
                "关键发现和建议": r'^##\s+.*发现.*建议\s*$(.*?)(?=^##\s+|^<!--|\Z)',
                "附录": r'^##\s+附录[：:]*\s*.*?$(.*?)(?=^##\s+|^<!--|\Z)',
            }
            
            for section_name, pattern in required_sections.items():
                match = re.search(pattern, md_content, re.MULTILINE | re.DOTALL)
                if not match:
                    result["md_issues"].append(f"缺失章节: {section_name}")
                    result["valid"] = False
                elif not match.group(1).strip():
                    result["md_issues"].append(f"章节内容为空: {section_name}")
                    result["valid"] = False
            
            # 1.2 检查工作流覆盖率
            expected_workflows = set(ci_data.get("workflows", {}).keys())
            found_workflows = set(re.findall(r'####\s+\d+\.\d+\s+([\w-]+\.yml)', md_content))
            missing_workflows = expected_workflows - found_workflows
            if missing_workflows:
                result["md_issues"].append(f"缺失工作流: {list(missing_workflows)[:5]}")
                result["valid"] = False
            
            # 1.3 检查 ARCHITECTURE_JSON 存在
            if not re.search(r'<!--\s*ARCHITECTURE_JSON', md_content):
                result["md_issues"].append("缺失 ARCHITECTURE_JSON")
                result["valid"] = False
        else:
            result["md_issues"].append("Markdown 报告文件不存在")
            result["valid"] = False
        
        # 2. 验证 HTML 报告
        if Path(html_report_path).exists():
            html_content = Path(html_report_path).read_text(encoding="utf-8")
            
            # 2.1 检查必要 section 存在且内容非空
            required_sections_html = {
                "overview": "项目概述",
                "findings": "关键发现和建议",
                "appendix": "附录",
            }
            
            for section_id, section_name in required_sections_html.items():
                # 检查 section 存在
                section_match = re.search(
                    rf'<section id="{section_id}"[^>]*>.*?<div[^>]*class="section-content"[^>]*>(.*?)</div>\s*</section>',
                    html_content, re.DOTALL
                )
                if not section_match:
                    result["html_issues"].append(f"缺失 section: {section_id} ({section_name})")
                    result["valid"] = False
                else:
                    content = section_match.group(1).strip()
                    # 检查是否为空或显示"暂无"
                    if not content or "暂无" in content:
                        result["html_issues"].append(f"section 内容为空: {section_id} ({section_name})")
                        result["valid"] = False
            
            # 2.2 检查架构图数据存在
            if 'const architectureData = {"layers"' not in html_content and 'const architectureData = {}' not in html_content:
                result["html_issues"].append("缺失架构图数据或数据为空")
                result["valid"] = False
        else:
            result["html_issues"].append("HTML 报告文件不存在")
            result["valid"] = False
        
        return result

    def validate_architecture_completeness(
        self,
        ci_data: dict,
        architecture: dict
    ) -> dict:
        """
        验证架构完整性
        
        检查 architecture.json 是否包含 ci_data.json 中的所有工作流，
        以及触发入口层是否包含所有触发类型。
        
        Args:
            ci_data: ci_data.json 内容
            architecture: architecture.json 内容
        
        Returns:
            {
                "is_complete": bool,
                "missing_workflows": list[str],
                "trigger_types_in_ci": set[str],
                "trigger_types_in_arch": set[str],
                "missing_trigger_types": set[str],
                "layer_workflow_count": int,
                "ci_workflow_count": int,
            }
        """
        result = {
            "is_complete": True,
            "missing_workflows": [],
            "trigger_types_in_ci": set(),
            "trigger_types_in_arch": set(),
            "missing_trigger_types": set(),
            "layer_workflow_count": 0,
            "ci_workflow_count": 0,
        }
        
        # 1. 统计 ci_data 中的工作流和触发类型
        workflows = ci_data.get("workflows", {})
        result["ci_workflow_count"] = len(workflows)
        ci_workflow_names = set(workflows.keys())
        
        for wf in workflows.values():
            for trigger in wf.get("triggers", []):
                result["trigger_types_in_ci"].add(trigger)
        
        # 2. 统计 architecture 中的工作流和触发类型
        layers = architecture.get("layers", [])
        
        for layer in layers:
            nodes = layer.get("nodes", [])
            layer_name = layer.get("name", "")
            
            # 统计工作流节点
            if "触发" in layer_name:
                # 触发入口层：统计触发类型
                for node in nodes:
                    label = node.get("label", "")
                    if "事件" in label or "dispatch" in label:
                        trigger_name = label.replace(" 事件", "").replace("dispatch", "workflow_dispatch")
                        result["trigger_types_in_arch"].add(trigger_name)
            else:
                # 其他层：统计工作流节点
                for node in nodes:
                    label = node.get("label", "")
                    if label.endswith(".yml"):
                        result["layer_workflow_count"] += 1
        
        # 3. 找出遗漏的工作流
        arch_workflow_labels = set()
        for layer in layers:
            for node in layer.get("nodes", []):
                label = node.get("label", "")
                if label.endswith(".yml"):
                    arch_workflow_labels.add(label)
        
        result["missing_workflows"] = sorted(list(ci_workflow_names - arch_workflow_labels))
        
        # 4. 找出遗漏的触发类型
        result["missing_trigger_types"] = result["trigger_types_in_ci"] - result["trigger_types_in_arch"]
        
        # 5. 判断是否完整
        result["is_complete"] = (
            len(result["missing_workflows"]) == 0 and
            len(result["missing_trigger_types"]) == 0
        )
        
        return result

    def validate_statistics_consistency(
        self,
        ci_data: dict,
        statistics: dict,
        architecture: dict
    ) -> dict:
        """
        验证统计数据一致性
        
        检查 statistics 中的各项数据是否与 ci_data 和 architecture 一致。
        
        Args:
            ci_data: ci_data.json 内容
            statistics: _generate_statistics() 生成的统计数据
            architecture: architecture.json 内容
        
        Returns:
            {
                "workflow_count_match": bool,
                "trigger_distribution_match": bool,
                "layer_distribution_complete": bool,
                "issues": list[str],
            }
        """
        result = {
            "workflow_count_match": True,
            "trigger_distribution_match": True,
            "layer_distribution_complete": True,
            "issues": [],
        }
        
        # 1. 检查工作流总数
        actual_count = len(ci_data.get("workflows", {}))
        stats_count = statistics.get("workflow_count", 0)
        
        if actual_count != stats_count:
            result["workflow_count_match"] = False
            result["issues"].append(f"工作流数量不一致: 统计={stats_count}, 实际={actual_count}")
        
        # 2. 检查触发类型分布
        stats_triggers = statistics.get("trigger_distribution", {})
        
        # 从 ci_data 重新计算触发类型分布
        actual_triggers = {}
        for wf in ci_data.get("workflows", {}).values():
            for trigger in wf.get("triggers", []):
                actual_triggers[trigger] = actual_triggers.get(trigger, 0) + 1
        
        if stats_triggers != actual_triggers:
            result["trigger_distribution_match"] = False
            result["issues"].append("触发类型分布不一致")
        
        # 3. 检查层级分布是否完整
        layer_dist = statistics.get("layer_distribution", {})
        layer_total = sum(layer_dist.values())
        
        if layer_total != actual_count:
            result["layer_distribution_complete"] = False
            result["issues"].append(f"层级分布合计 ({layer_total}) ≠ 工作流总数 ({actual_count})")
        
        return result

    def validate_overview_accuracy(
        self,
        overview: str,
        ci_data: dict
    ) -> dict:
        """
        验证项目概述中的数量准确性
        
        检查概述中的工作流数量、Job 数量等是否与实际一致。
        
        Args:
            overview: 项目概述文本
            ci_data: ci_data.json 内容
        
        Returns:
            {
                "is_accurate": bool,
                "workflow_count_in_overview": int,
                "actual_workflow_count": int,
                "job_count_in_overview": int,
                "actual_job_count": int,
                "corrected_overview": str,
            }
        """
        result = {
            "is_accurate": True,
            "workflow_count_in_overview": None,
            "actual_workflow_count": 0,
            "job_count_in_overview": None,
            "actual_job_count": 0,
            "corrected_overview": overview,
        }
        
        # 实际数量
        workflows = ci_data.get("workflows", {})
        result["actual_workflow_count"] = len(workflows)
        
        job_count = 0
        for wf in workflows.values():
            job_count += len(wf.get("jobs", {}))
        result["actual_job_count"] = job_count
        
        if not overview:
            return result
        
        # 提取概述中的工作流数量
        workflow_match = re.search(r'工作流总数[：:]\s*(\d+)\s*个', overview)
        if workflow_match:
            result["workflow_count_in_overview"] = int(workflow_match.group(1))
            
            if result["workflow_count_in_overview"] != result["actual_workflow_count"]:
                result["is_accurate"] = False
                result["corrected_overview"] = re.sub(
                    r'工作流总数[：:]\s*\d+\s*个',
                    f'工作流总数：{result["actual_workflow_count"]} 个',
                    overview
                )
        
        # 提取概述中的 Job 数量
        job_match = re.search(r'Job[续總]数[：:]\s*(\d+)', overview)
        if job_match:
            result["job_count_in_overview"] = int(job_match.group(1))
            
            if result["job_count_in_overview"] != result["actual_job_count"]:
                result["is_accurate"] = False
                result["corrected_overview"] = re.sub(
                    r'Job[續總]数[：:]\s*\d+',
                    f'Job总数：{result["actual_job_count"]}',
                    result["corrected_overview"]
                )
        
        return result
