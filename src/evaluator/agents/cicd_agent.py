"""CI/CD 分析 Agent - 分析项目的 CI/CD 架构

完整实现 SKILL.md 定义的功能：
1. 提取 CI/CD 数据
2. 检查工作流数量，决定处理策略
3. 中小型项目（≤30）：单次 LLM 调用
4. 大型项目（>30）：分割 prompt + 并发调用 + 合并结果
5. 生成最终报告
6. 生成架构图 JSON
"""
import re
import json
import asyncio
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from datetime import datetime
from typing import List, Dict, Any
from evaluator.llm import LLMClient
from evaluator.skills import CIAnalyzer


# 配置常量
MAX_WORKFLOWS_SINGLE_PROMPT = 10  # 单次调用的最大工作流数量
MAX_WORKFLOWS_PER_BATCH = 10      # 每批次的最大工作流数量
MAX_CONCURRENT_LLM_CALLS = 4      # 最大并发 LLM 调用数


class CICDAgent:
    """CI/CD 分析 Agent"""
    
    def __init__(
        self,
        llm: LLMClient = None,
    ):
        self.llm = llm
        self.ci_analyzer = CIAnalyzer()
    
    def run(self, state: dict) -> dict:
        """执行 CI/CD 分析"""
        project_path = state.get("project_path")
        project_name = state.get("project_name", "unknown")
        storage_dir = state.get("storage_dir")
        
        # 检查是否是重试/补充模式
        retry_mode = state.get("cicd_retry_mode")
        retry_issues = state.get("cicd_retry_issues", [])
        existing_report = state.get("cicd_existing_report")
        
        if not project_path:
            return {
                "current_step": "cicd",
                "cicd_analysis": None,
                "errors": ["项目路径未设置"],
            }
        
        print(f"\n{'='*50}")
        
        # 根据模式显示不同的标题
        if retry_mode == "retry":
            print("  CI/CD 架构分析 (重做模式)")
            print("  " + "-" * 30)
            print("  需要修正以下问题:")
            for issue in retry_issues[:5]:
                print(f"    • {issue.get('message', '未知问题')}")
            if len(retry_issues) > 5:
                print(f"    ... 还有 {len(retry_issues) - 5} 个问题")
        elif retry_mode == "supplement":
            print("  CI/CD 架构分析 (补充模式)")
            print("  " + "-" * 30)
            print("  需要补充以下内容:")
            for issue in retry_issues[:5]:
                print(f"    • {issue.get('message', '未知问题')}")
            if len(retry_issues) > 5:
                print(f"    ... 还有 {len(retry_issues) - 5} 个问题")
        else:
            print("  CI/CD 架构分析")
        
        print(f"{'='*50}")
        
        # 确定输出目录（优先使用 storage_dir）
        if storage_dir:
            output_dir = Path(storage_dir)
        else:
            output_dir = Path(project_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"  输出目录: {output_dir}")
        
        try:
            # Step 1: 提取 CI/CD 数据
            print("\n[Step 1/6] 提取 CI/CD 数据...")
            ci_data_path = str(output_dir / "ci_data.json")
            ci_data = self.ci_analyzer.extract_data(project_path, ci_data_path)
            
            workflows_count = len(ci_data.get("workflows", {}))
            actions_count = len(ci_data.get("actions", []))
            
            if workflows_count == 0:
                print("  未检测到 GitHub Actions 工作流")
                return {
                    "current_step": "cicd",
                    "cicd_analysis": {
                        "status": "no_cicd",
                        "message": "项目未使用 GitHub Actions",
                        "workflows_count": 0,
                        "actions_count": 0,
                    },
                    "errors": [],
                }
            
            print(f"  发现 {workflows_count} 个工作流, {actions_count} 个 Action")
            
            # 初始化 LLM 客户端
            if self.llm is None:
                from evaluator.llm import get_default_client
                self.llm = get_default_client()
            
            # Step 2: 检查工作流数量，决定处理策略
            print("\n[Step 2/6] 确定处理策略...")
            
            # 根据模式选择不同的分析策略
            if retry_mode == "retry":
                # 重做模式：将问题加入 prompt，让 LLM 修正
                print("  使用重做模式，修正报告中的错误")
                llm_response = self._retry_analysis(
                    ci_data, output_dir, retry_issues, existing_report
                )
            elif retry_mode == "supplement":
                # 补充模式：基于现有报告，补充缺失内容
                print("  使用补充模式，补充报告中的缺失内容")
                llm_response = self._supplement_analysis(
                    ci_data, output_dir, retry_issues, existing_report
                )
            elif workflows_count <= MAX_WORKFLOWS_SINGLE_PROMPT:
                print(f"  工作流数量 ≤ {MAX_WORKFLOWS_SINGLE_PROMPT}，使用单次调用模式")
                llm_response = self._single_call_analysis(ci_data, output_dir)
            else:
                print(f"  工作流数量 > {MAX_WORKFLOWS_SINGLE_PROMPT}，使用分割并发模式")
                llm_response = self._parallel_analysis(ci_data, output_dir, workflows_count, ci_data_path)
            
            # Step 4.5: 检视 LLM 响应
            print("\n[Step 4.5/8] 检视 LLM 响应...")
            llm_response = self._validate_and_supplement(llm_response, ci_data, output_dir)
            
            # Step 4.6: 从 LLM 响应提取架构图 JSON（用于阶段组织）
            print("\n[Step 4.6/8] 提取架构图数据用于阶段组织...")
            architecture_json_path = str(output_dir / "architecture.json")
            self._extract_and_save_json(
                llm_response,
                "ARCHITECTURE_JSON",
                architecture_json_path,
                default={"layers": [], "connections": []}
            )
            architecture_data = self._load_architecture_json(architecture_json_path)
            
            # Step 4.7: 检视并重新组织阶段
            print("\n[Step 4.7/8] 检视阶段划分...")
            llm_response = self._organize_stages(llm_response, architecture_data, ci_data)
            
            # Step 5: 生成最终报告
            print("\n[Step 5/8] 生成最终报告...")
            report_path = str(output_dir / "CI_ARCHITECTURE.md")
            self.ci_analyzer.generate_report(ci_data_path, llm_response, report_path)
            
            # Step 5.5: 验证最终报告（新增）
            print("\n[Step 5.5/8] 验证最终报告...")
            try:
                with open(report_path, 'r', encoding='utf-8') as f:
                    final_report = f.read()
                
                from evaluator.agents import ReviewerAgent
                reviewer = ReviewerAgent(llm=self.llm)
                final_validation = reviewer.validate_llm_response(final_report, ci_data)
                
                if not final_validation["valid"]:
                    print("  [WARN] 最终报告验证发现问题:")
                    if final_validation.get("missing_sections"):
                        print(f"    - 缺失章节: {final_validation['missing_sections']}")
                    if final_validation.get("missing_json"):
                        print(f"    - 缺失 JSON: {final_validation['missing_json']}")
                    if final_validation.get("missing_workflows"):
                        print(f"    - 缺失工作流: {final_validation['missing_workflows']}")
                else:
                    print("  [OK] 最终报告验证通过")
            except Exception as e:
                print(f"  [ERROR] 最终报告验证失败: {e}")
            
            # Step 8: 生成分析摘要 JSON
            print("\n[Step 8/8] 生成分析摘要...")
            analysis_summary_path = str(output_dir / "analysis_summary.json")
            self._generate_analysis_summary(
                llm_response, ci_data, architecture_data, analysis_summary_path
            )
            
            print(f"\n{'='*50}")
            print("  CI/CD 分析完成!")
            print(f"{'='*50}")
            print(f"  报告路径: {report_path}")
            
            return {
                "current_step": "cicd",
                "cicd_analysis": {
                    "status": "success",
                    "workflows_count": workflows_count,
                    "actions_count": actions_count,
                    "ci_data_path": ci_data_path,
                    "report_path": report_path,
                    "architecture_json_path": architecture_json_path,
                    "analysis_summary_path": analysis_summary_path,
                },
                "errors": [],
            }
            
        except Exception as e:
            error_msg = str(e)
            print(f"\n[ERROR] CI/CD 分析失败: {error_msg}")
            import traceback
            traceback.print_exc()
            
            return {
                "current_step": "cicd",
                "cicd_analysis": {
                    "status": "failed",
                    "error": error_msg,
                },
                "errors": [f"CI/CD 分析失败: {error_msg}"],
            }
    
    def _single_call_analysis(self, ci_data: dict, output_dir: Path) -> str:
        """中小型项目：单次 LLM 调用"""
        # Step 3: 生成单个 Prompt
        print("\n[Step 3/6] 生成分析 Prompt...")
        prompt_path = str(output_dir / "prompt.txt")
        prompt = self.ci_analyzer.generate_prompt(ci_data, prompt_path)
        
        # Step 4: 单次 LLM 调用
        print("\n[Step 4/6] 调用 LLM 分析...")
        llm_response = self.llm.chat(prompt)
        print(f"  LLM 分析完成 ({len(llm_response)} 字符)")
        
        # 保存响应
        response_path = output_dir / "llm_response.md"
        response_path.write_text(llm_response, encoding="utf-8")
        
        return llm_response
    
    def _parallel_analysis(self, ci_data: dict, output_dir: Path, workflows_count: int, ci_data_path: str = "") -> str:
        """大型项目：分割 prompt + 并发调用 + 合并结果"""
        
        # Step 3: 生成分割的 Prompt 文件
        print("\n[Step 3/6] 生成分割 Prompt...")
        prompts_dir = output_dir / "prompts"
        prompts_dir.mkdir(exist_ok=True)
        
        prompt_files = self.ci_analyzer.generate_split_prompts(
            ci_data,
            str(prompts_dir),
            max_per_batch=MAX_WORKFLOWS_PER_BATCH
        )
        print(f"  生成了 {len(prompt_files)} 个 prompt 文件")
        
        # Step 4: 并发调用 LLM
        print("\n[Step 4/6] 并发调用 LLM 分析...")
        responses = self._parallel_llm_calls(prompt_files)
        
        # 合并结果
        print("\n[Step 4.5/6] 合并 LLM 响应...")
        merged_response = self._merge_responses(responses, ci_data, ci_data_path)
        print(f"  合并完成 ({len(merged_response)} 字符)")
        
        # 保存合并后的响应
        response_path = output_dir / "llm_response.md"
        response_path.write_text(merged_response, encoding="utf-8")
        
        return merged_response
    
    def _parallel_llm_calls(self, prompt_files: List[str]) -> List[Dict[str, Any]]:
        """并发调用 LLM 处理多个 prompt"""
        results = []
        
        # 使用线程池进行并发调用
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_LLM_CALLS) as executor:
            # 读取所有 prompt 文件
            prompts = []
            for pf in prompt_files:
                if pf.endswith('.txt') and not pf.endswith('README.txt'):
                    with open(pf, 'r', encoding='utf-8') as f:
                        prompts.append({
                            'path': pf,
                            'content': f.read()
                        })
            
            print(f"  准备处理 {len(prompts)} 个 prompt...")
            
            # 提交所有任务
            futures = []
            for i, p in enumerate(prompts):
                future = executor.submit(self._call_llm_with_retry, p['content'], p['path'], i+1, len(prompts))
                futures.append(future)
            
            # 收集结果
            for future in futures:
                try:
                    result = future.result(timeout=600)  # 10分钟超时
                    results.append(result)
                except Exception as e:
                    print(f"  [WARN] 任务失败: {e}")
                    results.append({
                        'success': False,
                        'error': str(e)
                    })
        
        return results
    
    def _call_llm_with_retry(self, prompt: str, prompt_path: str, index: int, total: int) -> Dict[str, Any]:
        """带重试的 LLM 调用"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                print(f"  [{index}/{total}] 正在处理 {Path(prompt_path).name}...")
                response = self.llm.chat(prompt)
                print(f"  [{index}/{total}] 完成 ({len(response)} 字符)")
                return {
                    'success': True,
                    'prompt_path': prompt_path,
                    'response': response,
                    'index': index
                }
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"  [{index}/{total}] 失败，重试 {attempt + 2}/{max_retries}...")
                    import time
                    time.sleep(5)
                else:
                    raise e
    
    def _merge_responses(self, responses: List[Dict[str, Any]], ci_data: dict, ci_data_path: str = "") -> str:
        """合并多个 LLM 响应"""
        
        # 分离成功和失败的响应
        successful = [r for r in responses if r.get('success')]
        failed = [r for r in responses if not r.get('success')]
        
        if failed:
            print(f"  [WARN] {len(failed)} 个任务失败")
        
        if not successful:
            raise RuntimeError("所有 LLM 调用都失败了")
        
        # 按 index 排序
        successful.sort(key=lambda x: x.get('index', 0))
        
        # 判断响应类型（概览 vs 详细批次）
        overview_response = None
        detail_responses = []
        
        for r in successful:
            prompt_name = Path(r['prompt_path']).name
            if 'main' in prompt_name:
                overview_response = r['response']
            else:
                detail_responses.append(r['response'])
        
        # 合并策略
        if overview_response and detail_responses:
            # 有概览 + 详情：合并
            return self._merge_overview_and_details(overview_response, detail_responses, ci_data_path)
        elif len(successful) == 1:
            # 只有一个响应：直接返回
            return successful[0]['response']
        else:
            # 多个详细响应：拼接
            return self._merge_detail_responses(detail_responses)
    
    def _merge_overview_and_details(self, overview: str, details: List[str], ci_data_path: str = "") -> str:
        """合并概览和详细响应 - 按阶段整合
        
        策略：
        1. 从概览中提取项目概述、架构图、阶段划分说明
        2. 从概览中提取阶段内容（概览包含完整的阶段结构）
        3. 从 details 中提取工作流详情，替换/补充概览中的阶段内容
        4. 添加关键发现和建议、附录、ARCHITECTURE_JSON
        """
        
        merged = []
        overview_sections = self._extract_main_sections(overview)
        
        # 1. 从概览中提取项目概述
        if overview_sections.get('overview'):
            merged.append(overview_sections['overview'])
        
        # 2. 从概览中提取架构图
        if overview_sections.get('architecture'):
            merged.append(overview_sections['architecture'])
        
        # 3. 从概览中提取阶段划分说明（如果存在）
        stage_info_match = re.search(r'^##\s+阶段划分说明\s*$(.*?)(?=^##\s+)', overview, re.MULTILINE | re.DOTALL)
        if stage_info_match:
            merged.append(f"## 阶段划分说明{stage_info_match.group(1)}")
        
        # 4. 从概览中提取阶段内容
        # 概览中包含完整的阶段结构（阶段1-5）
        stage_pattern = r'(^##\s+阶段[^：:\n]+[：:]\s*[^\n]+\n.*?)(?=^##\s+关键发现|^##\s+附录|^<!-- ARCHITECTURE_JSON|## 附录|$)'
        stage_matches = list(re.finditer(stage_pattern, overview, re.MULTILINE | re.DOTALL))
        
        if stage_matches:
            for match in stage_matches:
                stage_content = match.group(1).strip()
                if stage_content:
                    merged.append(stage_content)
        else:
            # 如果概览中没有阶段内容，从 details 中提取
            all_stages = self._extract_and_organize_stages(details)
            for stage_content in all_stages:
                merged.append(stage_content)
        
        # 5. 从概览中提取发现和建议
        if overview_sections.get('findings'):
            merged.append(overview_sections['findings'])
        else:
            findings = self._extract_findings_section(details)
            if findings:
                merged.append(findings)
        
        # 6. 从概览中提取附录（排除脚本目录索引，因为会单独生成）
        appendix_content = ""
        if overview_sections.get('appendix'):
            appendix_content = overview_sections['appendix']
        else:
            appendix = self._extract_appendix_section(details)
            if appendix:
                appendix_content = appendix
        
        # 移除附录中的脚本目录索引（因为会单独生成）
        if appendix_content:
            appendix_content = re.sub(r'^##\s+脚本目录索引.*?(?=^##|\Z)', '', appendix_content, flags=re.MULTILINE | re.DOTALL)
            appendix_content = appendix_content.strip()
            if appendix_content:
                merged.append(appendix_content)
        
        # 7. 从概览中提取 JSON 数据
        if overview_sections.get('json'):
            merged.append(overview_sections['json'])
        
        # 8. 补充脚本目录索引（从 ci_data.json 提取）
        scripts_section = self._generate_scripts_section(ci_data_path)
        if scripts_section:
            merged.append(scripts_section)
        
        return '\n\n'.join(merged)
    
    def _generate_scripts_section(self, ci_data_path: str) -> str:
        """从 ci_data.json 生成脚本目录索引"""
        
        try:
            with open(ci_data_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except:
            return ""
        
        scripts = data.get('scripts', [])
        if not scripts:
            return ""
        
        # 按目录分组
        scripts_by_dir = defaultdict(list)
        for script in scripts:
            path = script.get('path', '')
            if path:
                dir_name = str(Path(path).parent)
                scripts_by_dir[dir_name].append({
                    'name': script.get('name', ''),
                    'type': script.get('type', ''),
                    'called_by': script.get('called_by', [])
                })
        
        # 优先展示 CI 相关目录
        ci_dirs = ['.github/scripts', 'scripts']
        sorted_dirs = []
        seen_dirs = set()
        for ci_dir in ci_dirs:
            for dir_name in scripts_by_dir.keys():
                normalized = dir_name.replace('\\', '/')
                if ci_dir in normalized and dir_name not in seen_dirs:
                    sorted_dirs.append(dir_name)
                    seen_dirs.add(dir_name)
        
        # 添加其他目录
        for dir_name in scripts_by_dir.keys():
            if dir_name not in seen_dirs:
                sorted_dirs.append(dir_name)
                seen_dirs.add(dir_name)
        
        # 生成索引内容
        lines = ["## 脚本目录索引\n"]
        
        # CI 相关脚本
        lines.append("### CI 相关脚本\n")
        ci_scripts_found = False
        for dir_name in sorted_dirs:
            if '.github/scripts' in dir_name.replace('\\', '/'):
                ci_scripts_found = True
                dir_scripts = scripts_by_dir[dir_name]
                lines.append(f"**{dir_name}/** ({len(dir_scripts)} 个脚本)\n")
                for s in dir_scripts:
                    called = s.get('called_by', [])
                    called_str = ', '.join(called[:3]) if called else '无'
                    if len(called) > 3:
                        called_str += f' ...(+{len(called)-3})'
                    lines.append(f"- `{s['name']}` - 被调用: {called_str}")
                lines.append("")
        
        if not ci_scripts_found:
            lines.append("未检测到 `.github/scripts/` 目录下的 CI 脚本。\n")
        
        # 其他脚本目录（只展示前几个）
        lines.append("### 其他脚本目录\n")
        other_dirs = [d for d in sorted_dirs if '.github/scripts' not in d.replace('\\', '/')]
        for dir_name in other_dirs[:5]:
            dir_scripts = scripts_by_dir[dir_name]
            lines.append(f"- **{dir_name}/** ({len(dir_scripts)} 个脚本)")
        
        if len(other_dirs) > 5:
            lines.append(f"- ... 共 {len(other_dirs)} 个目录")
        
        lines.append(f"\n**总计**: {len(scripts)} 个脚本文件")
        
        return '\n'.join(lines)
    
    def _extract_and_organize_stages(self, details: List[str]) -> List[str]:
        """从详细响应中提取并按阶段组织内容"""
        stages = {}
        stage_order = []
        
        for detail in details:
            # 提取所有阶段章节（支持多种格式：阶段1、阶段一、Stage 等）
            # 匹配 "## 阶段X：xxx" 或 "## Stage X: xxx"
            pattern = r'^##\s+(阶段[^：:\n]+[：:]\s*[^\n]+)'
            for match in re.finditer(pattern, detail, re.MULTILINE):
                stage_title = match.group(1).strip()
                if stage_title not in stages:
                    stages[stage_title] = []
                    stage_order.append(stage_title)
                
                # 提取该阶段的完整内容（直到下一个 ## 标题）
                start = match.end()
                next_match = re.search(r'^##\s+', detail[start:], re.MULTILINE)
                if next_match:
                    end = start + next_match.start()
                else:
                    end = len(detail)
                
                stage_content = detail[start:end].strip()
                if stage_content and stage_content not in stages[stage_title]:
                    stages[stage_title].append(stage_content)
        
        # 合并每个阶段的内容（去重）
        result = []
        for stage_title in stage_order:
            # 合并内容并去除重复的工作流
            combined = self._merge_stage_content(stages[stage_title])
            if combined:
                result.append(f"## {stage_title}\n\n{combined}")
        
        return result
    
    def _merge_stage_content(self, contents: List[str]) -> str:
        """合并相同阶段的内容，去除重复的工作流"""
        if not contents:
            return ""
        
        # 提取所有工作流及其内容
        workflows = {}
        for content in contents:
            # 匹配工作流标题 #### 1.1 workflow.yml
            wf_pattern = r'####\s+\d+\.\d+\s+([\w-]+\.yml)\s*\n'
            for wf_match in re.finditer(wf_pattern, content):
                wf_name = wf_match.group(1)
                if wf_name not in workflows:
                    # 提取该工作流的完整内容
                    start = wf_match.start()
                    next_wf = re.search(r'####\s+\d+\.\d+\s+[\w-]+\.yml', content[wf_match.end():])
                    if next_wf:
                        end = wf_match.end() + next_wf.start()
                    else:
                        end = len(content)
                    workflows[wf_name] = content[wf_match.start():end].strip()
        
        # 按原始编号排序
        sorted_workflows = sorted(workflows.items(), key=lambda x: x[0])
        
        return "\n\n".join(workflows.values())
    
    def _extract_scripts_section(self, details: List[str]) -> str:
        """从详细响应中提取脚本索引"""
        for detail in details:
            match = re.search(r'^##\s+.*脚本.*\s*$(.*?)(?=^##\s+|$)', detail, re.MULTILINE | re.DOTALL)
            if match:
                return f"## 脚本目录索引{match.group(1)}"
        return ""
    
    def _extract_findings_section(self, details: List[str]) -> str:
        """从详细响应中提取发现和建议"""
        for detail in details:
            match = re.search(r'^##\s+.*发现.*建议\s*$(.*?)(?=^##\s+|$)', detail, re.MULTILINE | re.DOTALL)
            if match:
                return f"## 关键发现和建议{match.group(1)}"
        return ""
    
    def _extract_appendix_section(self, details: List[str]) -> str:
        """从详细响应中提取附录"""
        for detail in details:
            match = re.search(r'^##\s+附录\s*$(.*)', detail, re.MULTILINE | re.DOTALL)
            if match:
                return f"## 附录{match.group(1)}"
        return ""
    
    def _merge_detail_responses(self, details: List[str]) -> str:
        """合并多个详细响应"""
        merged = []
        
        # 添加标题
        merged.append("# CI/CD 架构分析\n")
        
        # 合并所有详细内容
        for i, detail in enumerate(details):
            # 清理重复的标题
            content = self._clean_duplicate_headers(detail)
            merged.append(content)
        
        return '\n\n'.join(merged)
    
    def _extract_main_sections(self, content: str) -> Dict[str, str]:
        """从概览响应中提取主要章节"""
        sections = {
            'overview': '',
            'architecture': '',
            'scripts': '',
            'findings': '',
            'appendix': '',
            'json': ''
        }
        
        # 提取项目概述
        match = re.search(r'^##\s+项目概述\s*$(.*?)(?=^##\s+)', content, re.MULTILINE | re.DOTALL)
        if match:
            sections['overview'] = f"## 项目概述{match.group(1)}"
        
        # 提取架构图
        match = re.search(r'^##\s+.*架构图\s*$(.*?)(?=^##\s+)', content, re.MULTILINE | re.DOTALL)
        if match:
            sections['architecture'] = f"## CI/CD 整体架构图{match.group(1)}"
        
        # 提取脚本索引
        match = re.search(r'^##\s+.*脚本.*\s*$(.*?)(?=^##\s+)', content, re.MULTILINE | re.DOTALL)
        if match:
            sections['scripts'] = f"## 脚本目录索引{match.group(1)}"
        
        # 提取发现和建议
        match = re.search(r'^##\s+.*发现.*建议\s*$(.*?)(?=^##\s+)', content, re.MULTILINE | re.DOTALL)
        if match:
            sections['findings'] = f"## 关键发现和建议{match.group(1)}"
        
        # 提取附录
        match = re.search(r'^##\s+附录\s*$(.*)', content, re.MULTILINE | re.DOTALL)
        if match:
            sections['appendix'] = f"## 附录{match.group(1)}"
        
        # 提取 JSON 架构图数据
        json_match = re.search(r'<!--\s*ARCHITECTURE_JSON\s*(.*?)\s*ARCHITECTURE_JSON\s*-->', content, re.DOTALL)
        if json_match:
            sections['json'] = f"<!-- ARCHITECTURE_JSON\n{json_match.group(1).strip()}\nARCHITECTURE_JSON -->"
        
        return sections
    
    def _extract_workflow_sections(self, content: str) -> List[str]:
        """从详细响应中提取工作流章节"""
        sections = []
        
        # 提取所有阶段章节（## 阶段X：xxx）
        matches = re.finditer(r'^##\s+阶段.*$(.*?)(?=^##\s+(?!###)|$)', content, re.MULTILINE | re.DOTALL)
        for match in matches:
            sections.append(match.group(0))
        
        return sections
    
    def _extract_stage_content(self, content: str) -> str:
        """提取阶段内容，排除概述和架构图"""
        # 移除项目概述和架构图部分
        content = re.sub(r'^##\s+项目概述\s*$.*?(?=^##\s+)', '', content, flags=re.MULTILINE | re.DOTALL)
        content = re.sub(r'^##\s+.*架构图\s*$.*?(?=^##\s+)', '', content, flags=re.MULTILINE | re.DOTALL)
        
        # 清理多余的空行
        content = re.sub(r'\n{3,}', '\n\n', content)
        
        return content.strip()
    
    def _clean_duplicate_headers(self, content: str) -> str:
        """清理重复的标题"""
        # 移除文档开头的 # 标题（保留子标题）
        content = re.sub(r'^#\s+.*$\n*', '', content, flags=re.MULTILINE)
        return content.strip()
    
    def _generate_architecture_json(self, report_path: str, output_path: str):
        """从 Markdown 报告中提取 JSON 架构图数据"""
        
        with open(report_path, "r", encoding="utf-8") as f:
            md_content = f.read()
        
        # 尝试从 Markdown 中提取 JSON 数据
        json_match = re.search(r'<!--\s*ARCHITECTURE_JSON\s*(.*?)\s*ARCHITECTURE_JSON\s*-->', md_content, re.DOTALL)
        
        if json_match:
            try:
                json_str = json_match.group(1).strip()
                architecture_data = json.loads(json_str)
                
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(architecture_data, f, ensure_ascii=False, indent=2)
                
                print(f"  从报告中提取架构图 JSON: {output_path}")
                return
            except json.JSONDecodeError as e:
                print(f"  [WARN] JSON 解析失败: {e}")
        
        # 如果没有找到 JSON，尝试根据章节生成
        print("  [WARN] 报告中未找到 JSON 数据，尝试根据章节生成...")
        sections = self._extract_sections(md_content)
        
        if not sections:
            print("  [WARN] 未找到章节，跳过 JSON 生成")
            self._save_empty_architecture_json(output_path)
            return
        
        sections_text = "\n".join([
            f"{'  ' * (s['level'] - 2)}{'##' if s['level'] == 2 else '###'} {s['title']}"
            for s in sections[:25]
        ])
        
        prompt = f'''根据以下 CI/CD 报告章节，生成架构图的 JSON 结构。

章节:
{sections_text}

输出 JSON 格式:
{{"layers": [{{"id": "layer1", "name": "层名", "nodes": [{{"id": "n1", "label": "节点名", "description": "描述", "detail_section": "章节名"}}]}}], "connections": [{{"source": "n1", "target": "n2"}}]}}

要求:
1. 每个阶段对应一个 layer
2. 每个工作流对应一个 node
3. detail_section 填写对应的章节标题
4. 只输出 JSON，不要其他内容'''
        
        print("  正在生成架构图结构...")
        response = self.llm.chat(prompt)
        
        try:
            json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = response.strip()
            
            architecture_data = json.loads(json_str)
            
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(architecture_data, f, ensure_ascii=False, indent=2)
            
            print(f"  架构图结构已保存: {output_path}")
            
        except json.JSONDecodeError as e:
            print(f"  [WARN] JSON 解析失败: {e}")
            self._save_empty_architecture_json(output_path)
    
    def _extract_sections(self, md_content: str) -> list:
        """提取所有章节标题"""
        sections = []
        pattern = r'^(#{2,4})\s+(.+)$'
        
        for match in re.finditer(pattern, md_content, re.MULTILINE):
            level = len(match.group(1))
            title = match.group(2).strip()
            sections.append({"level": level, "title": title})
        
        return sections
    
    def _save_empty_architecture_json(self, output_path: str):
        """保存空的架构图 JSON"""
        empty_data = {
            "layers": [],
            "connections": []
        }
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(empty_data, f, ensure_ascii=False, indent=2)
    
    def _retry_analysis(
        self, 
        ci_data: dict, 
        output_dir: Path, 
        issues: list,
        existing_report: str
    ) -> str:
        """重做模式：根据问题修正报告"""
        
        print("\n[Retry Step] 生成修正 Prompt...")
        
        # 构建问题列表
        issues_text = []
        for i, issue in enumerate(issues[:10], 1):
            issues_text.append(f"{i}. {issue.get('message', '未知问题')}")
            if issue.get('workflow'):
                issues_text.append(f"   工作流: {issue['workflow']}")
            if issue.get('expected'):
                issues_text.append(f"   正确内容: {issue['expected']}")
            if issue.get('actual'):
                issues_text.append(f"   报告内容: {issue['actual']}")
        
        issues_str = "\n".join(issues_text)
        
        prompt = f"""你是一个 CI/CD 报告审核员。之前的报告存在以下问题，请修正：

## 需要修正的问题
{issues_str}

## 原始报告摘要
{existing_report[:8000] if existing_report else '(无)'}

## 修正要求
1. 修正报告中与实际项目不符的内容
2. 保持报告的整体结构和格式
3. 确保所有工作流、Job、触发条件等信息与实际项目一致
4. 只输出修正后的完整报告，不要说明修改了哪些内容

## 项目数据
- 工作流数量: {len(ci_data.get('workflows', {}))}
- Job 总数: {sum(len(wf.get('jobs', {{}})) for wf in ci_data.get('workflows', {{}}).values())}

请输出修正后的完整报告："""
        
        print("  正在调用 LLM 修正报告...")
        llm_response = self.llm.chat(prompt)
        print(f"  修正完成 ({len(llm_response)} 字符)")
        
        # 保存响应
        response_path = output_dir / "llm_response_retry.md"
        response_path.write_text(llm_response, encoding="utf-8")
        
        return llm_response
    
    def _supplement_analysis(
        self, 
        ci_data: dict, 
        output_dir: Path, 
        issues: list,
        existing_report: str
    ) -> str:
        """补充模式：基于现有报告补充缺失内容"""
        
        print("\n[Supplement Step] 生成补充 Prompt...")
        
        # 构建缺失内容列表
        supplement_text = []
        for i, issue in enumerate(issues[:10], 1):
            msg = issue.get('message', '内容不够详尽')
            suggestion = issue.get('suggestion', '')
            workflow = issue.get('workflow', '')
            
            supplement_text.append(f"{i}. {msg}")
            if workflow:
                supplement_text.append(f"   工作流: {workflow}")
            if suggestion:
                supplement_text.append(f"   建议: {suggestion}")
        
        supplement_str = "\n".join(supplement_text)
        
        # 获取未分析或分析不足的工作流
        missing_workflows = []
        for issue in issues:
            if issue.get('type') in ['missing_workflow_detail', 'weak_analysis'] and issue.get('workflow'):
                if issue['workflow'] not in missing_workflows:
                    missing_workflows.append(issue['workflow'])
        
        # 获取这些工作流的详细信息
        workflows_detail = {}
        for wf_name in missing_workflows:
            if wf_name in ci_data.get('workflows', {}):
                workflows_detail[wf_name] = ci_data['workflows'][wf_name]
        
        workflows_json = json.dumps(workflows_detail, ensure_ascii=False, indent=2)
        
        prompt = f"""你是一个 CI/CD 报告审核员。之前的报告内容不够详尽，请补充：

## 需要补充的内容
{supplement_str}

## 现有报告
{existing_report[:6000] if existing_report else '(无)'}

## 需要详细分析的工作流数据
{workflows_json}

## 补充要求
1. 补充缺失的工作流详细分析
2. 扩展现有分析不够详尽的部分
3. 确保关键发现和建议充分（至少3条有价值的建议）
4. 保持报告的整体结构和格式
5. 只输出补充后的完整报告，不要说明补充了哪些内容

请输出补充后的完整报告："""
        
        print("  正在调用 LLM 补充内容...")
        llm_response = self.llm.chat(prompt)
        print(f"  补充完成 ({len(llm_response)} 字符)")
        
        # 保存响应
        response_path = output_dir / "llm_response_supplement.md"
        response_path.write_text(llm_response, encoding="utf-8")
        
        return llm_response
    
    def _generate_analysis_summary(
        self,
        llm_response: str,
        ci_data: dict,
        architecture_data: dict,
        output_path: str,
    ) -> dict:
        """从 LLM 响应中提取 ANALYSIS_SUMMARY，合并其他信息，保存 JSON"""
        
        summary_data = {}
        
        match = re.search(
            r'<!--\s*ANALYSIS_SUMMARY\s*(.*?)\s*ANALYSIS_SUMMARY\s*-->',
            llm_response,
            re.DOTALL
        )
        
        if match:
            try:
                summary_data = json.loads(match.group(1).strip())
                print("  从报告中提取到评估评分")
            except json.JSONDecodeError as e:
                print(f"  WARNING: ANALYSIS_SUMMARY JSON 解析失败: {e}")
                summary_data = {}
        else:
            print("  WARNING: 未找到 ANALYSIS_SUMMARY，使用默认值")
            summary_data = {}
        
        workflows = ci_data.get("workflows", {})
        
        summary = {
            "project_name": ci_data.get("repo_name", "unknown"),
            "version_id": datetime.now().strftime("v%Y%m%d_%H%M%S"),
            "analyzed_at": datetime.now().isoformat() + "Z",
            
            "basic_stats": {
                "workflow_count": len(workflows),
                "job_count": sum(len(wf.get("jobs", {})) for wf in workflows.values()),
                "action_count": len(ci_data.get("actions", [])),
                "script_count": len(ci_data.get("scripts", [])),
            },
            
            "architecture": {
                "stages": [
                    {
                        "name": layer.get("name"),
                        "workflows": [
                            node.get("label") for node in layer.get("nodes", [])
                            if node.get("label", "").endswith(".yml")
                        ]
                    }
                    for layer in architecture_data.get("layers", [])
                ],
                "trigger_types": self._extract_trigger_types(ci_data),
                "has_matrix_build": self._check_matrix_build(ci_data),
                "has_caching": self._check_caching(ci_data),
                "has_reusable_workflows": self._check_reusable_workflows(ci_data),
            },
            
            "scores": summary_data.get("scores", {}),
            "score_rationale": summary_data.get("score_rationale", {}),
            "findings": summary_data.get("findings", {"strengths": [], "weaknesses": []}),
            "recommendations": summary_data.get("recommendations", []),
        }
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        
        print(f"  analysis_summary.json 已保存: {output_path}")
        
        return summary
    
    def _validate_and_supplement(
        self,
        llm_response: str,
        ci_data: dict,
        output_dir: Path
    ) -> str:
        """检视 LLM 响应并补充缺失内容
        
        Args:
            llm_response: LLM 的响应内容
            ci_data: CI 数据
            output_dir: 输出目录
        
        Returns:
            补充后的响应内容
        """
        from evaluator.agents import ReviewerAgent
        reviewer = ReviewerAgent(llm=self.llm)
        
        validation = reviewer.validate_llm_response(llm_response, ci_data)
        
        if validation["valid"]:
            print("  [OK] LLM 响应检视通过")
            return llm_response
        
        print("  [WARN] LLM 响应检视发现问题:")
        
        # 补充缺失的 JSON
        if validation["missing_json"]:
            for json_marker in validation["missing_json"]:
                if json_marker == "ARCHITECTURE_JSON":
                    print(f"    - 缺失 ARCHITECTURE_JSON，生成默认值")
                    arch_json = self._generate_default_architecture_json(ci_data)
                    llm_response += f"\n\n<!-- ARCHITECTURE_JSON\n{json.dumps(arch_json, ensure_ascii=False)}\nARCHITECTURE_JSON -->"
                elif json_marker == "ANALYSIS_SUMMARY":
                    print(f"    - 缺失 ANALYSIS_SUMMARY，生成默认值")
                    summary_json = self._generate_default_analysis_summary(ci_data)
                    llm_response += f"\n\n<!-- ANALYSIS_SUMMARY\n{json.dumps(summary_json, ensure_ascii=False)}\nANALYSIS_SUMMARY -->"
        
        # 报告缺失但不自动补充（需要重新分析）
        if validation["missing_workflows"]:
            print(f"    [WARN] 缺失工作流: {validation['missing_workflows']}")
            print(f"    建议: 考虑重新分析或手动补充")
        
        if validation["missing_sections"]:
            print(f"    [WARN] 缺失章节: {validation['missing_sections']}")
        
        return llm_response
    
    def _organize_stages(
        self,
        llm_response: str,
        architecture_data: dict,
        ci_data: dict
    ) -> str:
        """检视并重新组织阶段
        
        Args:
            llm_response: LLM 响应内容
            architecture_data: 架构图 JSON 数据
            ci_data: CI 数据
        
        Returns:
            处理后的内容
        """
        from evaluator.agents import ReviewerAgent
        reviewer = ReviewerAgent(llm=self.llm)
        
        validation = reviewer.validate_stage_organization(llm_response, architecture_data)
        
        if validation["valid"]:
            print("  [OK] 阶段划分检视通过")
            return llm_response
        
        print("  [WARN] 阶段划分检视发现问题:")
        if validation["missing_stages"]:
            print(f"    - 缺失阶段: {validation['missing_stages']}")
        print(f"    - 工作流覆盖率: {validation['workflow_coverage']:.1%}")
        
        if validation["workflow_coverage"] < 0.5:
            print("  [WARN] 工作流覆盖率过低，跳过自动重新组织")
            return llm_response
        
        try:
            reorganized = self._reorganize_by_architecture(llm_response, architecture_data, ci_data)
            
            re_validation = reviewer.validate_stage_organization(reorganized, architecture_data)
            if re_validation["valid"] or re_validation["workflow_coverage"] > validation["workflow_coverage"]:
                print("  [OK] 阶段重新组织成功")
                return reorganized
            else:
                print("  [WARN] 代码重新组织效果不佳，调用 LLM 重新划分...")
                return self._regenerate_stage_organization(llm_response, architecture_data, ci_data)
        except Exception as e:
            print(f"  [WARN] 阶段重新组织失败: {e}，调用 LLM 重新划分...")
            try:
                return self._regenerate_stage_organization(llm_response, architecture_data, ci_data)
            except:
                return llm_response
    
    def _generate_default_architecture_json(self, ci_data: dict) -> dict:
        """生成默认的架构图 JSON"""
        workflows = ci_data.get("workflows", {})
        layers = []
        
        # 按触发类型分组
        by_trigger = {}
        for wf_name, wf in workflows.items():
            triggers = wf.get("triggers", [])
            primary_trigger = triggers[0] if triggers else "unknown"
            if primary_trigger not in by_trigger:
                by_trigger[primary_trigger] = []
            by_trigger[primary_trigger].append(wf_name)
        
        # 生成层级
        for i, (trigger, wf_names) in enumerate(by_trigger.items()):
            nodes = []
            for j, wf_name in enumerate(wf_names):
                nodes.append({
                    "id": f"node-{i+1}-{j+1}",
                    "label": wf_name,
                    "description": f"{wf_name}",
                    "detail_section": f"阶段{i+1}"
                })
            layers.append({
                "id": f"layer-{i+1}",
                "name": f"{trigger} 触发",
                "nodes": nodes
            })
        
        return {"layers": layers, "connections": []}
    
    def _generate_default_analysis_summary(self, ci_data: dict) -> dict:
        """生成默认的分析摘要 JSON"""
        workflows = ci_data.get("workflows", {})
        return {
            "scores": {},
            "score_rationale": {},
            "findings": {
                "strengths": [],
                "weaknesses": []
            },
            "recommendations": []
        }
    
    def _extract_and_save_json(
        self,
        llm_response: str,
        marker: str,
        output_path: str,
        default: dict = None,
    ) -> bool:
        """从 LLM 响应中提取 JSON 并保存

        Args:
            llm_response: LLM 响应文本
            marker: JSON 标记名称 (如 "ARCHITECTURE_JSON", "ANALYSIS_SUMMARY")
            output_path: 输出文件路径
            default: 提取失败时的默认值

        Returns:
            是否成功提取
        """
        pattern = rf'<!--\s*{marker}\s*(.*?)\s*{marker}\s*-->'
        match = re.search(pattern, llm_response, re.DOTALL)

        if match:
            try:
                data = json.loads(match.group(1).strip())
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print(f"  {marker} 已保存: {output_path}")
                return True
            except json.JSONDecodeError as e:
                print(f"  WARNING: {marker} 解析失败: {e}")

        if default is not None:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(default, f, ensure_ascii=False, indent=2)
            print(f"  WARNING: 未找到 {marker}，使用默认值")

        return False
    
    def _reorganize_by_architecture(
        self,
        llm_response: str,
        architecture_data: dict,
        ci_data: dict
    ) -> str:
        """根据 architecture.json 重新组织阶段内容
        
        Args:
            llm_response: LLM 响应内容
            architecture_data: 架构图 JSON 数据
            ci_data: CI 数据
        
        Returns:
            重新组织后的内容
        """
        layers = architecture_data.get("layers", [])
        if not layers:
            return llm_response
        
        organized = []
        
        # 1. 提取并保留全局内容（按顺序）
        # 项目概述
        overview_match = re.search(r'^##\s+项目概述\s*$(.*?)(?=^##\s+)', llm_response, re.MULTILINE | re.DOTALL)
        if overview_match:
            organized.append(f"## 项目概述{overview_match.group(1)}")
        
        # 架构图
        arch_match = re.search(r'^##\s+.*架构图\s*$(.*?)(?=^##\s+)', llm_response, re.MULTILINE | re.DOTALL)
        if arch_match:
            organized.append(f"## CI/CD 整体架构图{arch_match.group(1)}")
        
        # 阶段划分说明
        stage_info_match = re.search(r'^##\s+阶段划分说明\s*$(.*?)(?=^##\s+)', llm_response, re.MULTILINE | re.DOTALL)
        if stage_info_match:
            organized.append(f"## 阶段划分说明{stage_info_match.group(1)}")
        
        # 2. 提取工作流详情（只提取 #### 开头的工作流）
        workflow_details = {}
        
        # 使用正则直接提取所有工作流详情
        # 匹配从 #### 工作流名 开始，到下一个 #### 工作流名 或附录 或关键发现 之前的内容
        pattern = r'(####\s+\d+\.\d+\s+([\w-]+\.yml)\s*\n)([\s\S]*?)(?=\n####\s+\d+\.\d+\s+|<!-- ARCHITECTURE_JSON|## 关键发现)'
        for match in re.finditer(pattern, llm_response):
            wf_header = match.group(1)  # "#### 1.1 workflow.yml\n"
            wf_name = match.group(2)
            wf_content = match.group(3)  # 工作流内容（不含标题行）
            
            # 清理内容：移除可能包含的 ## 阶段 标题
            wf_content = re.sub(r'^##\s+阶段[^：:\n]+[：:].*?\n', '', wf_content, flags=re.MULTILINE)
            wf_content = wf_content.strip()
            
            workflow_details[wf_name] = f"{wf_header}{wf_content}"
        
        # 3. 按 architecture.json 的层级重新组织（重新编号）
        used_workflows = set()
        
        for i, layer in enumerate(layers, 1):
            layer_name = layer.get("name", f"阶段{i}")
            layer_content = [f"## {layer_name}\n"]
            layer_has_content = False
            wf_in_layer = 0
            
            for node in layer.get("nodes", []):
                label = node.get("label", "")
                description = node.get("description", "")
                
                if label.endswith(".yml") and label in workflow_details:
                    wf_in_layer += 1
                    # 重新编号为 layer_num.workflow_num
                    new_num = f"{i}.{wf_in_layer}"
                    content = workflow_details[label]
                    # 替换原有的编号
                    content = re.sub(r'####\s+\d+\.\d+', f'#### {new_num}', content, count=1)
                    layer_content.append("\n" + content)
                    used_workflows.add(label)
                    layer_has_content = True
                elif not label.endswith(".yml"):
                    # 非 yml 节点（如 Jenkins Pipelines）作为描述性标题
                    layer_content.append(f"\n### {label}\n{description}\n")
                    layer_has_content = True
            
            if layer_has_content:
                organized.append("\n".join(layer_content))
        
        # 4. 未分配的工作流
        all_workflows = set(ci_data.get("workflows", {}).keys())
        unassigned = all_workflows - used_workflows
        
        if unassigned:
            print(f"  [WARN] 未分配到阶段的工作流: {unassigned}")
            unassigned_section = ["\n## 其他\n"]
            unassigned_count = 0
            for wf_name in unassigned:
                if wf_name in workflow_details:
                    unassigned_count += 1
                    content = workflow_details[wf_name]
                    # 编号为 99.x 表示未分配
                    content = re.sub(r'####\s+\d+\.\d+', f'#### 99.{unassigned_count}', content, count=1)
                    unassigned_section.append("\n" + content)
            if unassigned_count > 0:
                organized.append("\n".join(unassigned_section))
        
        # 5. 关键发现和建议
        findings_match = re.search(r'^##\s+.*发现.*建议\s*$(.*?)(?=^##\s+)', llm_response, re.MULTILINE | re.DOTALL)
        if findings_match:
            organized.append(f"## 关键发现和建议{findings_match.group(1)}")
        
        # 6. 附录
        appendix_match = re.search(r'^##\s+附录\s*$(.*)', llm_response, re.MULTILINE | re.DOTALL)
        if appendix_match:
            organized.append(f"## 附录{appendix_match.group(1)}")
        
        # 7. ARCHITECTURE_JSON
        json_match = re.search(r'<!--\s*ARCHITECTURE_JSON\s*(.*?)\s*ARCHITECTURE_JSON\s*-->', llm_response, re.DOTALL)
        if json_match:
            organized.append(f"\n<!-- ARCHITECTURE_JSON\n{json_match.group(1).strip()}\nARCHITECTURE_JSON -->")
        
        return "\n\n".join(organized)
    
    def _regenerate_stage_organization(
        self,
        llm_response: str,
        architecture_data: dict,
        ci_data: dict
    ) -> str:
        """调用 LLM 重新划分阶段
        
        Args:
            llm_response: 原始 LLM 响应
            architecture_data: 架构图 JSON 数据
            ci_data: CI 数据
        
        Returns:
            重新划分后的内容
        """
        layers = architecture_data.get("layers", [])
        
        stage_instruction = "请按照以下阶段重新组织报告内容：\n\n"
        for i, layer in enumerate(layers, 1):
            layer_name = layer.get("name", f"阶段{i}")
            workflows = [n.get("label") for n in layer.get("nodes", []) if n.get("label", "").endswith(".yml")]
            stage_instruction += f"{i}. {layer_name}：包含 {', '.join(workflows)}\n"
        
        stage_instruction += "\n请将每个工作流的详细内容放入对应阶段，保持原有的详细描述不变。"
        
        prompt = f"""以下是 CI/CD 分析报告的内容，但阶段划分不正确。

{stage_instruction}

原始报告内容：
{llm_response[:10000]}

请按照上述阶段划分重新组织报告，输出完整的 Markdown 内容。保持每个工作流的详细描述不变，只调整阶段归属。
"""
        
        print("  正在调用 LLM 重新划分阶段...")
        response = self.llm.chat(prompt)
        
        return response
    
    def _load_architecture_json(self, json_path: str) -> dict:
        """加载架构图 JSON"""
        try:
            if Path(json_path).exists():
                with open(json_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"  WARNING: 加载架构图 JSON 失败: {e}")
        return {"layers": [], "connections": []}
    
    def _extract_trigger_types(self, ci_data: dict) -> list:
        """提取触发类型"""
        trigger_types = set()
        for wf in ci_data.get("workflows", {}).values():
            for trigger in wf.get("triggers", []):
                trigger_types.add(trigger)
        return sorted(list(trigger_types))
    
    def _check_matrix_build(self, ci_data: dict) -> bool:
        """检查是否使用矩阵构建"""
        for wf in ci_data.get("workflows", {}).values():
            for job in wf.get("jobs", {}).values():
                if job.get("matrix") is not None:
                    return True
        return False
    
    def _check_caching(self, ci_data: dict) -> bool:
        """检查是否使用缓存"""
        for wf in ci_data.get("workflows", {}).values():
            for job in wf.get("jobs", {}).values():
                job_str = str(job).lower()
                if "cache" in job_str:
                    return True
        return False
    
    def _check_reusable_workflows(self, ci_data: dict) -> bool:
        """检查是否使用 Reusable Workflows"""
        for wf in ci_data.get("workflows", {}).values():
            for job in wf.get("jobs", {}).values():
                if job.get("uses", "").startswith(":"):
                    return True
        return False