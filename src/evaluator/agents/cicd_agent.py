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
        output_dir: str = None,
    ):
        self.llm = llm
        self.ci_analyzer = CIAnalyzer()
        self.output_dir = output_dir
    
    def run(self, state: dict) -> dict:
        """执行 CI/CD 分析"""
        project_path = state.get("project_path")
        project_name = state.get("project_name", "unknown")
        
        if not project_path:
            return {
                "current_step": "cicd",
                "cicd_analysis": None,
                "errors": ["项目路径未设置"],
            }
        
        print(f"\n{'='*50}")
        print("  CI/CD 架构分析")
        print(f"{'='*50}")
        
        if self.output_dir:
            output_dir = Path(self.output_dir)
        else:
            output_dir = Path(project_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        
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
            if workflows_count <= MAX_WORKFLOWS_SINGLE_PROMPT:
                print(f"  工作流数量 ≤ {MAX_WORKFLOWS_SINGLE_PROMPT}，使用单次调用模式")
                llm_response = self._single_call_analysis(ci_data, output_dir)
            else:
                print(f"  工作流数量 > {MAX_WORKFLOWS_SINGLE_PROMPT}，使用分割并发模式")
                llm_response = self._parallel_analysis(ci_data, output_dir, workflows_count, ci_data_path)
            
            # Step 5: 生成最终报告
            print("\n[Step 5/6] 生成最终报告...")
            report_path = str(output_dir / "CI_ARCHITECTURE.md")
            self.ci_analyzer.generate_report(ci_data_path, llm_response, report_path)
            
            # Step 6: 生成架构图 JSON
            print("\n[Step 6/6] 生成架构图结构...")
            architecture_json_path = str(output_dir / "architecture.json")
            self._generate_architecture_json(report_path, architecture_json_path)
            
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
                },
                "errors": [],
            }
            
        except Exception as e:
            error_msg = str(e)
            print(f"\n❌ CI/CD 分析失败: {error_msg}")
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
                    print(f"  ⚠️ 任务失败: {e}")
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
            print(f"  ⚠️ {len(failed)} 个任务失败")
        
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
        """合并概览和详细响应 - 按阶段整合"""
        
        merged = []
        
        # 1. 从概览中提取项目概述
        overview_sections = self._extract_main_sections(overview)
        if overview_sections.get('overview'):
            merged.append(overview_sections['overview'])
        
        # 2. 从概览中提取架构图
        if overview_sections.get('architecture'):
            merged.append(overview_sections['architecture'])
        
        # 3. 按阶段整合详细内容
        # 从所有详情中提取并按阶段组织
        all_stages = self._extract_and_organize_stages(details)
        for stage_content in all_stages:
            merged.append(stage_content)
        
        # 4. 从概览或详情中提取脚本索引
        if overview_sections.get('scripts'):
            merged.append(overview_sections['scripts'])
        else:
            scripts = self._extract_scripts_section(details)
            if scripts:
                merged.append(scripts)
        
        # 5. 从概览中提取发现和建议
        if overview_sections.get('findings'):
            merged.append(overview_sections['findings'])
        else:
            findings = self._extract_findings_section(details)
            if findings:
                merged.append(findings)
        
        # 6. 从概览中提取附录
        if overview_sections.get('appendix'):
            merged.append(overview_sections['appendix'])
        else:
            appendix = self._extract_appendix_section(details)
            if appendix:
                merged.append(appendix)
        
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
        import json
        from pathlib import Path
        from collections import defaultdict
        
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
        for ci_dir in ci_dirs:
            for dir_name in scripts_by_dir.keys():
                if ci_dir in dir_name.replace('\\', '/'):
                    sorted_dirs.append(dir_name)
        
        # 添加其他目录
        for dir_name in scripts_by_dir.keys():
            if dir_name not in sorted_dirs:
                sorted_dirs.append(dir_name)
        
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
            # 提取所有阶段章节
            pattern = r'^##\s+(阶段[^：:]*[：:].*?)\s*$'
            for match in re.finditer(pattern, detail, re.MULTILINE):
                stage_title = match.group(1)
                if stage_title not in stages:
                    stages[stage_title] = []
                    stage_order.append(stage_title)
                
                # 提取该阶段的完整内容
                start = match.end()
                next_match = re.search(r'^##\s+', detail[start:], re.MULTILINE)
                if next_match:
                    end = start + next_match.start()
                else:
                    end = len(detail)
                
                stage_content = detail[start:end].strip()
                stages[stage_title].append(stage_content)
        
        # 合并每个阶段的内容
        result = []
        for stage_title in stage_order:
            combined_content = '\n\n'.join(stages[stage_title])
            result.append(f"## {stage_title}\n\n{combined_content}")
        
        return result
    
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
                print(f"  ⚠️ JSON 解析失败: {e}")
        
        # 如果没有找到 JSON，尝试根据章节生成
        print("  ⚠️ 报告中未找到 JSON 数据，尝试根据章节生成...")
        sections = self._extract_sections(md_content)
        
        if not sections:
            print("  ⚠️ 未找到章节，跳过 JSON 生成")
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
            print(f"  ⚠️ JSON 解析失败: {e}")
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