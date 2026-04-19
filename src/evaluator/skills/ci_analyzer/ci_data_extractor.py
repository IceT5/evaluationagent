#!/usr/bin/env python3
"""
CI Data Extractor - Extract comprehensive raw CI/CD data without classification

This module extracts detailed raw data from CI/CD configurations.
All classification and understanding should be done by LLM.
"""

import os
import re
import yaml
import json
from pathlib import Path
from typing import Dict, List, Set, Any, Tuple, Optional
from collections import defaultdict
from dataclasses import dataclass, field, asdict
import sys


# 文件类型定义
SCRIPT_EXTS = {'.py', '.sh', '.ps1', '.bat', '.groovy', '.jl', '.rb', '.pl'}
CONFIG_EXTS = {'.yaml', '.yml', '.json'}


@dataclass
class StepData:
    """Detailed step data."""
    name: str = ""
    id: str = ""
    uses: str = ""
    run: str = ""
    with_params: Dict[str, Any] = field(default_factory=dict)
    env: Dict[str, str] = field(default_factory=dict)
    if_condition: str = ""
    continue_on_error: bool = False
    timeout_minutes: int = 0
    working_directory: str = ""
    shell: str = ""


@dataclass
class JobData:
    """Detailed job data extracted from workflow."""
    name: str
    display_name: str = ""
    runs_on: str = ""
    needs: List[str] = field(default_factory=list)
    uses: str = ""  # For reusable workflow calls
    with_params: Dict[str, Any] = field(default_factory=dict)  # Inputs for reusable workflow
    steps: List[StepData] = field(default_factory=list)
    if_condition: str = ""
    matrix: Optional[Dict] = None
    matrix_configs: List[Dict[str, Any]] = field(default_factory=list)  # Expanded matrix configs
    env_vars: Dict[str, str] = field(default_factory=dict)
    outputs: Dict[str, str] = field(default_factory=dict)
    timeout_minutes: int = 0
    # Extracted relationships
    calls_workflows: List[str] = field(default_factory=list)
    calls_actions: List[str] = field(default_factory=list)


@dataclass
class WorkflowData:
    """Detailed workflow data without classification."""
    filename: str
    name: str
    path: str
    triggers: List[str] = field(default_factory=list)
    trigger_details: Dict[str, Any] = field(default_factory=dict)  # Detailed trigger config
    jobs: Dict[str, JobData] = field(default_factory=dict)
    env_vars: Dict[str, str] = field(default_factory=dict)
    concurrency: Dict[str, str] = field(default_factory=dict)
    raw_content: str = ""  # Full content for LLM context
    # Relationships
    callers: List[str] = field(default_factory=list)  # Who calls this workflow


@dataclass
class ActionData:
    """Detailed composite action data."""
    name: str
    path: str
    description: str = ""
    inputs: Dict[str, Dict] = field(default_factory=dict)  # name -> {description, required, default}
    outputs: Dict[str, Dict] = field(default_factory=dict)
    runs_steps: List[StepData] = field(default_factory=list)
    runs_using: str = ""  # composite, docker, node
    called_actions: List[str] = field(default_factory=list)
    used_by: List[str] = field(default_factory=list)


@dataclass
class ScriptCallRelation:
    """Script call relationship."""
    caller_script: str = ""
    called_script: str = ""
    call_type: str = ""  # source, import, subprocess, etc.
    line_number: int = 0


@dataclass
class ScriptData:
    """Detailed script data."""
    name: str
    path: str
    type: str  # .py, .sh, .ps1, .bat
    content: str = ""  # Full content for LLM analysis
    functions: List[str] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    called_by: List[str] = field(default_factory=list)  # Which workflows use this
    calls_scripts: List[str] = field(default_factory=list)  # Scripts this script calls
    call_relations: List[ScriptCallRelation] = field(default_factory=list)  # Detailed call info


@dataclass
class PreCommitHookData:
    """Pre-commit hook configuration."""
    id: str = ""
    repo: str = ""
    rev: str = ""
    additional_dependencies: List[str] = field(default_factory=list)
    args: List[str] = field(default_factory=list)
    files: str = ""
    exclude: str = ""
    language: str = ""
    description: str = ""


@dataclass
class PreCommitConfigData:
    """Complete pre-commit configuration."""
    path: str = ""
    default_stages: List[str] = field(default_factory=list)
    default_language_version: Dict[str, str] = field(default_factory=dict)
    ci: Dict[str, Any] = field(default_factory=dict)  # CI-specific settings like autofix_prs
    repos: List[PreCommitHookData] = field(default_factory=list)
    local_hooks: List[PreCommitHookData] = field(default_factory=list)  # Local repo hooks


@dataclass
class OtherCIConfigData:
    """Other CI system configuration data."""
    system: str = ""  # circleci, gitlab_ci, azure_pipelines, etc.
    path: str = ""
    content: str = ""
    parsed_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CIData:
    """Complete CI/CD raw data for LLM analysis."""
    repo_name: str
    repo_path: str
    workflows: Dict[str, WorkflowData] = field(default_factory=dict)
    actions: List[ActionData] = field(default_factory=list)
    scripts: List[ScriptData] = field(default_factory=list)
    pre_commit_configs: List[PreCommitConfigData] = field(default_factory=list)  # pre-commit configs
    other_ci_configs: List[OtherCIConfigData] = field(default_factory=list)  # CircleCI, GitLab CI, etc.
    # Jenkins/External CI
    jenkins_pipelines: List[Dict[str, Any]] = field(default_factory=list)  # Jenkins Groovy scripts
    external_ci_scripts: List[Dict[str, Any]] = field(default_factory=list)  # Scripts called by external CI
    # Raw relationship data
    workflow_call_graph: Dict[str, List[str]] = field(default_factory=dict)
    job_dependency_graph: Dict[str, List[str]] = field(default_factory=dict)
    action_usage_graph: Dict[str, List[str]] = field(default_factory=dict)
    # Command-to-script mappings
    command_script_mappings: Dict[str, List[str]] = field(default_factory=dict)  # command -> scripts
    # Metadata
    ci_directories: List[str] = field(default_factory=list)
    # Scripts directory mapping
    scripts_by_directory: Dict[str, List[str]] = field(default_factory=dict)


class CIDataExtractor:
    """Extract comprehensive raw CI/CD data without making classification decisions."""
    
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        self.repo_name = self.repo_path.name
        
    def extract_all(self) -> CIData:
        """Extract all CI/CD data from repository."""
        data = CIData(
            repo_name=self.repo_name,
            repo_path=str(self.repo_path)
        )
        
        # Find CI directories
        ci_dirs = self._find_ci_directories()
        data.ci_directories = list(ci_dirs.keys())
        
        # Extract workflows
        workflows_dir = ci_dirs.get("github_workflows")
        if workflows_dir and workflows_dir.exists():
            for wf_file in workflows_dir.glob("*.yml"):
                wf_data = self._extract_workflow(wf_file)
                if wf_data:
                    data.workflows[wf_file.name] = wf_data
            for wf_file in workflows_dir.glob("*.yaml"):
                wf_data = self._extract_workflow(wf_file)
                if wf_data:
                    data.workflows[wf_file.name] = wf_data
        
        # Extract actions
        actions_dir = ci_dirs.get("github_actions")
        if actions_dir and actions_dir.exists():
            for action_dir in actions_dir.iterdir():
                if action_dir.is_dir():
                    action_data = self._extract_action(action_dir)
                    if action_data:
                        data.actions.append(action_data)
        
        # Extract scripts with directory mapping
        data.scripts, data.scripts_by_directory = self._extract_scripts(ci_dirs)
        
        # Extract pre-commit configurations
        data.pre_commit_configs = self._extract_pre_commit_configs()
        
        # Extract other CI system configurations (CircleCI, GitLab CI, etc.)
        data.other_ci_configs = self._extract_other_ci_configs()
        
        # Extract Jenkins pipelines
        jenkins_dir = ci_dirs.get("jenkins")
        if jenkins_dir and jenkins_dir.exists():
            data.jenkins_pipelines = self._extract_jenkins_pipelines(jenkins_dir)
        
        # Build relationship graphs
        self._build_relationships(data)
        
        # Build command-to-script mappings
        self._build_command_mappings(data)
        
        # Identify external CI scripts
        self._identify_external_ci_scripts(data)
        
        return data
    
    def _find_ci_directories(self) -> Dict[str, Path]:
        """Find all CI-related directories."""
        patterns = [
            # GitHub Actions
            (".github/workflows", "github_workflows"),
            (".github/actions", "github_actions"),
            (".github/scripts", "github_scripts"),
            # Generic CI directories
            (".ci", "ci_dir"),
            (".circleci", "circleci"),
            ("ci", "ci_root"),
            # Scripts and tests
            ("scripts", "scripts"),
            ("test", "test"),
            ("tests", "tests"),
            # External CI systems
            ("jenkins", "jenkins"),
            (".jenkins", "jenkins_hidden"),
            ("Jenkinsfile", "jenkinsfile"),  # Jenkinsfile in root
        ]
        
        found = {}
        for pattern, key in patterns:
            path = self.repo_path / pattern
            if path.exists():
                found[key] = path
        
        return found
    
    def _extract_workflow(self, filepath: Path) -> Optional[WorkflowData]:
        """Extract detailed workflow data from YAML file."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            
            wf_data = yaml.safe_load(content)
            if not wf_data:
                return None
            
            # Handle 'on' as True (YAML keyword)
            if True in wf_data and "on" not in wf_data:
                wf_data["on"] = wf_data.pop(True)
            
            # Extract triggers with details
            triggers, trigger_details = self._extract_triggers(wf_data)
            
            # Extract jobs with full details
            jobs = self._extract_jobs(wf_data, filepath.name)
            
            # Extract workflow-level env
            env_vars = wf_data.get("env", {}) or {}
            
            # Extract concurrency config
            concurrency = wf_data.get("concurrency", {}) or {}
            if isinstance(concurrency, str):
                concurrency = {"group": concurrency}
            
            return WorkflowData(
                filename=filepath.name,
                name=wf_data.get("name", filepath.stem),
                path=str(filepath.relative_to(self.repo_path)),
                triggers=triggers,
                trigger_details=trigger_details,
                jobs=jobs,
                env_vars=env_vars if isinstance(env_vars, dict) else {},
                concurrency=concurrency if isinstance(concurrency, dict) else {},
                raw_content=content
            )
        except Exception as e:
            print(f"Error parsing {filepath}: {e}", file=sys.stderr)
            return None
    
    def _extract_triggers(self, wf_data: Dict) -> Tuple[List[str], Dict]:
        """Extract trigger events with details."""
        triggers = []
        trigger_details = {}
        on_config = wf_data.get("on", {})
        
        if isinstance(on_config, str):
            triggers = [on_config]
        elif isinstance(on_config, list):
            triggers = on_config
        elif isinstance(on_config, dict):
            triggers = list(on_config.keys())
            trigger_details = on_config
        
        return triggers, trigger_details
    
    def _extract_jobs(self, wf_data: Dict, workflow_name: str) -> Dict[str, JobData]:
        """Extract detailed job data."""
        jobs = {}
        
        for job_name, job_data in (wf_data.get("jobs", {}) or {}).items():
            if not isinstance(job_data, dict):
                continue
            
            # Extract steps with full details
            steps = self._extract_steps(job_data.get("steps", []))
            
            # Extract matrix with expanded configs
            matrix = None
            matrix_configs = []
            strategy = job_data.get("strategy", {})
            if isinstance(strategy, dict):
                matrix = strategy.get("matrix")
                if matrix:
                    matrix_configs = self._expand_matrix(matrix)
            
            # Extract environment variables
            env = job_data.get("env", {}) or {}
            env_vars = env if isinstance(env, dict) else {}
            
            # Extract outputs
            outputs = job_data.get("outputs", {}) or {}
            
            # Extract needs (dependencies)
            needs = job_data.get("needs", [])
            if isinstance(needs, str):
                needs = [needs]
            
            # Extract uses (for reusable workflows) with parameters
            uses = job_data.get("uses", "")
            with_params = job_data.get("with", {}) or {}
            
            # Find calls in this job
            calls_workflows = []
            calls_actions = []
            
            if uses:
                calls_workflows.append(uses)
            
            for step in steps:
                step_uses = step.uses
                if step_uses:
                    if step_uses.startswith("./.github/actions/"):
                        action_name = step_uses.replace("./.github/actions/", "").split("/")[0]
                        calls_actions.append(f"local:{action_name}")
                    elif step_uses.startswith("./.github/workflows/"):
                        calls_workflows.append(step_uses)
                    elif "/" in step_uses and not step_uses.startswith("./"):
                        calls_actions.append(step_uses)
            
            # Extract display name
            display_name = job_data.get("name", job_name)
            
            jobs[job_name] = JobData(
                name=job_name,
                display_name=display_name,
                runs_on=job_data.get("runs-on", ""),
                needs=needs,
                uses=uses,
                with_params=with_params if isinstance(with_params, dict) else {},
                steps=steps,
                if_condition=str(job_data.get("if", "")),
                matrix=matrix,
                matrix_configs=matrix_configs,
                env_vars=env_vars,
                outputs=outputs if isinstance(outputs, dict) else {},
                timeout_minutes=job_data.get("timeout-minutes", 0),
                calls_workflows=calls_workflows,
                calls_actions=calls_actions
            )
        
        return jobs
    
    def _extract_steps(self, steps_data: List) -> List[StepData]:
        """Extract detailed step data."""
        steps = []
        for step in steps_data:
            if not isinstance(step, dict):
                continue
            
            with_params = step.get("with", {}) or {}
            env = step.get("env", {}) or {}
            
            steps.append(StepData(
                name=step.get("name", ""),
                id=step.get("id", ""),
                uses=step.get("uses", ""),
                run=step.get("run", ""),  # Keep full content, no truncation
                with_params=with_params if isinstance(with_params, dict) else {},
                env=env if isinstance(env, dict) else {},
                if_condition=str(step.get("if", "")),
                continue_on_error=step.get("continue-on-error", False),
                timeout_minutes=step.get("timeout-minutes", 0),
                working_directory=step.get("working-directory", ""),
                shell=step.get("shell", "")
            ))
        
        return steps
    
    def _expand_matrix(self, matrix: Dict) -> List[Dict[str, Any]]:
        """Expand matrix to list of all possible configurations.
        
        This method expands the matrix to show ALL possible job combinations,
        which is critical for understanding the full CI/CD pipeline.
        
        For dynamic matrices (fromJson, fromJSON, expressions), we preserve
        the full expression for LLM analysis instead of truncating.
        """
        import itertools
        
        configs = []
        dynamic_expressions = {}  # Track dynamic expressions for LLM analysis
        
        if not isinstance(matrix, dict):
            return configs
        
        # Handle include first - these are explicit configurations
        includes = matrix.get("include", [])
        if includes:
            for item in includes:
                if isinstance(item, dict):
                    configs.append(item)
        
        # Get all dimension keys (excluding include and exclude)
        dimension_keys = [k for k in matrix.keys() if k not in ["include", "exclude"]]
        
        # Get exclude patterns
        excludes = matrix.get("exclude", [])
        
        if dimension_keys:
            # Build dimension value lists
            dimension_values = {}
            for key in dimension_keys:
                values = matrix.get(key, [])
                if isinstance(values, list) and values:
                    # Check for dynamic expressions in list items
                    processed_values = []
                    for v in values:
                        if isinstance(v, str) and v.startswith("${{"):
                            # Preserve full dynamic expression
                            processed_values.append(v)
                            dynamic_expressions[f"{key}::{v[:30]}..."] = v
                        else:
                            processed_values.append(v)
                    dimension_values[key] = processed_values
                elif isinstance(values, str):
                    # Handle string references like ${{ fromJson(...) }}
                    # Preserve FULL expression for LLM analysis (no truncation)
                    full_expr = values
                    if "${{" in full_expr:
                        dynamic_expressions[key] = full_expr
                        # Mark as dynamic - LLM should analyze
                        dimension_values[key] = [f"<DYNAMIC_EXPRESSION>{full_expr}</DYNAMIC_EXPRESSION>"]
                    else:
                        dimension_values[key] = [values]
            
            # Generate all combinations
            if dimension_values:
                keys = list(dimension_values.keys())
                value_lists = [dimension_values[k] for k in keys]
                
                for combo in itertools.product(*value_lists):
                    config = dict(zip(keys, combo))
                    
                    # Check if this config is excluded
                    is_excluded = False
                    for exclude_pattern in excludes:
                        if isinstance(exclude_pattern, dict):
                            # Check if all exclude conditions match
                            match = True
                            for k, v in exclude_pattern.items():
                                if config.get(k) != v:
                                    match = False
                                    break
                            if match:
                                is_excluded = True
                                break
                    
                    if not is_excluded:
                        configs.append(config)
        
        # If we found dynamic expressions, add metadata for LLM analysis
        if dynamic_expressions and configs:
            # Add a special config entry with dynamic expression info
            for config in configs:
                if "<DYNAMIC_EXPRESSION>" in str(config.values()):
                    # Add metadata about dynamic nature
                    config["_dynamic_expressions"] = dynamic_expressions
                    config["_note"] = "Matrix contains dynamic expressions - analyze parent workflow for actual values"
        
        return configs  # Return ALL configs, no limit
    
    def _extract_action(self, action_dir: Path) -> Optional[ActionData]:
        """Extract detailed action data."""
        action_file = action_dir / "action.yml"
        if not action_file.exists():
            action_file = action_dir / "action.yaml"
        
        if not action_file.exists():
            return None
        
        try:
            with open(action_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            
            # Extract inputs with details
            inputs = {}
            for name, inp in (data.get("inputs", {}) or {}).items():
                if isinstance(inp, dict):
                    inputs[name] = {
                        "description": inp.get("description", ""),
                        "required": inp.get("required", False),
                        "default": inp.get("default", "")
                    }
            
            # Extract outputs
            outputs = {}
            for name, out in (data.get("outputs", {}) or {}).items():
                if isinstance(out, dict):
                    outputs[name] = {
                        "description": out.get("description", ""),
                        "value": out.get("value", "")
                    }
            
            # Extract steps
            runs = data.get("runs", {})
            steps = []
            called_actions = []
            
            if isinstance(runs, dict):
                steps = self._extract_steps(runs.get("steps", []))
                for step in steps:
                    if step.uses:
                        called_actions.append(step.uses)
            
            return ActionData(
                name=action_dir.name,
                path=str(action_dir.relative_to(self.repo_path)),
                description=data.get("description", ""),
                inputs=inputs,
                outputs=outputs,
                runs_steps=steps,
                runs_using=runs.get("using", "") if isinstance(runs, dict) else "",
                called_actions=called_actions
            )
        except Exception as e:
            print(f"Error parsing action {action_dir}: {e}", file=sys.stderr)
            return None
    
    def _extract_scripts(self, ci_dirs: Dict[str, Path]) -> Tuple[List[ScriptData], Dict[str, List[str]]]:
        """Extract script information with directory mapping and nested call tracking.
        
        根据目录类型应用不同的提取策略：
        - tests 目录：只提取 README.md 内容，其他文件只记录结构
        - scripts 目录：提取 README.md + 脚本文件 + 配置文件，其他文件只记录结构
        - 其他目录：保持原有逻辑（全部提取）
        """
        scripts = []
        scripts_by_dir = defaultdict(list)
        seen = {}  # name -> ScriptData (for lookup)
        script_paths = {}  # name -> full path (for resolution)
        
        for dir_key, path in ci_dirs.items():
            if not isinstance(path, Path) or not path.exists():
                continue
            
            # 判断目录类型
            is_tests = dir_key in ["tests", "test"]
            is_scripts = dir_key == "scripts"
            
            for f in path.rglob("*"):
                if not f.is_file():
                    continue
                
                # Use relative path as key to avoid same-name files in different directories
                rel_path = str(f.relative_to(self.repo_path))
                if rel_path in seen:
                    continue
                
                path_str = str(f).replace("\\", "/")
                # Skip workflow files (they are already parsed separately)
                if ".github/workflows/" in path_str and f.suffix in [".yaml", ".yml"]:
                    continue
                
                if f.stat().st_size > 1024 * 1024:
                    continue
                
                # 判断文件类型
                is_readme = f.name.lower() == "readme.md"
                is_script = f.suffix in SCRIPT_EXTS
                is_config = f.suffix in CONFIG_EXTS
                
                # 根据目录类型决定是否读取内容
                include_content = True
                
                if is_tests:
                    # tests 目录：只提取 README.md 内容
                    include_content = is_readme
                elif is_scripts:
                    # scripts 目录：提取 README.md + 脚本 + 配置
                    include_content = is_readme or is_script or is_config
                # 其他目录：保持原有逻辑（全部提取）
                
                try:
                    if include_content:
                        with open(f, "r", encoding="utf-8", errors="ignore") as fp:
                            content = fp.read()
                        
                        if "\x00" in content:
                            continue
                    else:
                        content = ""
                    
                    functions = []
                    imports = []
                    if include_content:
                        if f.suffix == ".py":
                            func_pattern = r'^def\s+(\w+)\s*\('
                            functions = re.findall(func_pattern, content, re.MULTILINE)
                            import_pattern = r'^(?:import|from)\s+(\S+)'
                            imports = re.findall(import_pattern, content, re.MULTILINE)
                        elif f.suffix == ".sh":
                            func_pattern = r'^(?:function\s+)?(\w+)\s*\(\s*\)\s*\{'
                            functions = re.findall(func_pattern, content, re.MULTILINE)
                    
                    script = ScriptData(
                        name=f.name,
                        path=rel_path,
                        type=f.suffix,
                        content=content,
                        functions=functions,
                        imports=imports
                    )
                    scripts.append(script)
                    seen[rel_path] = script
                    script_paths[f.name] = f
                    
                    rel_dir = str(f.parent.relative_to(self.repo_path))
                    scripts_by_dir[rel_dir].append(f.name)
                    
                except Exception:
                    pass
        
        self._analyze_script_calls(scripts, script_paths)
        
        return scripts, dict(scripts_by_dir)
    
    def _analyze_script_calls(self, scripts: List[ScriptData], script_paths: Dict[str, Path]):
        """Analyze nested script calls within each script."""
        script_names = set(script_paths.keys())
        
        # Phase 1: Extract variable definitions that contain script names
        var_to_scripts = {}  # script_name -> {var_name: [script_names]}
        for script in scripts:
            var_to_scripts[script.name] = self._extract_script_variables(script)
        
        # Phase 2: Analyze direct and variable-based script calls
        for script in scripts:
            content = script.content
            lines = content.split('\n')
            
            if script.type == ".sh":
                # Shell script: source, ., ./script.sh, bash script.sh
                for i, line in enumerate(lines, 1):
                    line_stripped = line.strip()
                    
                    # Skip comments
                    if line_stripped.startswith('#'):
                        continue
                    
                    # source or . command
                    source_match = re.match(r'^(?:source|\.)\s+(.+?)(?:\s|$)', line_stripped)
                    if source_match:
                        called = source_match.group(1).strip('"\'')
                        # Resolve the called script name
                        called_name = Path(called).name
                        if called_name in script_names and called_name != script.name:
                            script.calls_scripts.append(called_name)
                            script.call_relations.append(ScriptCallRelation(
                                caller_script=script.name,
                                called_script=called_name,
                                call_type="source",
                                line_number=i
                            ))
                    
                    # Direct script execution: ./script.sh, bash script.sh, sh script.sh
                    exec_match = re.match(r'^(?:bash|sh|zsh|\.\/)\s*(.+?)(?:\s|$)', line_stripped)
                    if exec_match:
                        called = exec_match.group(1).strip('"\'')
                        if called.startswith('./'):
                            called = called[2:]
                        called_name = Path(called).name
                        if called_name in script_names and called_name != script.name:
                            script.calls_scripts.append(called_name)
                            script.call_relations.append(ScriptCallRelation(
                                caller_script=script.name,
                                called_script=called_name,
                                call_type="execute",
                                line_number=i
                            ))
            
            elif script.type == ".py":
                # Python: import, from, subprocess, os.system, os.popen
                for i, line in enumerate(lines, 1):
                    line_stripped = line.strip()
                    
                    # Skip comments
                    if line_stripped.startswith('#'):
                        continue
                    
                    # import module (local modules)
                    import_match = re.match(r'^import\s+(\w+)', line_stripped)
                    if import_match:
                        module_name = import_match.group(1)
                        # Check if it's a local .py file
                        called_name = f"{module_name}.py"
                        if called_name in script_names and called_name != script.name:
                            script.calls_scripts.append(called_name)
                            script.call_relations.append(ScriptCallRelation(
                                caller_script=script.name,
                                called_script=called_name,
                                call_type="import",
                                line_number=i
                            ))
                    
                    # from module import ...
                    from_match = re.match(r'^from\s+(\w+)', line_stripped)
                    if from_match:
                        module_name = from_match.group(1)
                        called_name = f"{module_name}.py"
                        if called_name in script_names and called_name != script.name:
                            script.calls_scripts.append(called_name)
                            script.call_relations.append(ScriptCallRelation(
                                caller_script=script.name,
                                called_script=called_name,
                                call_type="from_import",
                                line_number=i
                            ))
                    
                    # subprocess.run/call/Popen with script
                    subprocess_patterns = [
                        r'subprocess\.(?:run|call|Popen)\s*\(\s*["\']([^"\']+\.sh)["\']',
                        r'subprocess\.(?:run|call|Popen)\s*\(\s*\[["\']([^"\']+\.sh)["\']',
                        r'os\.system\s*\(\s*["\']([^"\']+\.sh)["\']',
                        r'os\.popen\s*\(\s*["\']([^"\']+\.sh)["\']',
                    ]
                    for pattern in subprocess_patterns:
                        match = re.search(pattern, line_stripped)
                        if match:
                            called = match.group(1)
                            called_name = Path(called).name
                            if called_name in script_names and called_name != script.name:
                                script.calls_scripts.append(called_name)
                                script.call_relations.append(ScriptCallRelation(
                                    caller_script=script.name,
                                    called_script=called_name,
                                    call_type="subprocess",
                                    line_number=i
                                ))
            
            elif script.type == ".ps1":
                # PowerShell: .\script.ps1, & ".\script.ps1", . source.ps1
                for i, line in enumerate(lines, 1):
                    line_stripped = line.strip()
                    
                    if line_stripped.startswith('#'):
                        continue
                    
                    # .\script.ps1 or & ".\script.ps1"
                    ps_patterns = [
                        r'\.\s*[\\/]?([^\\/\s]+\.ps1)',
                        r'&\s*["\']?[.\\/]*([^"\'\\/\s]+\.ps1)',
                    ]
                    for pattern in ps_patterns:
                        match = re.search(pattern, line_stripped)
                        if match:
                            called_name = match.group(1)
                            if called_name in script_names and called_name != script.name:
                                script.calls_scripts.append(called_name)
                                script.call_relations.append(ScriptCallRelation(
                                    caller_script=script.name,
                                    called_script=called_name,
                                    call_type="dot_source",
                                    line_number=i
                                ))
            
            elif script.type == ".bat":
                # Batch: call script.bat, script.bat
                for i, line in enumerate(lines, 1):
                    line_stripped = line.strip()
                    
                    if line_stripped.startswith('::') or line_stripped.startswith('REM'):
                        continue
                    
                    # call script.bat or direct script.bat
                    bat_match = re.match(r'(?:call\s+)?([^\s]+\.bat)', line_stripped, re.IGNORECASE)
                    if bat_match:
                        called_name = bat_match.group(1)
                        if called_name in script_names and called_name != script.name:
                            script.calls_scripts.append(called_name)
                            script.call_relations.append(ScriptCallRelation(
                                caller_script=script.name,
                                called_script=called_name,
                                call_type="call",
                                line_number=i
                            ))
            
            # Remove duplicates
            script.calls_scripts = list(set(script.calls_scripts))
            
            # Phase 3: Analyze variable-based script calls
            self._analyze_variable_calls(script, var_to_scripts.get(script.name, {}), script_names)
    
    def _extract_script_variables(self, script: ScriptData) -> Dict[str, List[str]]:
        """Extract variable definitions that contain script names (generic)."""
        var_to_scripts = {}
        content = script.content
        
        if script.type == ".sh":
            # Match variable definition lines
            var_def_pattern = r'(\w+)=(.+)'
            
            for match in re.finditer(var_def_pattern, content):
                var_name = match.group(1)
                def_value = match.group(2)
                
                # Skip if not a valid variable name
                if not var_name or var_name.startswith('_'):
                    continue
                
                script_refs = []
                
                # Pattern 1: Direct script file reference (var="script.sh")
                direct_refs = re.findall(r'["\']([^"\']+\.(?:sh|py))["\']', def_value)
                script_refs.extend(direct_refs)
                
                # Pattern 2: Script file in command substitution (var=$(...script.sh...))
                cmd_subst_refs = re.findall(r'\$\([^)]*([^)\s"\']+\.(?:sh|py))[^)]*\)', def_value)
                script_refs.extend(cmd_subst_refs)
                
                # Pattern 3: sed replacement pattern (sed 's/old.sh/new.sh/' or sed "s/old.sh/new.sh/")
                # This is a generic pattern for sed substitution
                sed_patterns = [
                    r"sed\s+['\"]s/[^/]+/([^/]+)/['\"]",
                    r"sed\s+['\"]s/[^/]+/([^/]+)/g['\"]",
                ]
                for sed_pat in sed_patterns:
                    for sed_match in re.finditer(sed_pat, def_value):
                        replacement = sed_match.group(1)
                        if replacement.endswith(('.sh', '.py')):
                            script_refs.append(replacement)
                
                # Build mapping
                if script_refs:
                    if var_name not in var_to_scripts:
                        var_to_scripts[var_name] = []
                    for script_ref in script_refs:
                        script_name = Path(script_ref).name
                        if script_name not in var_to_scripts[var_name]:
                            var_to_scripts[var_name].append(script_name)
        
        elif script.type == ".py":
            # Python variable definitions (generic patterns)
            # var = "script.sh", var = os.path.join(dir, "script.sh")
            patterns = [
                r'(\w+)\s*=\s*["\']([^"\']+\.(?:sh|py))["\']',
            ]
            for pattern in patterns:
                for match in re.finditer(pattern, content):
                    var_name = match.group(1)
                    script_ref = match.group(2)
                    script_name = Path(script_ref).name
                    if var_name not in var_to_scripts:
                        var_to_scripts[var_name] = []
                    if script_name not in var_to_scripts[var_name]:
                        var_to_scripts[var_name].append(script_name)
        
        return var_to_scripts
    
    def _analyze_variable_calls(self, script: ScriptData, var_to_scripts: Dict[str, List[str]], script_names: Set[str]):
        """Analyze variable-based script calls (generic)."""
        if not var_to_scripts:
            return
        
        content = script.content
        
        if script.type == ".sh":
            # Shell variable references (generic patterns)
            # source "$var", . "$var", bash "$var"
            patterns = [
                r'(?:source|\.)\s+["\']?\$(\w+)',
                r'(?:bash|sh)\s+["\']?\$(\w+)',
            ]
            for pattern in patterns:
                for match in re.finditer(pattern, content):
                    var_name = match.group(1)
                    if var_name in var_to_scripts:
                        for called_script in var_to_scripts[var_name]:
                            if called_script in script_names and called_script != script.name:
                                if called_script not in script.calls_scripts:
                                    script.calls_scripts.append(called_script)
        
        elif script.type == ".py":
            # Python variable references (generic patterns)
            # subprocess.run([var]), os.system(var)
            patterns = [
                r'subprocess\.(?:run|call|Popen)\s*\(\s*["\']?\$(\w+)',
                r'os\.system\s*\(\s*["\']?\$(\w+)',
            ]
            for pattern in patterns:
                for match in re.finditer(pattern, content):
                    var_name = match.group(1)
                    if var_name in var_to_scripts:
                        for called_script in var_to_scripts[var_name]:
                            if called_script in script_names and called_script != script.name:
                                if called_script not in script.calls_scripts:
                                    script.calls_scripts.append(called_script)
    
    def _extract_pre_commit_configs(self) -> List[PreCommitConfigData]:
        """Extract pre-commit configuration from .pre-commit-config.yaml files."""
        configs = []
        
        # Common pre-commit config file locations
        config_paths = [
            self.repo_path / ".pre-commit-config.yaml",
            self.repo_path / ".pre-commit-config.yml",
            self.repo_path / ".pre-commit-config" / "config.yaml",
        ]
        
        for config_path in config_paths:
            if not config_path.exists():
                continue
            
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                
                config = PreCommitConfigData(
                    path=str(config_path.relative_to(self.repo_path))
                )
                
                # Extract default stages
                config.default_stages = data.get("default_stages", [])
                
                # Extract default language version
                config.default_language_version = data.get("default_language_version", {})
                
                # Extract CI settings
                config.ci = data.get("ci", {})
                
                # Extract repos and hooks
                repos = data.get("repos", [])
                for repo_data in repos:
                    if not isinstance(repo_data, dict):
                        continue
                    
                    repo_url = repo_data.get("repo", "")
                    rev = repo_data.get("rev", "")
                    hooks = repo_data.get("hooks", [])
                    
                    for hook in hooks:
                        if not isinstance(hook, dict):
                            continue
                        
                        hook_data = PreCommitHookData(
                            id=hook.get("id", ""),
                            repo=repo_url,
                            rev=rev,
                            additional_dependencies=hook.get("additional_dependencies", []),
                            args=hook.get("args", []),
                            files=hook.get("files", ""),
                            exclude=hook.get("exclude", ""),
                            language=hook.get("language", ""),
                            description=hook.get("description", "")
                        )
                        
                        # Check if it's a local hook (repo == "local")
                        if repo_url == "local":
                            config.local_hooks.append(hook_data)
                        else:
                            config.repos.append(hook_data)
                
                configs.append(config)
                
            except Exception as e:
                print(f"Error parsing pre-commit config {config_path}: {e}", file=sys.stderr)
        
        return configs
    
    def _extract_other_ci_configs(self) -> List[OtherCIConfigData]:
        """Extract other CI system configurations (CircleCI, GitLab CI, Azure Pipelines, etc.)."""
        configs = []
        
        # Define CI config file patterns
        ci_config_patterns = [
            # CircleCI
            (".circleci/config.yml", "circleci"),
            (".circleci/config.yaml", "circleci"),
            # GitLab CI
            (".gitlab-ci.yml", "gitlab_ci"),
            (".gitlab-ci.yaml", "gitlab_ci"),
            # Azure Pipelines
            ("azure-pipelines.yml", "azure_pipelines"),
            ("azure-pipelines.yaml", "azure_pipelines"),
            (".azure-pipelines.yml", "azure_pipelines"),
            (".azure-pipelines.yaml", "azure_pipelines"),
            # Jenkins
            ("Jenkinsfile", "jenkins"),
            ("jenkins/Jenkinsfile", "jenkins"),
            # Travis CI
            (".travis.yml", "travis_ci"),
            (".travis.yaml", "travis_ci"),
            # AppVeyor
            (".appveyor.yml", "appveyor"),
            (".appveyor.yaml", "appveyor"),
            # Bitbucket Pipelines
            ("bitbucket-pipelines.yml", "bitbucket_pipelines"),
            ("bitbucket-pipelines.yaml", "bitbucket_pipelines"),
            # Buildkite
            ("buildkite.yml", "buildkite"),
            ("buildkite.yaml", "buildkite"),
            (".buildkite/pipeline.yml", "buildkite"),
            # Drone CI
            (".drone.yml", "drone_ci"),
            (".drone.yaml", "drone_ci"),
            # .ci directory
            (".ci/config.yml", "ci_dir"),
            (".ci/config.yaml", "ci_dir"),
            (".ci/pipeline.yml", "ci_dir"),
            (".ci/pipeline.yaml", "ci_dir"),
            # Makefile (common for build automation)
            ("Makefile", "makefile"),
            # Tox
            ("tox.ini", "tox"),
            # pyproject.toml (may contain CI-related configs)
            ("pyproject.toml", "pyproject"),
        ]
        
        for pattern, system in ci_config_patterns:
            config_path = self.repo_path / pattern
            if not config_path.exists():
                continue
            
            try:
                with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                
                parsed_data = {}
                
                # Parse YAML files
                if pattern.endswith((".yml", ".yaml")):
                    try:
                        parsed_data = yaml.safe_load(content) or {}
                    except:
                        pass
                # Parse INI files
                elif pattern.endswith(".ini"):
                    try:
                        import configparser
                        parser = configparser.ConfigParser()
                        parser.read_string(content)
                        for section in parser.sections():
                            parsed_data[section] = dict(parser.items(section))
                    except:
                        pass
                # Parse TOML files
                elif pattern.endswith(".toml"):
                    try:
                        import tomllib
                        parsed_data = tomllib.loads(content)
                    except ImportError:
                        # Fallback for older Python versions
                        try:
                            import toml
                            parsed_data = toml.loads(content)
                        except:
                            pass
                
                config = OtherCIConfigData(
                    system=system,
                    path=str(config_path.relative_to(self.repo_path)),
                    content=content,  # Full content
                    parsed_data=parsed_data
                )
                configs.append(config)
                
            except Exception as e:
                print(f"Error parsing CI config {config_path}: {e}", file=sys.stderr)
        
        # 通配识别 ci/ 和 .ci/ 目录下的自定义配置文件
        for dir_name in ["ci", ".ci"]:
            dir_path = self.repo_path / dir_name
            if not dir_path.exists():
                continue
            
            for ext in ["*.yaml", "*.yml"]:
                for config_file in dir_path.glob(ext):
                    # 排除已处理的标准配置
                    if config_file.name in ["config.yml", "config.yaml", "pipeline.yml", "pipeline.yaml"]:
                        continue
                    
                    try:
                        with open(config_file, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                        
                        parsed_data = {}
                        try:
                            parsed_data = yaml.safe_load(content) or {}
                        except:
                            pass
                        
                        config = OtherCIConfigData(
                            system="custom_ci",
                            path=str(config_file.relative_to(self.repo_path)),
                            content=content,
                            parsed_data=parsed_data
                        )
                        configs.append(config)
                        
                    except Exception as e:
                        print(f"Error parsing custom CI config {config_file}: {e}", file=sys.stderr)
        
        return configs
    
    def _build_relationships(self, data: CIData):
        """Build relationship graphs from extracted data."""
        # Workflow call graph
        for wf_name, wf in data.workflows.items():
            callers = []
            for job_name, job in wf.jobs.items():
                for called_wf in job.calls_workflows:
                    if called_wf not in data.workflow_call_graph:
                        data.workflow_call_graph[called_wf] = []
                    data.workflow_call_graph[called_wf].append(f"{wf_name}::{job_name}")
        
        # Job dependency graph
        for wf_name, wf in data.workflows.items():
            for job_name, job in wf.jobs.items():
                key = f"{wf_name}::{job_name}"
                if job.needs:
                    data.job_dependency_graph[key] = job.needs
        
        # Action usage graph
        action_map = {f"local:{a.name}": a for a in data.actions}
        for wf_name, wf in data.workflows.items():
            for job_name, job in wf.jobs.items():
                for called_action in job.calls_actions:
                    if called_action not in data.action_usage_graph:
                        data.action_usage_graph[called_action] = []
                    data.action_usage_graph[called_action].append(f"{wf_name}::{job_name}")
                    
                    # Track local action usage
                    if called_action.startswith("local:") and called_action in action_map:
                        action_map[called_action].used_by.append(f"{wf_name}::{job_name}")
        
        # Track script usage in workflows
        script_names = {s.name: s for s in data.scripts}
        for wf_name, wf in data.workflows.items():
            for job_name, job in wf.jobs.items():
                for step in job.steps:
                    run_script = step.run
                    if run_script:
                        for script_name, script in script_names.items():
                            if script_name in run_script:
                                script.called_by.append(f"{wf_name}::{job_name}")
    
    def _extract_jenkins_pipelines(self, jenkins_dir: Path) -> List[Dict[str, Any]]:
        """Extract Jenkins pipeline scripts (Groovy)."""
        pipelines = []
        
        # Find all Groovy files
        for groovy_file in jenkins_dir.rglob("*.groovy"):
            try:
                with open(groovy_file, "r", encoding="utf-8") as f:
                    content = f.read()
                
                # Extract key information from Groovy script
                pipeline_info = {
                    "name": groovy_file.name,
                    "path": str(groovy_file.relative_to(self.repo_path)),
                    "type": "groovy",
                    "content": content,
                    "size": len(content),
                    # Extract shared libraries
                    "shared_libraries": self._extract_groovy_libraries(content),
                    # Extract stage names
                    "stages": self._extract_groovy_stages(content),
                    # Extract function calls
                    "function_calls": self._extract_groovy_function_calls(content),
                    # Extract environment variables
                    "env_vars": self._extract_groovy_env_vars(content),
                }
                pipelines.append(pipeline_info)
            except Exception as e:
                print(f"Error reading {groovy_file}: {e}", file=sys.stderr)
        
        return pipelines
    
    def _extract_groovy_libraries(self, content: str) -> List[str]:
        """Extract @Library annotations from Groovy script."""
        libraries = []
        # Match @Library(['lib1', 'lib2']) or @Library('lib')
        pattern = r"@Library\s*\(\s*\[?([^\]]+)\]?\s*\)"
        for match in re.finditer(pattern, content):
            libs_str = match.group(1)
            # Extract library names
            for lib_match in re.finditer(r"'([^']+)'|\"([^\"]+)\"", libs_str):
                lib = lib_match.group(1) or lib_match.group(2)
                if lib:
                    libraries.append(lib)
        return libraries
    
    def _extract_groovy_stages(self, content: str) -> List[str]:
        """Extract stage names from Groovy script."""
        stages = []
        # Match stage('name') or stage("name")
        pattern = r"stage\s*\(\s*'([^']+)'|stage\s*\(\s*\"([^\"]+)\""
        for match in re.finditer(pattern, content):
            stage = match.group(1) or match.group(2)
            if stage:
                stages.append(stage)
        return stages
    
    def _extract_groovy_function_calls(self, content: str) -> List[str]:
        """Extract function/method calls from Groovy script."""
        calls = []
        # Match function calls like blossom-ci, sh, bat, etc.
        patterns = [
            r"\b(blossom-ci|blossom\s+ci|jenkins|sh|bat|powershell|node|parallel)\b",
            r"(\w+)\s*\(",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, content):
                call = match.group(1)
                if call and call not in calls and not call.startswith('//'):
                    calls.append(call)
        return calls[:20]  # Limit to avoid noise
    
    def _extract_groovy_env_vars(self, content: str) -> List[str]:
        """Extract environment variable references from Groovy script."""
        env_vars = []
        # Match env.VAR or ${VAR} or $VAR
        patterns = [
            r"\benv\.(\w+)",
            r"\$\{(\w+)\}",
            r"\$(\w+)",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, content):
                var = match.group(1)
                if var and var not in env_vars and len(var) > 2:
                    env_vars.append(var)
        return env_vars[:30]  # Limit to avoid noise
    
    def _build_command_mappings(self, data: CIData):
        """Build mappings from run commands to scripts."""
        # Common command patterns that might reference scripts
        command_patterns = [
            # Python scripts
            (r"python\s+([^\s;|&]+\.py)", "python"),
            (r"python3\s+([^\s;|&]+\.py)", "python3"),
            # Shell scripts
            (r"bash\s+([^\s;|&]+\.sh)", "bash"),
            (r"sh\s+([^\s;|&]+\.sh)", "sh"),
            (r"\./([^\s;|&]+\.sh)", "direct_sh"),
            (r"\./([^\s;|&]+\.py)", "direct_py"),
            # Generic script references
            (r"([^\s;|&]+\.(?:py|sh|ps1|bat))", "script"),
        ]
        
        # Build script lookup
        script_lookup = {}
        for script in data.scripts:
            script_lookup[script.name] = script
            # Also add by path
            script_lookup[str(Path(script.path).name)] = script
        
        # Scan all run commands
        for wf_name, wf in data.workflows.items():
            for job_name, job in wf.jobs.items():
                for step in job.steps:
                    if step.run:
                        self._map_run_to_scripts(step.run, script_lookup, data.command_script_mappings, wf_name, job_name)
    
    def _map_run_to_scripts(self, run_content: str, script_lookup: Dict, mappings: Dict, wf_name: str, job_name: str):
        """Map a run command to scripts."""
        # Common command patterns
        patterns = [
            r"python\s+([^\s;|&`'\"]+\.py)",
            r"python3\s+([^\s;|&`'\"]+\.py)",
            r"bash\s+([^\s;|&`'\"]+\.sh)",
            r"sh\s+([^\s;|&`'\"]+\.sh)",
            r"\./([^\s;|&`'\"]+\.(?:py|sh))",
            r"([^\s;|&`'\"]+\.(?:py|sh))",
        ]
        
        for pattern in patterns:
            for match in re.finditer(pattern, run_content):
                script_ref = match.group(1)
                # Clean up the reference
                script_ref = script_ref.strip('\'"')
                
                # Try to find matching script
                script_name = Path(script_ref).name
                if script_name in script_lookup:
                    script = script_lookup[script_name]
                    # Add to mappings
                    if script_ref not in mappings:
                        mappings[script_ref] = []
                    mapping_entry = f"{wf_name}::{job_name}"
                    if mapping_entry not in mappings[script_ref]:
                        mappings[script_ref].append(mapping_entry)
                    # Also update script's called_by
                    if mapping_entry not in script.called_by:
                        script.called_by.append(mapping_entry)
    
    def _identify_external_ci_scripts(self, data: CIData):
        """Identify scripts that are likely called by external CI systems."""
        # Scripts that are not called by GitHub Actions but might be called by external CI
        external_ci_indicators = [
            # Jenkins-related patterns
            "jenkins", "blossom", "ci_server", "artifact", "upload", "deploy",
            # Build-related patterns
            "build", "compile", "package", "wheel", "docker", "image",
            # Test-related patterns
            "test", "l0", "l1", "e2e", "integration", "benchmark",
        ]
        
        # Find scripts not called by GitHub Actions
        for script in data.scripts:
            if not script.called_by:
                # Check if script name or path contains external CI indicators
                script_lower = (script.name + script.path).lower()
                for indicator in external_ci_indicators:
                    if indicator in script_lower:
                        data.external_ci_scripts.append({
                            "name": script.name,
                            "path": script.path,
                            "type": script.type,
                            "likely_called_by": "external_ci",
                            "indicator": indicator,
                        })
                        break
        
        # Also check Jenkins pipelines for script references
        script_names = {s.name: s for s in data.scripts}
        for pipeline in data.jenkins_pipelines:
            content = pipeline.get("content", "")
            pipeline_name = pipeline["name"]
            
            # Find script references in Groovy using multiple patterns
            # Pattern 1: Direct script file references in strings
            script_refs = set()
            script_ref_patterns = [
                r'["\']([^"\']+\.(?:sh|py|ps1|bat))["\']',
                r'sh\s*\(["\']([^"\']+)["\']',
                r'bat\s*\(["\']([^"\']+)["\']',
            ]
            for pattern in script_ref_patterns:
                for match in re.finditer(pattern, content):
                    script_ref = match.group(1)
                    script_refs.add(Path(script_ref).name)
            
            # Pattern 2: Check script name/path in content (fallback)
            for script in data.scripts:
                if script.name in content or script.path in content:
                    script_refs.add(script.name)
            
            # Update called_by and external_ci_scripts
            for script_name in script_refs:
                if script_name in script_names:
                    script = script_names[script_name]
                    jenkins_ref = f"jenkins:{pipeline_name}"
                    
                    # Update called_by
                    if jenkins_ref not in script.called_by:
                        script.called_by.append(jenkins_ref)
                    
                    # Add to external_ci_scripts if not already there
                    existing = any(
                        e.get("name") == script.name and e.get("likely_called_by") == jenkins_ref
                        for e in data.external_ci_scripts
                    )
                    if not existing:
                        data.external_ci_scripts.append({
                            "name": script.name,
                            "path": script.path,
                            "type": script.type,
                            "likely_called_by": jenkins_ref,
                            "indicator": "jenkins_reference",
                        })
        
        # Phase 3: Identify workflow → external CI → Jenkins call chain
        self._link_workflows_to_jenkins(data)
        
        # Phase 4: Extract Jenkins info from other_ci_configs
        self._extract_jenkins_from_configs(data)
        
        # Phase 5: Extract file references from Action inputs
        self._link_actions_to_files(data)
    
    def _link_actions_to_files(self, data: CIData):
        """Link Actions to files via input parameters (generic)."""
        # Build action map
        action_map = {a.name: a for a in data.actions}
        script_names = {s.name: s for s in data.scripts}
        
        # Build action.yml content map from scripts
        action_yml_map = {}  # action_name -> action.yml content
        for script in data.scripts:
            if script.name == "action.yml" or script.name == "action.yaml":
                # Extract action name from path
                path = script.path.replace("\\", "/")
                if ".github/actions/" in path:
                    parts = path.split("/")
                    try:
                        idx = parts.index("actions")
                        if idx + 1 < len(parts):
                            action_name = parts[idx + 1]
                            action_yml_map[action_name] = script.content
                    except ValueError:
                        pass
        
        # Extract file paths from action inputs
        action_input_files = {}  # action_name -> {input_name: file_path}
        for action_name, yml_content in action_yml_map.items():
            input_files = self._extract_action_input_files_from_content(yml_content)
            if input_files:
                action_input_files[action_name] = input_files
        
        # Link workflows to files via actions
        for wf_name, wf in data.workflows.items():
            for job_name, job in wf.jobs.items():
                for step in job.steps:
                    uses = step.uses
                    if not uses:
                        continue
                    
                    # Extract action name from uses
                    action_name = None
                    if uses.startswith("./.github/actions/"):
                        action_name = uses.replace("./.github/actions/", "").split("@")[0]
                    elif uses.startswith("./"):
                        action_name = uses[2:].split("@")[0]
                    
                    if not action_name or action_name not in action_input_files:
                        continue
                    
                    # Get actual file paths (considering with_params override)
                    with_params = step.with_params or {}
                    actual_files = self._get_actual_file_paths(
                        action_input_files[action_name], with_params
                    )
                    
                    # Update called_by for scripts
                    workflow_ref = f"{wf_name}::{job_name}"
                    for input_name, file_path in actual_files.items():
                        file_name = Path(file_path).name
                        if file_name in script_names:
                            script = script_names[file_name]
                            action_ref = f"action:{action_name}"
                            if action_ref not in script.called_by:
                                script.called_by.append(action_ref)
                            if workflow_ref not in script.called_by:
                                script.called_by.append(workflow_ref)
    
    def _extract_action_input_files_from_content(self, yml_content: str) -> Dict[str, str]:
        """Extract file paths from action.yml content (generic)."""
        input_files = {}
        
        if not yml_content:
            return input_files
        
        # Parse action.yml
        try:
            action_def = yaml.safe_load(yml_content)
            inputs = action_def.get('inputs', {})
            
            for input_name, input_def in inputs.items():
                if not isinstance(input_def, dict):
                    continue
                
                default_value = input_def.get('default', '')
                if self._is_likely_file_path(default_value):
                    input_files[input_name] = default_value
        except Exception:
            pass
        
        return input_files
    
    def _is_likely_file_path(self, value: str) -> bool:
        """Check if a value is likely a file path (generic)."""
        if not value or not isinstance(value, str):
            return False
        
        # Filter out obvious non-file values
        if value.startswith('/'):  # Absolute path
            return False
        if value.startswith('$'):  # Variable reference
            return False
        if value.startswith('{{'):  # Template reference
            return False
        if value.lower() in ['true', 'false', 'yes', 'no', 'on', 'off']:
            return False
        if re.match(r'^v?\d+\.\d+', value):  # Version number (v1.0, 3.10)
            return False
        if re.match(r'^\d+$', value):  # Pure number
            return False
        
        # Must end with file suffix
        file_suffixes = ['.yaml', '.yml', '.json', '.sh', '.py', '.toml', '.ini', '.properties']
        if not any(value.endswith(suffix) for suffix in file_suffixes):
            return False
        
        return True
    
    def _get_actual_file_paths(self, action_input_files: Dict[str, str], with_params: Dict[str, Any]) -> Dict[str, str]:
        """Get actual file paths considering with_params override (generic)."""
        actual_files = {}
        
        for input_name, default_path in action_input_files.items():
            # If workflow specified this parameter, use the specified value
            if input_name in with_params:
                actual_value = str(with_params[input_name])
                if self._is_likely_file_path(actual_value):
                    actual_files[input_name] = actual_value
            else:
                # Otherwise use default value
                actual_files[input_name] = default_path
        
        return actual_files
    
    def _link_workflows_to_jenkins(self, data: CIData):
        """Link workflows to Jenkins pipelines (generic)."""
        # Standard GitHub runners
        standard_runners = [
            "ubuntu-latest", "ubuntu-22.04", "ubuntu-20.04",
            "macos-latest", "macos-12", "macos-11",
            "windows-latest", "windows-2022", "windows-2019",
        ]
        
        # Find workflows that call external CI
        for wf_name, wf in data.workflows.items():
            for job_name, job in wf.jobs.items():
                # Check if job uses non-standard runner (likely external CI)
                if job.runs_on and job.runs_on not in standard_runners:
                    self._link_job_to_jenkins(data, wf_name, job_name)
                    continue
                
                # Check steps for external CI calls
                for step in job.steps:
                    if self._is_external_ci_step(step):
                        self._link_job_to_jenkins(data, wf_name, job_name)
                        break
    
    def _is_external_ci_step(self, step: StepData) -> bool:
        """Check if a step calls external CI (generic)."""
        # Check uses: external action (not actions/* or local ./*)
        if step.uses:
            if not step.uses.startswith("actions/") and not step.uses.startswith("./"):
                return True
        
        # Check run: contains CI-related keywords
        if step.run:
            ci_keywords = ["ci", "jenkins", "pipeline", "trigger", "build-server"]
            run_lower = step.run.lower()
            for keyword in ci_keywords:
                if keyword in run_lower:
                    # Exclude common false positives
                    if keyword == "ci" and "ci/" in run_lower:
                        continue  # Likely a path reference
                    return True
        
        return False
    
    def _link_job_to_jenkins(self, data: CIData, wf_name: str, job_name: str):
        """Link a workflow job to Jenkins pipelines (generic)."""
        workflow_ref = f"{wf_name}::{job_name}"
        
        for pipeline in data.jenkins_pipelines:
            # Check if pipeline is triggered by GitHub
            if self._is_triggered_by_github(pipeline):
                pipeline_name = pipeline["name"]
                jenkins_ref = f"jenkins:{pipeline_name}"
                
                # Update called_by for scripts called by this pipeline
                for script in data.scripts:
                    if jenkins_ref in script.called_by:
                        chain_ref = f"{workflow_ref}→{jenkins_ref}"
                        if chain_ref not in script.called_by:
                            script.called_by.append(chain_ref)
    
    def _is_triggered_by_github(self, pipeline: Dict) -> bool:
        """Check if Jenkins pipeline is triggered by GitHub (generic)."""
        content = pipeline.get("content", "")
        
        # Generic indicators of GitHub-triggered pipelines
        github_indicators = [
            "githubPush", "github", "GIT_URL", "gitlabSourceRepo",
            "pullRequest", "webhook", "pr_", "merge_request",
        ]
        
        for indicator in github_indicators:
            if indicator in content:
                return True
        
        # Check shared libraries (might contain GitHub integration)
        shared_libs = pipeline.get("shared_libraries", [])
        for lib in shared_libs:
            if "github" in lib.lower() or "gitlab" in lib.lower():
                return True
        
        return False
    
    def _extract_jenkins_from_configs(self, data: CIData):
        """Extract Jenkins info from other_ci_configs (generic)."""
        for config in data.other_ci_configs:
            parsed = config.parsed_data
            if not parsed:
                continue
            
            # Recursively search for jenkins/pipeline/job keys
            for key in ["jenkins", "pipeline", "job", "jobs"]:
                info = self._find_key_recursive(parsed, key)
                if info:
                    pipelines = self._extract_names_from_config(info)
                    for pipeline_name in pipelines:
                        self._link_config_to_jenkins(data, config, pipeline_name)
    
    def _find_key_recursive(self, obj: Any, key: str) -> Any:
        """Recursively find a key in nested dict/list (generic)."""
        if isinstance(obj, dict):
            if key in obj:
                return obj[key]
            for v in obj.values():
                result = self._find_key_recursive(v, key)
                if result is not None:
                    return result
        elif isinstance(obj, list):
            for item in obj:
                result = self._find_key_recursive(item, key)
                if result is not None:
                    return result
        return None
    
    def _extract_names_from_config(self, obj: Any) -> List[str]:
        """Extract pipeline/job names from config object (generic)."""
        names = []
        if isinstance(obj, str):
            # Filter out variables and invalid names
            if not obj.startswith("$") and not obj.startswith("{{") and len(obj) > 2:
                # Filter out URLs and paths
                if "/" not in obj and "://" not in obj:
                    names.append(obj)
        elif isinstance(obj, dict):
            # Check for 'name' key
            if "name" in obj:
                names.extend(self._extract_names_from_config(obj["name"]))
            # Recursively search values
            for v in obj.values():
                names.extend(self._extract_names_from_config(v))
        elif isinstance(obj, list):
            for item in obj:
                names.extend(self._extract_names_from_config(item))
        return names
    
    def _link_config_to_jenkins(self, data: CIData, config: OtherCIConfigData, pipeline_name: str):
        """Link other_ci_config to Jenkins pipeline (generic)."""
        config_ref = f"external_ci:{config.system}"
        
        for pipeline in data.jenkins_pipelines:
            # Match by name similarity
            if pipeline_name in pipeline["name"] or pipeline["name"] in pipeline_name:
                jenkins_ref = f"jenkins:{pipeline['name']}"
                
                # Update called_by for scripts
                for script in data.scripts:
                    if jenkins_ref in script.called_by:
                        if config_ref not in script.called_by:
                            script.called_by.append(config_ref)


def extract_to_json(repo_path: str, output_file: str = None) -> str:
    """Extract CI/CD data and output as JSON for LLM analysis."""
    extractor = CIDataExtractor(repo_path)
    data = extractor.extract_all()
    
    # Convert to dict for JSON serialization
    result = {
        "repo_name": data.repo_name,
        "repo_path": data.repo_path,
        "ci_directories": data.ci_directories,
        "workflows": {},
        "actions": [],
        "scripts": [],
        "scripts_by_directory": data.scripts_by_directory,
        "relationships": {
            "workflow_calls": data.workflow_call_graph,
            "job_dependencies": data.job_dependency_graph,
            "action_usages": data.action_usage_graph,
        }
    }
    
    # Convert workflows with full details
    for wf_name, wf in data.workflows.items():
        result["workflows"][wf_name] = {
            "name": wf.name,
            "filename": wf.filename,
            "path": wf.path,
            "triggers": wf.triggers,
            "trigger_details": wf.trigger_details,
            "env_vars": wf.env_vars,
            "concurrency": wf.concurrency,
            "jobs": {
                job_name: {
                    "display_name": job.display_name,
                    "runs_on": job.runs_on,
                    "needs": job.needs,
                    "uses": job.uses,
                    "with_params": job.with_params,
                    "if_condition": job.if_condition,
                    "matrix": job.matrix,
                    "matrix_configs": job.matrix_configs,
                    "env_vars": job.env_vars,
                    "outputs": job.outputs,
                    "timeout_minutes": job.timeout_minutes,
                    "steps": [
                        {
                            "name": step.name,
                            "id": step.id,
                            "uses": step.uses,
                            "run": step.run,  # Full content, no truncation
                            "with_params": step.with_params,
                            "env": step.env,
                            "working_directory": step.working_directory,
                            "shell": step.shell,
                        }
                        for step in job.steps
                    ],
                    "calls_workflows": job.calls_workflows,
                    "calls_actions": job.calls_actions,
                }
                for job_name, job in wf.jobs.items()
            },
            "callers": wf.callers,
        }
    
    # Convert actions
    for action in data.actions:
        result["actions"].append({
            "name": action.name,
            "path": action.path,
            "description": action.description,
            "inputs": action.inputs,
            "outputs": action.outputs,
            "runs_using": action.runs_using,
            "called_actions": action.called_actions,
            "used_by": action.used_by,
        })
    
    # Convert scripts with nested call information
    for script in data.scripts:
        result["scripts"].append({
            "name": script.name,
            "path": script.path,
            "type": script.type,
            "functions": script.functions,
            "imports": script.imports,
            "content": script.content,  # Full content, no truncation
            "called_by": script.called_by,
            "calls_scripts": script.calls_scripts,  # Scripts this script calls
            "call_relations": [
                {
                    "called_script": rel.called_script,
                    "call_type": rel.call_type,
                    "line_number": rel.line_number,
                }
                for rel in script.call_relations
            ],
        })
    
    # Add script call graph for nested script analysis
    result["script_call_graph"] = {}
    for script in data.scripts:
        if script.calls_scripts:
            result["script_call_graph"][script.name] = script.calls_scripts
    
    # Convert other CI configs
    result["other_ci_configs"] = []
    for ci_config in data.other_ci_configs:
        result["other_ci_configs"].append({
            "system": ci_config.system,
            "path": ci_config.path,
            "content": ci_config.content,  # Full content for LLM analysis
            "parsed_data": ci_config.parsed_data,
        })
    
    # Convert pre-commit configs
    result["pre_commit_configs"] = []
    for pc_config in data.pre_commit_configs:
        config_dict = {
            "path": pc_config.path,
            "default_stages": pc_config.default_stages,
            "default_language_version": pc_config.default_language_version,
            "ci": pc_config.ci,
            "repos": [],
            "local_hooks": [],
        }
        
        # External repo hooks
        for hook in pc_config.repos:
            config_dict["repos"].append({
                "id": hook.id,
                "repo": hook.repo,
                "rev": hook.rev,
                "additional_dependencies": hook.additional_dependencies,
                "args": hook.args,
                "files": hook.files,
                "exclude": hook.exclude,
                "language": hook.language,
                "description": hook.description,
            })
        
        # Local hooks
        for hook in pc_config.local_hooks:
            config_dict["local_hooks"].append({
                "id": hook.id,
                "additional_dependencies": hook.additional_dependencies,
                "args": hook.args,
                "files": hook.files,
                "exclude": hook.exclude,
                "language": hook.language,
                "description": hook.description,
            })
        
        result["pre_commit_configs"].append(config_dict)
    
    # Convert Jenkins pipelines
    result["jenkins_pipelines"] = []
    for pipeline in data.jenkins_pipelines:
        result["jenkins_pipelines"].append({
            "name": pipeline.get("name"),
            "path": pipeline.get("path"),
            "type": pipeline.get("type"),
            "size": pipeline.get("size"),
            "shared_libraries": pipeline.get("shared_libraries", []),
            "stages": pipeline.get("stages", []),
            "function_calls": pipeline.get("function_calls", []),
            "env_vars": pipeline.get("env_vars", []),
        })
    
    # Convert command-script mappings
    result["command_script_mappings"] = data.command_script_mappings
    
    # Convert external CI scripts
    result["external_ci_scripts"] = data.external_ci_scripts
    
    # Output JSON
    json_str = json.dumps(result, indent=2, ensure_ascii=False)
    
    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(json_str)
        print(f"CI data extracted to: {output_file}")
    
    return json_str


if __name__ == "__main__":
    import sys
    
    repo_path = sys.argv[1] if len(sys.argv) > 1 else None
    output_file = sys.argv[2] if len(sys.argv) > 2 else "ci_data.json"
    
    if repo_path:
        extract_to_json(repo_path, output_file)
    else:
        print("Usage: python ci_data_extractor.py <repo_path> [output_file]")