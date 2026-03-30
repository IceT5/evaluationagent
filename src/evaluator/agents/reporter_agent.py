"""报告生成 Agent - 将 Markdown 报告转为交互式 HTML"""
import re
import json
from pathlib import Path
from typing import Optional, Dict, List, Any

from storage import StorageManager
from .base_agent import BaseAgent, AgentMeta


class ReporterAgent(BaseAgent):
    """报告生成 Agent"""

    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="ReporterAgent",
            description="将 Markdown 报告转换为交互式 HTML 报告",
            category="output",
            inputs=["cicd_analysis", "project_name", "review_result", "corrected_report"],
            outputs=["html_report", "report_path"],
            dependencies=["ReviewerAgent"],
        )

    LAYER_COLORS = [
        ("#3498db", "rgba(52, 152, 219, 0.15)"),
        ("#2ecc71", "rgba(46, 204, 113, 0.15)"),
        ("#e67e22", "rgba(230, 126, 34, 0.15)"),
        ("#9b59b6", "rgba(155, 89, 182, 0.15)"),
        ("#1abc9c", "rgba(26, 188, 156, 0.15)"),
        ("#e74c3c", "rgba(231, 76, 60, 0.15)"),
    ]

    def __init__(self, storage_manager: Optional[StorageManager] = None):
        super().__init__()
        self.storage = storage_manager or StorageManager()
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        cicd_analysis = state.get("cicd_analysis") or {}
        project_name = state.get("project_name") or "unknown"
        project_path = state.get("project_path") or ""
        storage_dir = state.get("storage_dir")
        storage_version_id = state.get("storage_version_id")
        errors = state.get("errors", [])
        
        review_result = state.get("review_result")
        review_issues = state.get("review_issues", [])
        review_retry_count = state.get("review_retry_count", 0)
        
        if storage_dir and Path(storage_dir).exists():
            data_dir = Path(storage_dir)
            print(f"  使用持久化存储: {data_dir}")
        else:
            data_dir = Path(project_path)
        
        md_path = cicd_analysis.get("report_path")
        if not md_path:
            md_path = str(data_dir / "CI_ARCHITECTURE.md")
        
        architecture_json_path = cicd_analysis.get("architecture_json_path")
        if not architecture_json_path:
            architecture_json_path = str(data_dir / "architecture.json")
        
        ci_data_path = cicd_analysis.get("ci_data_path")
        if not ci_data_path:
            ci_data_path = str(data_dir / "ci_data.json")
        
        if not Path(md_path).exists():
            print(f"\n⚠️ 未找到 Markdown 报告: {md_path}")
            return {
                **state,
                "current_step": "reporter",
                "html_report": None,
                "report_path": None,
                "errors": errors + ["未找到 Markdown 报告"],
            }
        
        print(f"\n{'='*50}")
        print("  报告生成")
        print(f"{'='*50}")
        
        corrected_report = state.get("corrected_report")
        md_content = corrected_report if corrected_report else Path(md_path).read_text(encoding="utf-8")
        
        if corrected_report:
            print("  ✓ 使用修正后的报告")
        
        print("\n[1/3] 解析数据...")
        
        architecture_data = self._load_architecture_json(architecture_json_path)
        if architecture_data and architecture_data.get("layers"):
            print(f"  读取到 {len(architecture_data['layers'])} 个架构层")
        
        workflow_details = self._extract_workflow_details(md_content)
        unique_workflows = len([k for k in workflow_details.keys() if k.endswith('.yml')])
        print(f"  提取到 {unique_workflows} 个工作流详情")
        
        overview = self._extract_overview(md_content)
        appendix = self._extract_appendix(md_content)
        findings = self._extract_findings(md_content)
        # 优先从 CI_ARCHITECTURE.md 提取脚本目录索引（包含关键配置）
        scripts_section = self._extract_scripts_section_from_md(md_content)
        if not scripts_section:
            scripts_section = self._generate_scripts_section(ci_data_path)
        statistics = self._generate_statistics(architecture_data, workflow_details, ci_data_path)
        
        review_summary = self._generate_review_summary(
            review_result, review_issues, review_retry_count
        )
        
        if review_summary:
            appendix = review_summary + "\n\n" + appendix
        
        print("\n[2/3] 生成交互式 HTML...")
        
        html_content = self._generate_html(
            overview=overview,
            architecture_data=architecture_data,
            workflow_details=workflow_details,
            scripts_section=scripts_section,
            findings=findings,
            appendix=appendix,
            project_name=project_name,
            statistics=statistics,
            ci_data_path=ci_data_path,
        )
        
        print("\n[3/3] 保存报告...")
        
        html_path = data_dir / "report.html"
        html_path.write_text(html_content, encoding="utf-8")
        
        if storage_version_id:
            project_meta = self.storage.get_project_metadata(project_name)
            if project_meta:
                self.storage._create_latest_link(project_name, storage_version_id)
        
        print(f"\n{'='*50}")
        print("  报告生成完成!")
        print(f"{'='*50}")
        print(f"  存储位置: {html_path}")
        print(f"  版本: {storage_version_id or 'N/A'}")
        
        self._open_browser(html_path)
        
        return {
            **state,
            "current_step": "reporter",
            "html_report": str(html_path),
            "report_path": str(html_path),
        }
    
    def _load_architecture_json(self, json_path: str) -> dict:
        """加载架构图 JSON"""
        try:
            if Path(json_path).exists():
                with open(json_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"  ⚠️ 加载架构图 JSON 失败: {e}")
        return {"layers": [], "connections": []}
    
    def _extract_overview(self, content: str) -> str:
        """提取项目概述"""
        match = re.search(r'^##\s+项目概述\s*$(.*?)(?=^##\s+)', content, re.MULTILINE | re.DOTALL)
        if match:
            return f"## 项目概述{match.group(1)}"
        return ""
    
    def _extract_appendix(self, content: str) -> str:
        """提取附录"""
        match = re.search(r'^##\s+附录\s*$(.*?)(?=^##\s+|^<!--\s*ARCHITECTURE_JSON|\Z)', content, re.MULTILINE | re.DOTALL)
        if match:
            return f"## 附录{match.group(1)}"
        return ""
    
    def _extract_findings(self, content: str) -> str:
        """提取关键发现和建议"""
        match = re.search(r'^##\s+[^\n]*发现[^\n]*建议[^\n]*$(.*?)(?=^##\s+|^<!--\s*ARCHITECTURE_JSON|\Z)', content, re.MULTILINE | re.DOTALL)
        if match:
            return f"## 关键发现和建议{match.group(1)}"
        return ""
    
    def _extract_scripts_section_from_md(self, content: str) -> str:
        """从 Markdown 内容中提取脚本目录索引章节"""
        match = re.search(r'^##\s+脚本目录索引\s*$(.*?)(?=^##\s+|^<!--\s*ARCHITECTURE_JSON|\Z)', content, re.MULTILINE | re.DOTALL)
        if match:
            return f"## 脚本目录索引{match.group(1)}"
        return ""
    
    def _extract_workflow_details(self, content: str) -> dict:
        """提取工作流详情"""
        details = {}
        pattern = r'####\s+(\d+\.\d+)\s+([\w-]+\.yml)'
        for match in re.finditer(pattern, content):
            num = match.group(1)
            name = match.group(2).strip()
            
            start = match.end()
            next_match = re.search(r'\n####\s+\d+\.\d+', content[start:])
            if next_match:
                end = start + next_match.start()
            else:
                next_match = re.search(r'\n###\s+', content[start:])
                if next_match:
                    end = start + next_match.start()
                else:
                    next_match = re.search(r'\n##\s+', content[start:])
                    if next_match:
                        end = start + next_match.start()
                    else:
                        end = len(content)
            
            detail_content = content[start:end].strip()
            lines = detail_content.split('\n')
            desc = lines[0].strip() if lines else ""
            if desc.startswith('-'):
                desc = desc[1:].strip()
            
            anchor = self._to_anchor(name)
            details[anchor] = {
                "num": num,
                "name": name,
                "desc": desc,
                "content": detail_content,
            }
            details[name] = details[anchor]
            details[name.replace('.yml', '')] = details[anchor]
        
        return details
    
    def _generate_scripts_section(self, ci_data_path: str) -> str:
        """从 ci_data.json 生成脚本目录索引"""
        from collections import defaultdict
        
        try:
            with open(ci_data_path, 'r', encoding="utf-8") as f:
                data = json.load(f)
        except:
            return ""
        
        scripts = data.get('scripts', [])
        if not scripts:
            return ""
        
        scripts_by_dir = defaultdict(list)
        for script in scripts:
            path = script.get('path', '')
            if path:
                dir_name = str(Path(path).parent)
                scripts_by_dir[dir_name].append({
                    'name': script.get('name', ''),
                    'called_by': script.get('called_by', [])
                })
        
        lines = ["## 脚本目录索引\n"]
        lines.append("### CI 相关脚本\n")
        ci_scripts_found = False
        for dir_name in scripts_by_dir.keys():
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
        
        other_dirs = [d for d in scripts_by_dir.keys() if '.github/scripts' not in d.replace('\\', '/')]
        if other_dirs:
            lines.append("### 其他脚本目录\n")
            for dir_name in other_dirs[:5]:
                dir_scripts = scripts_by_dir[dir_name]
                lines.append(f"- **{dir_name}/** ({len(dir_scripts)} 个脚本)")
            if len(other_dirs) > 5:
                lines.append(f"- ... 共 {len(other_dirs)} 个目录")
        
        lines.append(f"\n**总计**: {len(scripts)} 个脚本文件")
        return '\n'.join(lines)
    
    def _generate_statistics(self, architecture_data: dict, workflow_details: dict, ci_data_path: str) -> dict:
        """生成统计数据"""
        stats = {
            "workflow_count": 0,
            "job_count": 0,
            "trigger_distribution": {},
            "layer_distribution": {},
            "action_usage": {},
            "script_count": 0,
        }
        
        layers = architecture_data.get("layers", [])
        
        # 从 ci_data.json 统计所有数据
        ci_data = None
        try:
            with open(ci_data_path, 'r', encoding="utf-8") as f:
                ci_data = json.load(f)
            workflows = ci_data.get('workflows', {})
            
            # 统计工作流总数（从 ci_data.json）
            stats["workflow_count"] = len(workflows)
            
            # 统计 Job 总数
            for wf_name, wf in workflows.items():
                stats["job_count"] += len(wf.get('jobs', {}))
            
            # 统计脚本数量
            stats["script_count"] = len(ci_data.get('scripts', []))
            
            # 从 ci_data.json 提取触发类型分布
            for wf in workflows.values():
                for trigger in wf.get('triggers', []):
                    stats["trigger_distribution"][trigger] = stats["trigger_distribution"].get(trigger, 0) + 1
            
            # 统计 Action 使用
            actions = ci_data.get('actions', [])
            for action in actions:
                action_name = action.get('name', action.get('uses', 'unknown'))
                stats["action_usage"][action_name] = stats["action_usage"].get(action_name, 0) + 1
        except:
            pass
        
        # 从 architecture_data 统计层级分布
        for layer in layers:
            layer_name = layer.get("name", "未知")
            nodes = layer.get("nodes", [])
            
            # "辅助工作流" 层：统计所有节点
            if layer_name == "辅助工作流":
                workflow_nodes = nodes
            else:
                # 其他层：只统计 .yml 结尾的工作流节点
                workflow_nodes = [n for n in nodes if n.get("label", "").endswith(".yml")]
            
            # 只统计有工作流的层
            if workflow_nodes:
                stats["layer_distribution"][layer_name] = len(workflow_nodes)
        
        # 一致性校验
        layer_total = sum(stats["layer_distribution"].values())
        if layer_total != stats["workflow_count"]:
            print(f"  [WARN] 层级分布合计 ({layer_total}) ≠ 工作流总数 ({stats['workflow_count']})")
        
        return stats
    
    def _extract_workflow_jobs(self, ci_data_path: str) -> dict:
        """从 ci_data.json 提取工作流的 Job 列表"""
        workflow_jobs = {}
        try:
            with open(ci_data_path, 'r', encoding="utf-8") as f:
                data = json.load(f)
            workflows = data.get('workflows', {})
            for wf_name, wf in workflows.items():
                jobs = list(wf.get('jobs', {}).keys())
                if jobs:
                    workflow_jobs[wf_name] = jobs
        except:
            pass
        return workflow_jobs
    
    def _to_anchor(self, text: str) -> str:
        anchor = re.sub(r'[^\w\u4e00-\u9fff-]', '-', text)
        anchor = re.sub(r'-+', '-', anchor)
        return anchor.strip('-').lower()
    
    def _generate_html(
        self,
        overview: str,
        architecture_data: dict,
        workflow_details: dict,
        scripts_section: str,
        findings: str,
        appendix: str,
        project_name: str,
        statistics: dict,
        ci_data_path: str,
    ) -> str:
        """生成交互式 HTML"""
        
        nav_items = [
            '<li><a href="#overview" class="nav-link" data-section="overview">项目概述</a></li>',
            '<li><a href="#architecture" class="nav-link" data-section="architecture">CI/CD 整体架构图</a></li>',
        ]
        
        layers = architecture_data.get("layers", [])
        for i, layer in enumerate(layers):
            layer_name = layer.get("name", f"阶段{i+1}")
            anchor = f"stage-{i+1}"
            nav_items.append(f'<li><a href="#{anchor}" class="nav-link" data-section="{anchor}">{layer_name}</a></li>')
        
        nav_items.extend([
            '<li><a href="#scripts" class="nav-link" data-section="scripts">脚本目录索引</a></li>',
            '<li><a href="#findings" class="nav-link" data-section="findings">关键发现和建议</a></li>',
            '<li><a href="#appendix" class="nav-link" data-section="appendix">附录</a></li>',
        ])
        
        architecture_svg = self._generate_architecture_svg(architecture_data)
        statistics_html = self._generate_statistics_html(statistics)
        stage_contents = self._generate_stage_contents(architecture_data, workflow_details, ci_data_path)
        workflow_jobs = self._extract_workflow_jobs(ci_data_path)
        
        css = self._generate_css()
        js = self._generate_js(architecture_data, workflow_details, statistics, workflow_jobs)
        
        html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{project_name} - CI/CD 架构分析报告</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/languages/yaml.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/languages/python.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/languages/bash.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
    <style>
{css}
    </style>
</head>
<body>
    <!-- 搜索面板 -->
    <div id="search-panel" class="search-panel">
        <div class="search-header">
            <input type="text" id="search-input" placeholder="搜索工作流、脚本..." autocomplete="off">
            <button id="search-close" class="search-close">&times;</button>
        </div>
        <div id="search-results" class="search-results"></div>
    </div>
    
    <!-- 面包屑 -->
    <div id="breadcrumb" class="breadcrumb">
        <span class="breadcrumb-item" data-section="top">首页</span>
    </div>
    
    <!-- 节点详情面板 -->
    <div id="node-popover" class="node-popover">
        <div class="popover-header">
            <span class="popover-title">选择节点查看详情</span>
        </div>
        <div class="popover-placeholder">
            点击架构图中的节点<br>查看工作流详情
        </div>
        <div class="popover-desc" style="display: none;"></div>
        <div class="popover-jobs" style="display: none;">
            <div class="popover-jobs-title">Jobs:</div>
            <div class="popover-jobs-list"></div>
        </div>
        <div class="popover-action" style="display: none;">
            <span class="popover-link" onclick="jumpToDetail()">点击查看详情 →</span>
        </div>
    </div>
    
    <div class="container">
        <nav class="sidebar">
            <h1>📋 {project_name}</h1>
            <p style="font-size: 12px; color: #a0a0a0; margin-bottom: 15px;">CI/CD 架构分析报告</p>
            <div class="search-trigger" id="search-trigger">
                <span>🔍</span> 搜索
            </div>
            <ul class="nav-list">
                {''.join(nav_items)}
            </ul>
        </nav>
        <main class="main">
            <!-- 项目概述 -->
            <section id="overview" class="section" data-title="项目概述">
                <div class="section-header">
                    <h2>项目概述</h2>
                    <button class="toggle-btn" data-target="overview-content">折叠</button>
                </div>
                <div id="overview-content" class="section-content">
                    {self._md_to_html(overview.replace('## 项目概述', '').strip()) if overview else '<p>暂无概述</p>'}
                </div>
            </section>
            
            <!-- 统计概览 -->
            <section id="statistics" class="section" data-title="统计概览">
                <div class="section-header">
                    <h2>📊 统计概览</h2>
                    <button class="toggle-btn" data-target="statistics-content">折叠</button>
                </div>
                <div id="statistics-content" class="section-content">
                    {statistics_html}
                </div>
            </section>
            
            <!-- CI/CD 整体架构图 -->
            <section id="architecture" class="section" data-title="CI/CD 整体架构图">
                <div class="section-header">
                    <h2>CI/CD 整体架构图</h2>
                    <div class="arch-controls">
                        <button class="arch-btn" id="zoom-in" title="放大">🔍+</button>
                        <button class="arch-btn" id="zoom-out" title="缩小">🔍-</button>
                        <button class="arch-btn" id="zoom-reset" title="重置">⟲</button>
                        <button class="arch-btn" id="arch-fullscreen" title="全屏">⛶</button>
                        <button class="arch-btn" id="export-png" title="导出PNG">📷</button>
                    </div>
                </div>
                <div id="arch-container" class="arch-container">
                    <div id="arch-content" class="arch-content">
                        {architecture_svg}
                    </div>
                </div>
                <p class="arch-hint">💡 点击节点查看详情 | 滚轮缩放 | 拖拽移动</p>
            </section>
            
            <!-- 各阶段详情 -->
            {stage_contents}
            
            <!-- 脚本目录索引 -->
            <section id="scripts" class="section" data-title="脚本目录索引">
                <div class="section-header">
                    <h2>脚本目录索引</h2>
                    <button class="toggle-btn" data-target="scripts-content">折叠</button>
                </div>
                <div id="scripts-content" class="section-content">
                    {self._generate_scripts_html(scripts_section)}
                </div>
            </section>
            
            <!-- 关键发现和建议 -->
            <section id="findings" class="section" data-title="关键发现和建议">
                <div class="section-header">
                    <h2>关键发现和建议</h2>
                    <button class="toggle-btn" data-target="findings-content">折叠</button>
                </div>
                <div id="findings-content" class="section-content">
                    {self._md_to_html(findings.replace('## 关键发现和建议', '').strip()) if findings else '<p>暂无发现和建议</p>'}
                </div>
            </section>
            
            <!-- 附录 -->
            <section id="appendix" class="section" data-title="附录">
                <div class="section-header">
                    <h2>附录</h2>
                    <button class="toggle-btn" data-target="appendix-content">折叠</button>
                </div>
                <div id="appendix-content" class="section-content">
                    {self._md_to_html(appendix.replace('## 附录', '').strip()) if appendix else '<p>暂无附录</p>'}
                </div>
            </section>
        </main>
    </div>
    
    <!-- 返回顶部 -->
    <button id="back-to-top" class="back-to-top">↑</button>
    
    <script>
{js}
    </script>
</body>
</html>'''
        return html
    
    def _generate_css(self) -> str:
        """生成 CSS 样式"""
        return '''
        :root {
            --primary: #3498db;
            --success: #2ecc71;
            --warning: #f39c12;
            --danger: #e74c3c;
            --purple: #9b59b6;
            --dark: #1a1a2e;
            --darker: #16213e;
            --gray: #95a5a6;
            --light-gray: #ecf0f1;
        }
        
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
        }
        
        /* 面包屑 */
        .breadcrumb {
            position: fixed;
            top: 0;
            left: 280px;
            right: 0;
            background: rgba(255,255,255,0.95);
            backdrop-filter: blur(10px);
            padding: 8px 20px;
            border-bottom: 1px solid #eee;
            z-index: 99;
            font-size: 13px;
            display: none;
        }
        .breadcrumb.visible { display: flex; }
        .breadcrumb-item {
            color: var(--gray);
            cursor: pointer;
            transition: color 0.2s;
        }
        .breadcrumb-item:hover { color: var(--primary); }
        .breadcrumb-item::after {
            content: " > ";
            color: var(--gray);
        }
        .breadcrumb-item:last-child::after { content: ""; }
        .breadcrumb-item:last-child { color: var(--dark); font-weight: 600; }
        
        /* 容器布局 */
        .container {
            max-width: 1800px;
            margin: 0 auto;
            display: flex;
            min-height: 100vh;
        }
        
        /* 侧边栏 */
        .sidebar {
            width: 280px;
            background: linear-gradient(180deg, var(--dark) 0%, var(--darker) 100%);
            color: #fff;
            padding: 20px;
            position: fixed;
            top: 0;
            left: 0;
            height: 100vh;
            overflow-y: auto;
            z-index: 100;
        }
        .sidebar h1 {
            font-size: 18px;
            margin-bottom: 8px;
            padding-bottom: 15px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        .nav-list { list-style: none; margin-top: 15px; }
        .nav-list li { margin: 2px 0; }
        .nav-list a {
            color: #a0a0a0;
            text-decoration: none;
            font-size: 14px;
            display: block;
            padding: 10px 12px;
            border-radius: 6px;
            transition: all 0.2s;
        }
        .nav-list a:hover, .nav-list a.active {
            background: rgba(52, 152, 219, 0.2);
            color: var(--primary);
        }
        
        /* 搜索触发按钮 */
        .search-trigger {
            background: rgba(255,255,255,0.1);
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 8px;
            padding: 12px;
            text-align: center;
            color: #a0a0a0;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.2s;
            margin-bottom: 15px;
        }
        .search-trigger:hover {
            background: rgba(52, 152, 219, 0.2);
            color: var(--primary);
        }
        
        /* 搜索面板 */
        .search-panel {
            position: fixed;
            top: 0;
            left: 280px;
            right: 0;
            bottom: 0;
            background: rgba(0,0,0,0.7);
            z-index: 200;
            display: none;
        }
        .search-panel.active { display: block; }
        .search-header {
            background: #fff;
            padding: 20px;
            display: flex;
            gap: 10px;
            border-bottom: 1px solid #eee;
        }
        .search-header input {
            flex: 1;
            padding: 12px 16px;
            border: 2px solid #eee;
            border-radius: 8px;
            font-size: 16px;
            outline: none;
            transition: border-color 0.2s;
        }
        .search-header input:focus { border-color: var(--primary); }
        .search-close {
            background: #f4f4f4;
            border: none;
            width: 44px;
            height: 44px;
            border-radius: 8px;
            font-size: 24px;
            cursor: pointer;
            color: var(--gray);
        }
        .search-close:hover { background: #e0e0e0; }
        .search-results {
            background: #fff;
            max-height: calc(100vh - 100px);
            overflow-y: auto;
            padding: 10px;
        }
        .search-result-item {
            padding: 15px;
            border-radius: 8px;
            cursor: pointer;
            transition: background 0.2s;
            margin-bottom: 5px;
        }
        .search-result-item:hover { background: var(--light-gray); }
        .search-result-item .result-title {
            font-weight: 600;
            color: var(--dark);
            margin-bottom: 5px;
        }
        .search-result-item .result-path {
            font-size: 12px;
            color: var(--gray);
        }
        .search-result-item mark {
            background: #fffde7;
            padding: 0 2px;
            border-radius: 2px;
        }
        
        /* 主内容区 */
        .main {
            flex: 1;
            margin-left: 280px;
            padding: 20px 30px 60px;
            background: #fff;
            min-height: 100vh;
            overflow-x: hidden;
            max-width: calc(100vw - 280px);
        }
        
        /* 章节样式 */
        .section {
            margin-bottom: 30px;
            background: #fff;
            border-radius: 12px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
            overflow: hidden;
        }
        .section-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px 25px;
            background: linear-gradient(135deg, #f8f9fa 0%, #fff 100%);
            border-bottom: 1px solid #eee;
        }
        .section-header h2 {
            color: var(--dark);
            font-size: 22px;
            margin: 0;
            padding: 0;
            border: none;
        }
        .toggle-btn {
            background: #f4f4f4;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
            color: var(--gray);
            transition: all 0.2s;
        }
        .toggle-btn:hover { background: #e0e0e0; color: var(--dark); }
        .section-content {
            padding: 25px;
            overflow-x: auto;
        }
        .section-content.collapsed { display: none; }
        .stage-section .section-content {
            display: none;
        }
        .stage-section .section-content.expanded {
            display: block;
        }
        
        /* 节点详情面板 */
        .node-popover {
            position: fixed;
            display: none;
            width: 350px;
            background: rgba(255,255,255,0.98);
            border-radius: 12px;
            box-shadow: 0 8px 30px rgba(0,0,0,0.3);
            padding: 20px;
            z-index: 1000;
            max-height: 400px;
            overflow-y: auto;
        }
        .node-popover .popover-header {
            margin-bottom: 12px;
        }
        .node-popover .popover-title {
            font-size: 16px;
            font-weight: 600;
            color: var(--dark);
        }
        .node-popover .popover-desc {
            font-size: 13px;
            color: var(--gray);
            margin-bottom: 12px;
        }
        .node-popover .popover-jobs {
            background: #f8f9fa;
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 12px;
        }
        .node-popover .popover-jobs-title {
            font-size: 12px;
            color: var(--gray);
            margin-bottom: 8px;
        }
        .node-popover .popover-job-item {
            font-size: 13px;
            color: var(--dark);
            padding: 4px 0;
        }
        .node-popover .popover-action {
            text-align: center;
            padding-top: 8px;
            border-top: 1px solid #eee;
        }
        .node-popover .popover-link {
            color: var(--primary);
            font-size: 13px;
            cursor: pointer;
        }
        .node-popover .popover-placeholder {
            color: var(--gray);
            font-size: 14px;
            text-align: center;
            padding: 40px 20px;
        }
        
        /* 统计卡片 */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: linear-gradient(135deg, var(--primary) 0%, #2980b9 100%);
            color: #fff;
            padding: 25px;
            border-radius: 12px;
            text-align: center;
            box-shadow: 0 4px 15px rgba(52, 152, 219, 0.3);
        }
        .stat-card.green { background: linear-gradient(135deg, var(--success) 0%, #27ae60 100%); box-shadow: 0 4px 15px rgba(46, 204, 113, 0.3); }
        .stat-card.orange { background: linear-gradient(135deg, var(--warning) 0%, #d68910 100%); box-shadow: 0 4px 15px rgba(243, 156, 18, 0.3); }
        .stat-card.purple { background: linear-gradient(135deg, var(--purple) 0%, #8e44ad 100%); box-shadow: 0 4px 15px rgba(155, 89, 182, 0.3); }
        .stat-value { font-size: 42px; font-weight: 700; margin-bottom: 5px; }
        .stat-label { font-size: 14px; opacity: 0.9; }
        
        .charts-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 30px;
        }
        .chart-container {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 12px;
        }
        .chart-container h4 {
            margin-bottom: 15px;
            color: var(--dark);
            font-size: 16px;
        }
        .chart-wrapper { position: relative; height: 300px; }
        
        /* 架构图容器 */
        .arch-container {
            display: block;
            background: linear-gradient(135deg, var(--dark) 0%, var(--darker) 100%);
            border-radius: 12px;
            overflow: hidden;
            position: relative;
            height: calc(100vh - 200px);
            max-height: 800px;
        }
        .arch-content {
            padding: 30px;
            cursor: grab;
            user-select: none;
            height: 100%;
        }
        .arch-content:active { cursor: grabbing; }
        .arch-controls {
            display: flex;
            gap: 8px;
        }
        .arch-btn {
            background: rgba(255,255,255,0.1);
            border: 1px solid rgba(255,255,255,0.2);
            color: #fff;
            padding: 6px 12px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 12px;
            transition: all 0.2s;
        }
        .arch-btn:hover { background: rgba(255,255,255,0.2); }
        .arch-hint {
            color: rgba(255,255,255,0.6);
            font-size: 13px;
            padding: 15px 25px;
            text-align: center;
        }
        
        /* 架构图 SVG */
        .arch-svg { display: block; margin: 0 auto; }
        .arch-layer-bg {
            rx: 12;
            opacity: 0.9;
        }
        .arch-layer-label {
            font-size: 14px;
            font-weight: 600;
            fill: rgba(255,255,255,0.9);
        }
        .arch-node {
            cursor: pointer;
            transition: all 0.3s;
        }
        .arch-node:hover .arch-node-bg { opacity: 1; }
        .arch-node-bg {
            rx: 8;
            stroke-width: 2;
            opacity: 0.85;
        }
        .arch-node-title {
            font-size: 13px;
            font-weight: 600;
            fill: #fff;
        }
        .arch-node-desc {
            font-size: 10px;
            fill: rgba(255,255,255,0.7);
        }
        .arch-connection {
            stroke-width: 2;
            fill: none;
            opacity: 0.6;
            marker-end: url(#arrowhead);
        }
        .arch-connection.highlight { opacity: 1; stroke-width: 3; }
        
        /* 工作流卡片 */
        .workflow-card {
            background: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 12px;
            margin: 20px 0;
            overflow: hidden;
        }
        .workflow-card-header {
            background: linear-gradient(135deg, #fff 0%, #f8f9fa 100%);
            padding: 20px;
            border-bottom: 1px solid #e9ecef;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .workflow-card-header h4 {
            color: var(--dark);
            margin: 0;
            font-size: 18px;
        }
        .workflow-card-header .meta {
            display: flex;
            gap: 15px;
            margin-top: 10px;
        }
        .workflow-card-header .meta-item {
            background: #e9ecef;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            color: var(--gray);
        }
        .workflow-card-body {
            padding: 20px;
        }
        .workflow-card-body.collapsed { display: none; }
        .workflow-card pre {
            background: #1e1e1e;
            color: #d4d4d4;
            padding: 15px;
            border-radius: 8px;
            overflow-x: auto;
            font-size: 13px;
            line-height: 1.5;
        }
        .workflow-card code {
            background: #f4f4f4;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 13px;
            font-family: 'Fira Code', monospace;
        }
        
        /* 表格样式 */
        table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            margin: 15px 0;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        th {
            background: linear-gradient(135deg, var(--primary) 0%, #2980b9 100%);
            color: white;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 12px;
            letter-spacing: 0.5px;
            padding: 12px 15px;
            text-align: left;
        }
        td {
            padding: 12px 15px;
            border-bottom: 1px solid #eee;
            font-size: 14px;
        }
        tr:nth-child(even) { background: #f8f9fa; }
        tr:hover { background: #e3f2fd; transition: background 0.2s; }
        
        /* 代码块样式 */
        pre {
            background: #1e1e1e;
            padding: 15px;
            border-radius: 8px;
            overflow-x: auto;
            font-size: 13px;
            line-height: 1.5;
            margin: 15px 0;
        }
        pre code { background: transparent; padding: 0; }
        
        /* 列表样式 */
        ul, ol { margin: 10px 0 15px 25px; }
        li { margin: 6px 0; line-height: 1.6; }
        
        /* 高亮动画 */
        .highlight {
            background: #fffde7 !important;
            animation: highlight-fade 2s ease;
        }
        @keyframes highlight-fade {
            from { background: #fffde7; }
            to { background: transparent; }
        }
        
        /* 返回顶部按钮 */
        .back-to-top {
            position: fixed;
            bottom: 30px;
            right: 30px;
            width: 50px;
            height: 50px;
            background: var(--primary);
            color: #fff;
            border: none;
            border-radius: 50%;
            font-size: 24px;
            cursor: pointer;
            opacity: 0;
            visibility: hidden;
            transition: all 0.3s;
            box-shadow: 0 4px 15px rgba(52, 152, 219, 0.4);
            z-index: 50;
        }
        .back-to-top.visible { opacity: 1; visibility: visible; }
        .back-to-top:hover { background: #2980b9; transform: translateY(-3px); }
        
        /* 阶段内容 */
        .stage-section {
            margin-bottom: 20px;
        }
        .stage-title {
            color: var(--dark);
            font-size: 22px;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid var(--primary);
        }
        
        /* Job 依赖图 */
        .job-dependency-graph {
            background: #1e1e1e;
            border-radius: 8px;
            padding: 20px;
            margin: 15px 0;
            overflow-x: auto;
        }
        .job-node {
            display: inline-block;
            background: var(--primary);
            color: #fff;
            padding: 8px 16px;
            border-radius: 6px;
            margin: 5px;
            font-size: 13px;
        }
        .job-arrow {
            color: var(--primary);
            margin: 0 10px;
            font-size: 18px;
        }
        
        /* 响应式 */
        @media (max-width: 1200px) {
            .sidebar { width: 220px; }
            .main { margin-left: 220px; }
            .breadcrumb { left: 220px; }
            .search-panel { left: 220px; }
            .charts-grid { grid-template-columns: 1fr; }
        }
        @media (max-width: 768px) {
            .sidebar { transform: translateX(-100%); }
            .main { margin-left: 0; }
            .breadcrumb { left: 0; }
            .search-panel { left: 0; }
        }
        
        /* 滚动条美化 */
        ::-webkit-scrollbar { width: 8px; height: 8px; }
        ::-webkit-scrollbar-track { background: #f1f1f1; }
        ::-webkit-scrollbar-thumb { background: #c1c1c1; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #a1a1a1; }
        
        /* 脚本目录折叠样式 */
        .script-details {
            margin: 15px 0;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            background: #f8f9fa;
        }
        .script-summary {
            padding: 12px 16px;
            cursor: pointer;
            font-weight: 500;
            color: var(--primary);
            list-style: none;
            display: flex;
            align-items: center;
            gap: 8px;
            user-select: none;
        }
        .script-summary::-webkit-details-marker {
            display: none;
        }
        .script-summary::before {
            content: "▶";
            font-size: 10px;
            transition: transform 0.2s;
        }
        .script-details[open] .script-summary::before {
            transform: rotate(90deg);
        }
        .script-content {
            padding: 12px 16px;
            border-top: 1px solid #e0e0e0;
            background: #fff;
            border-radius: 0 0 8px 8px;
        }
        .script-content ul {
            margin: 0;
            padding-left: 20px;
        }
'''
    
    def _generate_js(self, architecture_data: dict, workflow_details: dict, statistics: dict, workflow_jobs: dict) -> str:
        """生成 JavaScript 脚本"""
        return f'''
        const architectureData = {json.dumps(architecture_data, ensure_ascii=False)};
        const workflowDetails = {json.dumps(workflow_details, ensure_ascii=False)};
        const statistics = {json.dumps(statistics, ensure_ascii=False)};
        const workflowJobs = {json.dumps(workflow_jobs, ensure_ascii=False)};
        
        let activeNodeId = null;
        let pendingJumpLabel = null;
        
        // 节点到锚点映射
        const nodeAnchorMap = {{}};
        architectureData.layers && architectureData.layers.forEach((layer, layerIndex) => {{
            layer.nodes && layer.nodes.forEach(node => {{
                let key = node.label.replace(/\\.yml$/, '').replace(/\\.yml/g, '');
                nodeAnchorMap[key] = node.detail_section;
                nodeAnchorMap[node.label] = node.detail_section;
                nodeAnchorMap[node.id] = node.detail_section;
            }});
        }});
        
        // 搜索功能
        const searchPanel = document.getElementById('search-panel');
        const searchInput = document.getElementById('search-input');
        const searchResults = document.getElementById('search-results');
        const searchTrigger = document.getElementById('search-trigger');
        const searchClose = document.getElementById('search-close');
        
        searchTrigger.addEventListener('click', () => {{
            searchPanel.classList.add('active');
            searchInput.focus();
        }});
        
        searchClose.addEventListener('click', () => {{
            searchPanel.classList.remove('active');
            searchInput.value = '';
            searchResults.innerHTML = '';
        }});
        
        searchPanel.addEventListener('click', (e) => {{
            if (e.target === searchPanel) {{
                searchPanel.classList.remove('active');
            }}
        }});
        
        searchInput.addEventListener('input', debounce(() => {{
            const query = searchInput.value.trim();
            if (query.length < 2) {{
                searchResults.innerHTML = '<p style="padding: 20px; color: #999;">请输入至少2个字符</p>';
                return;
            }}
            const results = performSearch(query);
            displaySearchResults(results, query);
        }}, 300));
        
        function performSearch(query) {{
            const results = [];
            const lowerQuery = query.toLowerCase();
            
            // 搜索工作流
            for (const key in workflowDetails) {{
                const wf = workflowDetails[key];
                if (wf.name.toLowerCase().includes(lowerQuery) || 
                    wf.desc.toLowerCase().includes(lowerQuery) ||
                    wf.content.toLowerCase().includes(lowerQuery)) {{
                    results.push({{
                        type: 'workflow',
                        title: wf.name,
                        subtitle: wf.desc,
                        anchor: wf.name,
                        path: '工作流详情'
                    }});
                }}
            }}
            
            // 搜索架构图节点
            architectureData.layers && architectureData.layers.forEach((layer, idx) => {{
                layer.nodes && layer.nodes.forEach(node => {{
                    if (node.label.toLowerCase().includes(lowerQuery) ||
                        node.description.toLowerCase().includes(lowerQuery)) {{
                        results.push({{
                            type: 'node',
                            title: node.label,
                            subtitle: node.description,
                            anchor: node.detail_section,
                            path: layer.name
                        }});
                    }}
                }});
            }});
            
            return results.slice(0, 20);
        }}
        
        function displaySearchResults(results, query) {{
            if (results.length === 0) {{
                searchResults.innerHTML = '<p style="padding: 20px; color: #999;">未找到匹配结果</p>';
                return;
            }}
            
            const html = results.map(r => {{
                const highlightedTitle = r.title.replace(
                    new RegExp(`(${{query}})`, 'gi'),
                    '<mark>$1</mark>'
                );
                return `
                    <div class="search-result-item" data-anchor="${{r.anchor}}">
                        <div class="result-title">${{highlightedTitle}}</div>
                        <div class="result-path">${{r.type === 'workflow' ? '📄' : '🔵'}} ${{r.path}}</div>
                    </div>
                `;
            }}).join('');
            
            searchResults.innerHTML = html;
            
            document.querySelectorAll('.search-result-item').forEach(item => {{
                item.addEventListener('click', () => {{
                    const anchor = item.dataset.anchor;
                    const targetAnchor = toAnchor(anchor);
                    const target = document.getElementById(targetAnchor);
                    if (target) {{
                        searchPanel.classList.remove('active');
                        scrollToTarget(target);
                    }}
                }});
            }});
        }}
        
        // 折叠/展开功能
        document.querySelectorAll('.toggle-btn').forEach(btn => {{
            btn.addEventListener('click', () => {{
                const targetId = btn.dataset.target;
                const content = document.getElementById(targetId);
                if (content) {{
                    const isStageSection = content.closest('.stage-section');
                    if (isStageSection) {{
                        // stage-section 使用 expanded 类
                        const isExpanded = content.classList.toggle('expanded');
                        btn.textContent = isExpanded ? '折叠' : '展开';
                    }} else {{
                        // 普通 section 使用 collapsed 类
                        const isCollapsed = content.classList.toggle('collapsed');
                        btn.textContent = isCollapsed ? '展开' : '折叠';
                    }}
                }}
            }});
        }});
        
        // 工作流卡片折叠
        document.querySelectorAll('.workflow-card-header').forEach(header => {{
            header.addEventListener('click', () => {{
                const body = header.nextElementSibling;
                const isCollapsed = body.classList.toggle('collapsed');
                const hint = header.querySelector('.toggle-hint');
                if (hint) {{
                    hint.textContent = isCollapsed ? '点击展开详情' : '点击折叠';
                }}
            }});
        }});
        
        // 面包屑导航
        const breadcrumb = document.getElementById('breadcrumb');
        const sections = document.querySelectorAll('.section[data-title]');
        
        const observer = new IntersectionObserver((entries) => {{
            entries.forEach(entry => {{
                if (entry.isIntersecting) {{
                    updateBreadcrumb(entry.target.id);
                }}
            }});
        }}, {{ threshold: 0.3 }});
        
        sections.forEach(section => observer.observe(section));
        
        function updateBreadcrumb(currentId) {{
            const section = document.getElementById(currentId);
            if (!section) return;
            
            const title = section.dataset.title || currentId;
            const items = breadcrumb.querySelectorAll('.breadcrumb-item');
            
            // 移除所有 active
            items.forEach(item => item.classList.remove('active'));
            
            // 添加新的面包屑
            breadcrumb.innerHTML = `
                <span class="breadcrumb-item" data-section="top">首页</span>
                <span class="breadcrumb-item active">${{title}}</span>
            `;
            
            // 添加点击事件
            breadcrumb.querySelectorAll('.breadcrumb-item').forEach(item => {{
                item.addEventListener('click', () => {{
                    const sectionId = item.dataset.section;
                    if (sectionId === 'top') {{
                        window.scrollTo({{ top: 0, behavior: 'smooth' }});
                    }} else {{
                        const target = document.getElementById(sectionId);
                        if (target) scrollToTarget(target);
                    }}
                }});
            }});
            
            breadcrumb.classList.add('visible');
        }}
        
        // 返回顶部
        const backToTop = document.getElementById('back-to-top');
        window.addEventListener('scroll', () => {{
            if (window.scrollY > 400) {{
                backToTop.classList.add('visible');
            }} else {{
                backToTop.classList.remove('visible');
            }}
        }});
        
        backToTop.addEventListener('click', () => {{
            window.scrollTo({{ top: 0, behavior: 'smooth' }});
        }});
        
        // 架构图缩放/拖拽
        const archContent = document.getElementById('arch-content');
        let scale = 1;
        let translateX = 0;
        let translateY = 0;
        let isDragging = false;
        let startX, startY;
        
        function updateTransform() {{
            archContent.style.transform = `translate(${{translateX}}px, ${{translateY}}px) scale(${{scale}})`;
            archContent.style.transformOrigin = 'center top';
        }}
        
        function initAutoScale() {{
            const container = document.getElementById('arch-container');
            const svg = archContent.querySelector('svg.arch-svg');
            
            if (!svg) return;
            
            const containerWidth = container.clientWidth - 60;
            const containerHeight = container.clientHeight - 60;
            const svgWidth = parseFloat(svg.getAttribute('width'));
            const svgHeight = parseFloat(svg.getAttribute('height'));
            
            if (svgWidth > 0 && svgHeight > 0) {{
                const scaleX = containerWidth / svgWidth;
                const scaleY = containerHeight / svgHeight;
                scale = Math.min(scaleX, scaleY, 1);
                translateX = 0;
                translateY = 0;
                updateTransform();
            }}
        }}
        
        window.addEventListener('load', initAutoScale);
        
        document.getElementById('zoom-in').addEventListener('click', () => {{
            scale = Math.min(2, scale + 0.2);
            updateTransform();
        }});
        
        document.getElementById('zoom-out').addEventListener('click', () => {{
            scale = Math.max(0.5, scale - 0.2);
            updateTransform();
        }});
        
        document.getElementById('zoom-reset').addEventListener('click', () => {{
            scale = 1;
            translateX = 0;
            translateY = 0;
            updateTransform();
        }});
        
        archContent.addEventListener('wheel', (e) => {{
            e.preventDefault();
            const delta = e.deltaY > 0 ? -0.1 : 0.1;
            scale = Math.max(0.5, Math.min(2, scale + delta));
            updateTransform();
        }});
        
        archContent.addEventListener('mousedown', (e) => {{
            if (e.target.closest('.arch-node')) return;
            isDragging = true;
            startX = e.clientX - translateX;
            startY = e.clientY - translateY;
            archContent.style.cursor = 'grabbing';
        }});
        
        document.addEventListener('mousemove', (e) => {{
            if (!isDragging) return;
            translateX = e.clientX - startX;
            translateY = e.clientY - startY;
            updateTransform();
        }});
        
        document.addEventListener('mouseup', () => {{
            isDragging = false;
            archContent.style.cursor = 'grab';
        }});
        
        // 全屏
        document.getElementById('arch-fullscreen').addEventListener('click', () => {{
            const container = document.getElementById('arch-container');
            if (document.fullscreenElement) {{
                document.exitFullscreen();
            }} else {{
                container.requestFullscreen();
            }}
        }});
        
        // 导出PNG
        document.getElementById('export-png').addEventListener('click', async () => {{
            const container = document.getElementById('arch-container');
            try {{
                const canvas = await html2canvas(container, {{
                    backgroundColor: '#1a1a2e',
                    scale: 2,
                }});
                const link = document.createElement('a');
                link.download = 'architecture-diagram.png';
                link.href = canvas.toDataURL('image/png');
                link.click();
            }} catch (err) {{
                alert('导出失败，请重试');
            }}
        }});
        
        // 节点点击更新面板
        function showDetail(nodeId, nodeLabel, event) {{
            activeNodeId = nodeId;
            pendingJumpLabel = nodeLabel;
            updatePopoverContent(nodeId, nodeLabel);
            showPopoverAtNode(event);
        }}
        
        function showPopoverAtNode(event) {{
            const popover = document.getElementById('node-popover');
            const nodeEl = event.target.closest('.arch-node');
            
            if (!nodeEl) return;
            
            const rect = nodeEl.getBoundingClientRect();
            const popoverWidth = 350;
            const popoverHeight = 300;
            
            let left = rect.right + 15;
            let top = rect.top;
            
            if (left + popoverWidth > window.innerWidth - 20) {{
                left = rect.left - popoverWidth - 15;
            }}
            
            if (left < 10) {{
                left = Math.max(10, Math.min(rect.left, window.innerWidth - popoverWidth - 20));
                top = rect.bottom + 10;
            }}
            
            if (top + popoverHeight > window.innerHeight - 20) {{
                top = Math.max(10, window.innerHeight - popoverHeight - 20);
            }}
            
            if (top < 10) {{
                top = 10;
            }}
            
            popover.style.left = left + 'px';
            popover.style.top = top + 'px';
            popover.style.display = 'block';
        }}
        
        function updatePopoverContent(nodeId, nodeLabel) {{
            const popover = document.getElementById('node-popover');
            const titleEl = popover.querySelector('.popover-title');
            const descEl = popover.querySelector('.popover-desc');
            const jobsListEl = popover.querySelector('.popover-jobs-list');
            const jobsSection = popover.querySelector('.popover-jobs');
            const actionSection = popover.querySelector('.popover-action');
            const placeholder = popover.querySelector('.popover-placeholder');
            
            if (placeholder) placeholder.style.display = 'none';
            descEl.style.display = 'block';
            if (jobsSection) jobsSection.style.display = 'block';
            if (actionSection) actionSection.style.display = 'block';
            
            titleEl.textContent = nodeLabel;
            
            const node = findNode(nodeId);
            descEl.textContent = node ? node.description : '';
            
            const jobs = workflowJobs[nodeLabel] || [];
            if (jobs.length > 0) {{
                jobsListEl.innerHTML = jobs.map(function(j) {{ return '<div class="popover-job-item">• ' + j + '</div>'; }}).join('');
            }} else {{
                const isTriggerNode = nodeLabel.includes('事件') || 
                                      nodeLabel === 'workflow_dispatch' ||
                                      !nodeLabel.endsWith('.yml');
                if (isTriggerNode) {{
                    jobsListEl.innerHTML = '<div class="popover-job-item">触发事件节点，点击查看详情</div>';
                }} else {{
                    jobsListEl.innerHTML = '<div class="popover-job-item">无 Job 信息</div>';
                }}
            }}
        }}
        
        function jumpToDetail() {{
            if (!activeNodeId || !pendingJumpLabel) return;
            
            const nodeLabel = pendingJumpLabel;
            const nodeId = activeNodeId;
            let target = null;
            
            const isWorkflowFile = nodeLabel.endsWith('.yml');
            
            if (isWorkflowFile) {{
                for (const key in workflowDetails) {{
                    const wf = workflowDetails[key];
                    const cleanLabel = nodeLabel.replace(/\\.yml/g, '');
                    if (key.includes(cleanLabel) || wf.name.includes(cleanLabel)) {{
                        target = document.getElementById(toAnchor(wf.name));
                        break;
                    }}
                }}
            }}
            
            if (!target) {{
                for (let i = 0; i < architectureData.layers.length; i++) {{
                    const layer = architectureData.layers[i];
                    for (const node of (layer.nodes || [])) {{
                        if (node.id === nodeId) {{
                            target = document.getElementById('stage-' + (i + 1));
                            break;
                        }}
                    }}
                    if (target) break;
                }}
            }}
            
            if (target) {{
                const section = target.closest('.section');
                if (section) {{
                    const content = section.querySelector('.section-content');
                    if (content) {{
                        content.classList.add('expanded');
                        const btn = section.querySelector('.toggle-btn');
                        if (btn) btn.textContent = '折叠';
                    }}
                }}
                const cardBody = target.querySelector('.workflow-card-body');
                if (cardBody) {{
                    cardBody.classList.remove('collapsed');
                    const hint = target.querySelector('.toggle-hint');
                    if (hint) {{
                        hint.textContent = '点击折叠';
                    }}
                }}
                scrollToTarget(target);
                const popover = document.getElementById('node-popover');
                popover.style.display = 'none';
            }}
        }}
        
        // 点击外部关闭弹出框
        document.addEventListener('click', function(e) {{
            const popover = document.getElementById('node-popover');
            if (popover.style.display === 'block' && 
                !popover.contains(e.target) && 
                !e.target.closest('.arch-node')) {{
                popover.style.display = 'none';
            }}
        }});
        
        function findNode(nodeId) {{
            for (const layer of (architectureData.layers || [])) {{
                for (const node of (layer.nodes || [])) {{
                    if (node.id === nodeId) return node;
                }}
            }}
            return null;
        }}
        
        function scrollToTarget(target) {{
            target.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
            target.classList.add('highlight');
            setTimeout(() => target.classList.remove('highlight'), 2000);
        }}
        
        function toAnchor(text) {{
            return text.replace(/[^\\w\\u4e00-\\u9fff-]/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '').toLowerCase();
        }}
        
        function debounce(fn, delay) {{
            let timer;
            return function(...args) {{
                clearTimeout(timer);
                timer = setTimeout(() => fn.apply(this, args), delay);
            }};
        }}
        
        // 导航高亮
        document.querySelectorAll('.nav-link').forEach(link => {{
            link.addEventListener('click', function(e) {{
                e.preventDefault();
                document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
                this.classList.add('active');
                
                const sectionId = this.getAttribute('href').substring(1);
                const target = document.getElementById(sectionId);
                if (target) {{
                    scrollToTarget(target);
                }}
            }});
        }});
        
        // 初始化统计图表
        document.addEventListener('DOMContentLoaded', () => {{
            initCharts();
            hljs.highlightAll();
        }});
        
        function initCharts() {{
            // 触发类型饼图
            const triggerCtx = document.getElementById('chart-triggers');
            if (triggerCtx && statistics.trigger_distribution) {{
                const labels = Object.keys(statistics.trigger_distribution);
                const data = Object.values(statistics.trigger_distribution);
                
                new Chart(triggerCtx, {{
                    type: 'doughnut',
                    data: {{
                        labels: labels.map(l => l.replace('_', ' ')),
                        datasets: [{{
                            data: data,
                            backgroundColor: ['#3498db', '#2ecc71', '#e74c3c', '#f39c12', '#9b59b6', '#1abc9c'],
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {{
                            legend: {{ position: 'right' }}
                        }}
                    }}
                }});
            }}
            
            // 阶段分布柱状图
            const layerCtx = document.getElementById('chart-layers');
            if (layerCtx && statistics.layer_distribution) {{
                const labels = Object.keys(statistics.layer_distribution);
                const data = Object.values(statistics.layer_distribution);
                const colors = ['#3498db', '#2ecc71', '#e67e22', '#9b59b6', '#1abc9c', '#e74c3c'];
                
                new Chart(layerCtx, {{
                    type: 'bar',
                    data: {{
                        labels: labels,
                        datasets: [{{
                            label: '工作流数量',
                            data: data,
                            backgroundColor: colors.slice(0, labels.length),
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        indexAxis: 'y',
                        plugins: {{
                            legend: {{ display: false }}
                        }}
                    }}
                }});
            }}
        }}
'''
    
    def _generate_architecture_svg(self, architecture_data: dict) -> str:
        """生成 SVG 架构图"""
        layers = architecture_data.get("layers", [])
        connections = architecture_data.get("connections", [])
        
        if not layers:
            return '<p style="color: #a0a0a0; text-align: center; padding: 40px;">📊 架构图数据未生成</p>'
        
        node_width = 180
        node_height = 70
        layer_gap = 40
        node_gap = 15
        padding = 30
        
        layer_heights = []
        layer_y_positions = []
        total_height = padding * 2
        
        for i, layer in enumerate(layers):
            node_count = len(layer.get("nodes", []))
            layer_height = node_count * (node_height + node_gap) - node_gap + padding * 2
            layer_heights.append(layer_height)
            layer_y_positions.append(total_height)
            total_height += layer_height + layer_gap
        
        max_nodes = max(len(l.get("nodes", [])) for l in layers)
        total_width = max_nodes * (node_width + node_gap) - node_gap + padding * 2 + 150
        
        svg = [f'''<svg class="arch-svg" viewBox="0 0 {total_width} {total_height}" width="{total_width}" height="{total_height}">
    <defs>
        <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#3498db"/>
        </marker>
    </defs>''']
        
        node_positions = {}
        
        for layer_idx, layer in enumerate(layers):
            layer_name = layer.get("name", f"层{layer_idx+1}")
            nodes = layer.get("nodes", [])
            layer_y = layer_y_positions[layer_idx]
            
            color_idx = layer_idx % len(self.LAYER_COLORS)
            border_color, bg_color = self.LAYER_COLORS[color_idx]
            
            layer_height = layer_heights[layer_idx]
            
            svg.append(f'''
    <rect x="10" y="{layer_y}" width="{total_width - 20}" height="{layer_height}" 
          class="arch-layer-bg" fill="{bg_color}" stroke="{border_color}" stroke-width="1" stroke-dasharray="5,5" opacity="0.5"/>''')
            
            total_nodes_width = len(nodes) * (node_width + node_gap) - node_gap
            start_x = (total_width - total_nodes_width) / 2
            
            for node_idx, node in enumerate(nodes):
                node_id = node.get("id", f"node-{layer_idx}-{node_idx}")
                label = node.get("label", "未命名")
                description = node.get("description", "")[:30]
                
                node_x = start_x + node_idx * (node_width + node_gap)
                node_y = layer_y + layer_height / 2 - node_height / 2
                
                node_positions[node_id] = {
                    "x": node_x + node_width / 2,
                    "y": node_y,
                    "width": node_width,
                    "height": node_height
                }
                
                onclick = f"showDetail('{node_id}', '{label}', event)"
                
                svg.append(f'''
    <g class="arch-node" onclick="{onclick}">
        <rect x="{node_x}" y="{node_y}" width="{node_width}" height="{node_height}" 
              class="arch-node-bg" fill="{bg_color}" stroke="{border_color}"/>
        <text x="{node_x + node_width/2}" y="{node_y + 28}" class="arch-node-title" text-anchor="middle">{label}</text>
        <text x="{node_x + node_width/2}" y="{node_y + 48}" class="arch-node-desc" text-anchor="middle">{description}</text>
    </g>''')
        
        for conn in connections:
            source = conn.get("source")
            target = conn.get("target")
            
            if source in node_positions and target in node_positions:
                src = node_positions[source]
                tgt = node_positions[target]
                
                start_x = src["x"] + src["width"] / 2
                start_y = src["y"] + src["height"]
                end_x = tgt["x"]
                end_y = tgt["y"]
                
                mid_y = (start_y + end_y) / 2
                
                path = f"M {start_x} {start_y} C {start_x} {mid_y}, {end_x} {mid_y}, {end_x} {end_y}"
                
                svg.append(f'''
    <path class="arch-connection" d="{path}" stroke="{self.LAYER_COLORS[0][0]}"/>''')
        
        svg.append('</svg>')
        
        return '\n'.join(svg)
    
    def _generate_statistics_html(self, statistics: dict) -> str:
        """生成统计概览 HTML"""
        workflow_count = statistics.get("workflow_count", 0)
        job_count = statistics.get("job_count", 0)
        script_count = statistics.get("script_count", 0)
        layer_count = len(statistics.get("layer_distribution", {}))
        
        trigger_labels = {
            "pull_request": "PR 触发",
            "workflow_dispatch": "手动触发",
            "schedule": "定时触发",
            "issue_comment": "评论触发",
            "issues": "Issue 触发",
            "push": "Push 触发"
        }
        
        html = '''
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">''' + str(workflow_count) + '''</div>
                <div class="stat-label">工作流总数</div>
            </div>
            <div class="stat-card green">
                <div class="stat-value">''' + str(job_count) + '''</div>
                <div class="stat-label">Job 总数</div>
            </div>
            <div class="stat-card orange">
                <div class="stat-value">''' + str(script_count) + '''</div>
                <div class="stat-label">脚本文件</div>
            </div>
            <div class="stat-card purple">
                <div class="stat-value">''' + str(layer_count) + '''</div>
                <div class="stat-label">阶段数量</div>
            </div>
        </div>
        
        <div class="charts-grid">
            <div class="chart-container">
                <h4>📊 触发类型分布</h4>
                <div class="chart-wrapper">
                    <canvas id="chart-triggers"></canvas>
                </div>
            </div>
            <div class="chart-container">
                <h4>📈 阶段工作流分布</h4>
                <div class="chart-wrapper">
                    <canvas id="chart-layers"></canvas>
                </div>
            </div>
        </div>
        '''
        return html
    
    def _generate_stage_contents(self, architecture_data: dict, workflow_details: dict, ci_data_path: str | None = None) -> str:
        """根据架构图层生成各阶段内容"""
        layers = architecture_data.get("layers", [])
        sections = []
        
        ci_data = None
        if ci_data_path:
            try:
                with open(ci_data_path, 'r', encoding='utf-8') as f:
                    ci_data = json.load(f)
            except:
                pass
        
        for i, layer in enumerate(layers):
            layer_name = layer.get("name", f"阶段{i+1}")
            layer_id = f"stage-{i+1}"
            nodes = layer.get("nodes", [])
            
            workflow_cards = []
            external_system_details = ""
            
            for node in nodes:
                node_label = node.get("label", "")
                node_desc = node.get("description", "")
                detail_section = node.get("detail_section", "")
                
                detail = None
                clean_label = node_label.replace(".yml", "")
                
                for key, wf in workflow_details.items():
                    if clean_label in key or clean_label in wf.get("name", ""):
                        detail = wf
                        break
                
                if detail:
                    card_html = f'''
                <div class="workflow-card" id="{self._to_anchor(detail['name'])}">
                    <div class="workflow-card-header">
                        <h4>{detail['name']}</h4>
                        <div>
                            <div class="meta">
                                <span class="meta-item toggle-hint">点击展开详情</span>
                            </div>
                        </div>
                    </div>
                    <div class="workflow-card-body collapsed">
                        {self._md_to_html(detail['content'])}
                    </div>
                </div>'''
                    workflow_cards.append(card_html)
                else:
                    card_html = f'''
                <div class="workflow-card" id="{self._to_anchor(node_label)}">
                    <div class="workflow-card-header">
                        <h4>{node_label}</h4>
                    </div>
                    <div class="workflow-card-body">
                        <p>{node_desc}</p>
                    </div>
                </div>'''
                    workflow_cards.append(card_html)
            
            if ci_data and self._is_external_system_layer(layer_name):
                external_system_details = self._generate_external_system_details(ci_data)
            
            section_html = f'''
        <section id="{layer_id}" class="section stage-section" data-title="{layer_name}">
            <div class="section-header">
                <h2 class="stage-title">{layer_name}</h2>
                <button class="toggle-btn" data-target="{layer_id}-content">展开</button>
            </div>
            <div id="{layer_id}-content" class="section-content">
                {''.join(workflow_cards) if workflow_cards else '<p>暂无工作流详情</p>'}
                {external_system_details}
            </div>
        </section>'''
            sections.append(section_html)
        
        return '\n'.join(sections)
    
    def _is_external_system_layer(self, layer_name: str) -> bool:
        """判断是否为外部系统集成层"""
        keywords = ['外部', 'external', 'jenkins', 'blossom', 'ci系统', '集成']
        return any(kw.lower() in layer_name.lower() for kw in keywords)
    
    def _generate_external_system_details(self, ci_data: dict) -> str:
        """生成外部系统详细信息"""
        from collections import defaultdict
        
        details = []
        
        jenkins_pipelines = ci_data.get('jenkins_pipelines', [])
        if jenkins_pipelines:
            details.append('<div class="external-system-info" style="margin-top: 20px; padding: 15px; background: #f8f9fa; border-radius: 8px;">')
            details.append('<h4 style="margin-bottom: 10px;">Jenkins Pipeline 文件</h4>')
            details.append('<ul style="margin-left: 20px; line-height: 1.8;">')
            for jp in jenkins_pipelines[:15]:
                jp_path = jp.get('path', jp.get('name', str(jp))) if isinstance(jp, dict) else str(jp)
                shared_libs = jp.get('shared_libraries', []) if isinstance(jp, dict) else []
                lib_info = f' <span style="color: #666; font-size: 0.9em;">(共享库: {len(shared_libs)})</span>' if shared_libs else ''
                details.append(f'<li><code>{jp_path}</code>{lib_info}</li>')
            if len(jenkins_pipelines) > 15:
                details.append(f'<li><em>... 共 {len(jenkins_pipelines)} 个文件</em></li>')
            details.append('</ul>')
        
        external_ci_scripts = ci_data.get('external_ci_scripts', [])
        if external_ci_scripts:
            scripts_by_dir = defaultdict(list)
            for script in external_ci_scripts:
                script_path = script.get('path', script.get('name', str(script))) if isinstance(script, dict) else str(script)
                dir_name = str(Path(script_path).parent).replace('\\', '/')
                script_name = Path(script_path).name
                indicator = script.get('indicator', '') if isinstance(script, dict) else ''
                scripts_by_dir[dir_name].append((script_name, indicator))
            
            if not details:
                details.append('<div class="external-system-info" style="margin-top: 20px; padding: 15px; background: #f8f9fa; border-radius: 8px;">')
            
            details.append('<h4 style="margin-bottom: 10px;">外部 CI 脚本</h4>')
            details.append('<ul style="margin-left: 20px; line-height: 1.8;">')
            for dir_name, scripts in list(scripts_by_dir.items())[:10]:
                script_count = len(scripts)
                scripts_preview = ', '.join([s[0] for s in scripts[:3]])
                if script_count > 3:
                    scripts_preview += f'... (+{script_count - 3})'
                details.append(f'<li><strong>{dir_name}/</strong> ({script_count} 个脚本): {scripts_preview}</li>')
            if len(scripts_by_dir) > 10:
                details.append(f'<li><em>... 共 {len(scripts_by_dir)} 个目录</em></li>')
            details.append('</ul>')
        
        if details:
            details.append('</div>')
        
        return '\n'.join(details)
    
    def _generate_scripts_html(self, scripts_section: str) -> str:
        """生成脚本目录索引 HTML（带折叠功能）"""
        if not scripts_section:
            return '<p>暂无脚本信息</p>'
        
        html = self._md_to_html(scripts_section.replace('## 脚本目录索引', '').strip())
        html = self._add_scripts_collapsible(html)
        
        return html
    
    def _add_scripts_collapsible(self, html: str) -> str:
        """为脚本目录添加折叠功能"""
        pattern = r'(<h3>其他脚本目录</h3>\s*<ul>)'
        match = re.search(pattern, html)
        if not match:
            return html
        
        list_start = match.end() - 4
        list_end = html.find('</ul>', list_start)
        if list_end == -1:
            return html
        
        list_content = html[list_start:list_end + 5]
        items = re.findall(r'<li>(.*?)</li>', list_content, re.DOTALL)
        if len(items) <= 10:
            return html
        
        visible_items = items[:10]
        hidden_items = items[10:]
        
        visible_html = ''.join(f'<li>{item}</li>' for item in visible_items)
        hidden_html = ''.join(f'<li>{item}</li>' for item in hidden_items)
        
        collapsible_html = f'''<h3>其他脚本目录</h3>
<ul>{visible_html}</ul>
<details class="script-details">
<summary class="script-summary">📁 显示更多目录 ({len(hidden_items)} 个)</summary>
<div class="script-content">
<ul>{hidden_html}</ul>
</div>
</details>'''
        
        result = html[:match.start()] + collapsible_html + html[list_end + 5:]
        
        return result
    
    def _md_to_html(self, md_content: str) -> str:
        """将 Markdown 内容转为 HTML"""
        if not md_content:
            return ""
        
        html = md_content
        
        html = re.sub(r'```json\s*<!--[\s\S]*?ARCHITECTURE_JSON[\s\S]*?-->\s*```', '', html)
        html = re.sub(r'<!--[\s\S]*?ARCHITECTURE_JSON[\s\S]*?ARCHITECTURE_JSON\s*-->', '', html)
        html = re.sub(r'\*\*检查清单\*\*.*?(?=\n\n|\n##|\Z)', '', html, flags=re.DOTALL)
        html = re.sub(r'<strong>检查清单</strong>[\s\S]*?</ul>\s*', '', html)
        html = re.sub(r'<pre><code[^>]*>\s*</code></pre>', '', html)
        
        code_blocks = []
        code_pattern = r'```(\w+)?\n(.*?)```'
        
        def replace_code(match):
            lang = match.group(1) or 'plaintext'
            code = self._escape_html(match.group(2))
            idx = len(code_blocks)
            code_blocks.append((lang, code))
            return f'__CODE_BLOCK_{idx}__'
        
        html = re.sub(code_pattern, replace_code, html, flags=re.DOTALL)
        html = re.sub(r'`([^`]+)`', lambda m: f'<code>{self._escape_html(m.group(1))}</code>', html)
        
        lines = html.split('\n')
        result_lines = []
        in_table = False
        
        for line in lines:
            if line.startswith('|') and '|' in line[1:]:
                if not in_table:
                    result_lines.append('<table>')
                    in_table = True
                
                if re.match(r'^\|[\s\-:|]+\|$', line):
                    continue
                
                cells = [c.strip() for c in line.split('|')[1:-1]]
                if cells:
                    cell_tag = 'th' if result_lines[-1] == '<table>' else 'td'
                    row = '<tr>' + ''.join(f'<{cell_tag}>{c}</{cell_tag}>' for c in cells) + '</tr>'
                    result_lines.append(row)
            else:
                if in_table:
                    result_lines.append('</table>')
                    in_table = False
                result_lines.append(line)
        
        if in_table:
            result_lines.append('</table>')
        
        html = '\n'.join(result_lines)
        
        html = re.sub(r'^####\s+(.+)$', r'<h4>\1</h4>', html, flags=re.MULTILINE)
        html = re.sub(r'^###\s+(.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
        
        lines = html.split('\n')
        result = []
        list_type = None
        list_buffer = []
        
        def flush_list():
            nonlocal list_type, list_buffer, result
            if list_type and list_buffer:
                tag = '<ol>' if list_type == 'ol' else '<ul>'
                close_tag = '</ol>' if list_type == 'ol' else '</ul>'
                result.append(tag)
                result.extend(list_buffer)
                result.append(close_tag)
                list_buffer = []
                list_type = None
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            if re.match(r'^\s*[-*]\s+', line):
                if list_type == 'ul':
                    list_buffer.append('<li>' + line.lstrip('-* ').strip() + '</li>')
                else:
                    flush_list()
                    list_type = 'ul'
                    list_buffer.append('<li>' + line.lstrip('-* ').strip() + '</li>')
                i += 1
            elif re.match(r'^\s*\d+\.\s+', line):
                if list_type == 'ol':
                    list_buffer.append('<li>' + re.sub(r'^\s*\d+\.\s+', '', line) + '</li>')
                else:
                    flush_list()
                    list_type = 'ol'
                    list_buffer.append('<li>' + re.sub(r'^\s*\d+\.\s+', '', line) + '</li>')
                i += 1
            elif re.match(r'^\s*$', line):
                if list_type and list_buffer:
                    next_idx = i + 1
                    if next_idx < len(lines):
                        next_line = lines[next_idx]
                        if not (re.match(r'^\s*[-*]\s+', next_line) or re.match(r'^\s*\d+\.\s+', next_line)):
                            flush_list()
                            result.append(line)
                    else:
                        flush_list()
                else:
                    result.append(line)
                i += 1
            else:
                flush_list()
                result.append(line)
                i += 1
        
        flush_list()
        
        html = '\n'.join(result)
        html = re.sub(r'^---$', '<hr>', html, flags=re.MULTILINE)
        html = re.sub(r'\n{3,}', '\n\n', html)
        
        for idx, (lang, code) in enumerate(code_blocks):
            html = html.replace(f'__CODE_BLOCK_{idx}__', f'<pre><code class="language-{lang}">{code}</code></pre>')
        
        html = re.sub(r'<pre><code[^>]*>\s*</code></pre>', '', html)
        
        return html
    
    def _escape_html(self, text: str) -> str:
        """转义 HTML 特殊字符"""
        return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&#39;'))
    
    def _open_browser(self, html_path: Path):
        import webbrowser
        import urllib.parse
        
        try:
            url = f"file:///{urllib.parse.quote(str(html_path.absolute()))}"
            webbrowser.open(url)
            print(f"  已在浏览器中打开报告")
        except Exception as e:
            print(f"  无法自动打开浏览器: {e}")
    
    def _generate_review_summary(
        self, 
        review_result: dict | None, 
        review_issues: list,
        retry_count: int
    ) -> str:
        """生成验证结果摘要，添加到附录开头"""
        
        if not review_result:
            return ""
        
        lines = ["## 报告验证记录\n"]
        
        status = review_result.get("status", "unknown")
        status_text = {
            "passed": "✅ 验证通过",
            "corrected": "✅ 小错误已自动修正",
            "critical": "🔴 存在重大问题",
            "incomplete": "🟡 内容已补充完善",
            "max_retry": "⚠️ 重试次数用尽",
        }
        
        lines.append(f"**验证状态**: {status_text.get(status, status)}")
        lines.append(f"**重试次数**: {retry_count}")
        
        if review_issues:
            lines.append("\n**发现问题**:")
            for i, issue in enumerate(review_issues[:10], 1):
                severity = issue.get("severity", "unknown")
                msg = issue.get("message", "未知问题")
                
                icon = {
                    "minor": "🔹",
                    "critical": "🔴",
                    "incomplete": "🟡",
                }.get(severity, "•")
                
                workflow = issue.get("workflow")
                if workflow:
                    lines.append(f"{i}. {icon} **{workflow}**: {msg}")
                else:
                    lines.append(f"{i}. {icon} {msg}")
            
            if len(review_issues) > 10:
                lines.append(f"\n... 还有 {len(review_issues) - 10} 个问题")
        
        lines.append("\n---\n")
        
        return "\n".join(lines)
