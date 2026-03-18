"""报告生成 Agent - 将 Markdown 报告转为交互式 HTML"""
import re
import json
from pathlib import Path
from typing import Optional


class ReporterAgent:
    """报告生成 Agent"""
    
    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = output_dir
    
    def run(self, state: dict) -> dict:
        cicd_analysis = state.get("cicd_analysis", {})
        project_name = state.get("project_name", "unknown")
        project_path = state.get("project_path", "")
        
        md_path = cicd_analysis.get("report_path")
        if not md_path:
            md_path = str(Path(project_path) / "CI_ARCHITECTURE.md")
        
        architecture_json_path = cicd_analysis.get("architecture_json_path")
        if not architecture_json_path:
            architecture_json_path = str(Path(project_path) / "architecture.json")
        
        ci_data_path = cicd_analysis.get("ci_data_path")
        if not ci_data_path:
            ci_data_path = str(Path(project_path) / "ci_data.json")
        
        if not Path(md_path).exists():
            print(f"\n⚠️ 未找到 Markdown 报告: {md_path}")
            return {
                "current_step": "reporter",
                "html_report": None,
                "report_path": None,
                "errors": ["未找到 Markdown 报告"],
            }
        
        print(f"\n{'='*50}")
        print("  报告生成")
        print(f"{'='*50}")
        
        with open(md_path, "r", encoding="utf-8") as f:
            md_content = f.read()
        
        print("\n[1/3] 解析数据...")
        
        # 读取架构图 JSON
        architecture_data = self._load_architecture_json(architecture_json_path)
        if architecture_data and architecture_data.get("layers"):
            print(f"  读取到 {len(architecture_data['layers'])} 个架构层")
        
        # 提取工作流详情
        workflow_details = self._extract_workflow_details(md_content)
        print(f"  提取到 {len(workflow_details)} 个工作流详情")
        
        # 提取项目概述
        overview = self._extract_overview(md_content)
        
        # 提取附录
        appendix = self._extract_appendix(md_content)
        
        # 提取关键发现
        findings = self._extract_findings(md_content)
        
        # 读取脚本信息
        scripts_section = self._generate_scripts_section(ci_data_path)
        
        print("\n[2/3] 生成交互式 HTML...")
        
        # 根据架构图层级重新组织内容
        html_content = self._generate_html(
            overview=overview,
            architecture_data=architecture_data,
            workflow_details=workflow_details,
            scripts_section=scripts_section,
            findings=findings,
            appendix=appendix,
            project_name=project_name
        )
        
        print("\n[3/3] 保存报告...")
        
        if self.output_dir:
            output_path = Path(self.output_dir)
        else:
            output_path = Path(project_path)
        output_path.mkdir(parents=True, exist_ok=True)
        
        html_path = output_path / f"{project_name}_interactive_report.html"
        html_path.write_text(html_content, encoding="utf-8")
        
        print(f"\n{'='*50}")
        print("  报告生成完成!")
        print(f"{'='*50}")
        print(f"  HTML 报告: {html_path}")
        
        self._open_browser(html_path)
        
        return {
            "current_step": "reporter",
            "html_report": str(html_path),
            "report_path": str(html_path),
            "errors": [],
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
        match = re.search(r'^##\s+附录\s*$(.*)', content, re.MULTILINE | re.DOTALL)
        if match:
            return f"## 附录{match.group(1)}"
        return ""
    
    def _extract_findings(self, content: str) -> str:
        """提取关键发现和建议"""
        match = re.search(r'^##\s+.*发现.*建议\s*$(.*?)(?=^##\s+)', content, re.MULTILINE | re.DOTALL)
        if match:
            return f"## 关键发现和建议{match.group(1)}"
        return ""
    
    def _extract_workflow_details(self, content: str) -> dict:
        """提取工作流详情"""
        details = {}
        
        # 匹配 #### X.X xxx.yml 格式
        pattern = r'####\s+(\d+\.\d+)\s+([\w-]+\.yml)'
        for match in re.finditer(pattern, content):
            num = match.group(1)
            name = match.group(2).strip()
            
            start = match.end()
            # 找到下一个同级标题
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
            
            # 提取描述（第一行通常是描述）
            lines = detail_content.split('\n')
            desc = lines[0].strip() if lines else ""
            if desc.startswith('-'):
                desc = desc[1:].strip()
            
            # 使用工作流文件名作为 key
            anchor = self._to_anchor(name)
            details[anchor] = {
                "num": num,
                "name": name,
                "desc": desc,
                "content": detail_content,
            }
            
            # 也按文件名索引（去掉 .yml）
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
        
        # CI 相关脚本
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
        project_name: str
    ) -> str:
        """生成交互式 HTML"""
        
        # 生成导航
        nav_items = [
            '<li><a href="#overview" class="nav-link">项目概述</a></li>',
            '<li><a href="#architecture" class="nav-link">CI/CD 整体架构图</a></li>',
        ]
        
        # 根据架构图层生成导航
        layers = architecture_data.get("layers", [])
        for i, layer in enumerate(layers):
            layer_name = layer.get("name", f"阶段{i+1}")
            anchor = f"stage-{i+1}"
            nav_items.append(f'<li><a href="#{anchor}" class="nav-link">{layer_name}</a></li>')
        
        nav_items.extend([
            '<li><a href="#scripts" class="nav-link">脚本目录索引</a></li>',
            '<li><a href="#findings" class="nav-link">关键发现和建议</a></li>',
            '<li><a href="#appendix" class="nav-link">附录</a></li>',
        ])
        
        # 生成架构图
        architecture_html = self._generate_architecture_graphic(architecture_data)
        
        # 生成各阶段内容
        stage_contents = self._generate_stage_contents(architecture_data, workflow_details)
        
        # 生成完整 HTML
        html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{project_name} - CI/CD 架构分析报告</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
        }}
        .container {{
            max-width: 1600px;
            margin: 0 auto;
            display: flex;
            min-height: 100vh;
        }}
        .sidebar {{
            width: 280px;
            background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
            color: #fff;
            padding: 20px;
            position: fixed;
            top: 0;
            left: 0;
            height: 100vh;
            overflow-y: auto;
            z-index: 100;
        }}
        .sidebar h1 {{
            font-size: 18px;
            margin-bottom: 10px;
            padding-bottom: 15px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}
        .sidebar ul {{ list-style: none; }}
        .sidebar li {{ margin: 4px 0; }}
        .sidebar a {{
            color: #a0a0a0;
            text-decoration: none;
            font-size: 14px;
            display: block;
            padding: 10px 12px;
            border-radius: 6px;
            transition: all 0.2s;
        }}
        .sidebar a:hover, .sidebar a.active {{
            background: rgba(52, 152, 219, 0.2);
            color: #3498db;
        }}
        .main {{
            flex: 1;
            margin-left: 280px;
            padding: 30px 40px;
            background: #fff;
            min-height: 100vh;
        }}
        .section {{
            margin-bottom: 40px;
            padding-bottom: 30px;
            border-bottom: 1px solid #eee;
        }}
        .section h2 {{
            color: #1a1a2e;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #3498db;
            font-size: 24px;
        }}
        .section h3 {{ color: #2c3e50; margin: 25px 0 15px; font-size: 18px; }}
        .section h4 {{ color: #7f8c8d; margin: 15px 0 10px; font-size: 16px; }}
        .architecture-container {{
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            border-radius: 12px;
            padding: 30px;
            margin: 20px 0;
            overflow-x: auto;
        }}
        .arch-layer {{ margin-bottom: 25px; }}
        .arch-layer-title {{
            color: #3498db;
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 12px;
            padding-left: 10px;
            border-left: 3px solid #3498db;
        }}
        .arch-nodes {{
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            justify-content: flex-start;
        }}
        .arch-node {{
            background: rgba(255,255,255,0.1);
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 8px;
            padding: 12px 16px;
            color: #fff;
            cursor: pointer;
            transition: all 0.3s;
            min-width: 160px;
            text-align: center;
        }}
        .arch-node:hover {{
            background: rgba(52, 152, 219, 0.3);
            border-color: #3498db;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(52, 152, 219, 0.3);
        }}
        .arch-node.active {{
            background: rgba(52, 152, 219, 0.4);
            border-color: #3498db;
        }}
        .arch-node-title {{ font-weight: 600; margin-bottom: 4px; }}
        .arch-node-desc {{ font-size: 12px; color: #a0a0a0; }}
        .arch-connector {{
            text-align: center;
            color: #3498db;
            font-size: 24px;
            margin: 15px 0;
        }}
        .workflow-card {{
            background: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 8px;
            padding: 20px;
            margin: 15px 0;
        }}
        .workflow-card h4 {{
            color: #1a1a2e;
            margin: 0 0 15px 0;
            padding-bottom: 10px;
            border-bottom: 1px solid #dee2e6;
        }}
        .workflow-card .meta {{
            display: flex;
            gap: 20px;
            margin-bottom: 15px;
            flex-wrap: wrap;
        }}
        .workflow-card .meta-item {{
            background: #e9ecef;
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 13px;
        }}
        .workflow-card pre {{
            background: #f4f4f4;
            padding: 12px;
            border-radius: 6px;
            overflow-x: auto;
            font-size: 13px;
        }}
        .workflow-card code {{
            background: #f4f4f4;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 13px;
        }}
        .workflow-card table {{
            width: 100%;
            border-collapse: collapse;
            margin: 10px 0;
        }}
        .workflow-card th, .workflow-card td {{
            padding: 8px 10px;
            text-align: left;
            border-bottom: 1px solid #eee;
            font-size: 13px;
        }}
        .workflow-card th {{
            background: #f8f9fa;
            font-weight: 600;
        }}
        .workflow-card ul {{
            margin: 10px 0 10px 20px;
        }}
        .highlight {{
            background: #fffde7 !important;
            animation: highlight-fade 2s ease;
        }}
        @keyframes highlight-fade {{
            from {{ background: #fffde7; }}
            to {{ background: transparent; }}
        }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #f8f9fa; font-weight: 600; }}
        tr:hover {{ background: #f8f9fa; }}
        pre {{ background: #f4f4f4; padding: 15px; border-radius: 4px; overflow-x: auto; font-size: 13px; line-height: 1.5; }}
        code {{ background: #f4f4f4; padding: 2px 6px; border-radius: 3px; font-size: 13px; }}
        ul, ol {{ margin: 10px 0 10px 25px; }}
        li {{ margin: 5px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <nav class="sidebar">
            <h1>📋 {project_name}</h1>
            <p style="font-size: 12px; color: #a0a0a0; margin-bottom: 20px;">CI/CD 架构分析报告</p>
            <ul>
                {''.join(nav_items)}
            </ul>
        </nav>
        <main class="main">
            <!-- 项目概述 -->
            <section id="overview" class="section">
                <h2>项目概述</h2>
                <div class="content">
                    {self._md_to_html(overview.replace('## 项目概述', '').strip()) if overview else '<p>暂无概述</p>'}
                </div>
            </section>
            
            <!-- CI/CD 整体架构图 -->
            <section id="architecture" class="section">
                <h2>CI/CD 整体架构图</h2>
                {architecture_html}
            </section>
            
            <!-- 各阶段详情 -->
            {stage_contents}
            
            <!-- 脚本目录索引 -->
            <section id="scripts" class="section">
                <h2>脚本目录索引</h2>
                <div class="content">
                    {self._md_to_html(scripts_section.replace('## 脚本目录索引', '').strip()) if scripts_section else '<p>暂无脚本信息</p>'}
                </div>
            </section>
            
            <!-- 关键发现和建议 -->
            <section id="findings" class="section">
                <h2>关键发现和建议</h2>
                <div class="content">
                    {self._md_to_html(findings.replace('## 关键发现和建议', '').strip()) if findings else '<p>暂无发现和建议</p>'}
                </div>
            </section>
            
            <!-- 附录 -->
            <section id="appendix" class="section">
                <h2>附录</h2>
                <div class="content">
                    {self._md_to_html(appendix.replace('## 附录', '').strip()) if appendix else '<p>暂无附录</p>'}
                </div>
            </section>
        </main>
    </div>
    
    <script>
        const workflowDetails = {json.dumps(workflow_details, ensure_ascii=False)};
        const architectureData = {json.dumps(architecture_data, ensure_ascii=False)};
        
        // 建立节点到锚点的映射
        const nodeAnchorMap = {{}};
        architectureData.layers && architectureData.layers.forEach((layer, layerIndex) => {{
            layer.nodes && layer.nodes.forEach(node => {{
                // 使用 label 作为 key（去掉 .yml 后缀）
                let key = node.label.replace(/\\.yml$/, '').replace(/\\.yml/g, '');
                nodeAnchorMap[key] = node.detail_section;
                nodeAnchorMap[node.label] = node.detail_section;
                nodeAnchorMap[node.id] = node.detail_section;
            }});
        }});
        
        function showDetail(nodeId, nodeLabel) {{
            console.log('showDetail called:', nodeId, nodeLabel);
            
            // 查找对应的详情
            let detail = null;
            let anchor = null;
            
            // 1. 尝试通过 nodeLabel 找到 detail_section
            if (nodeAnchorMap[nodeLabel]) {{
                anchor = nodeAnchorMap[nodeLabel];
            }} else if (nodeAnchorMap[nodeId]) {{
                anchor = nodeAnchorMap[nodeId];
            }}
            
            // 2. 尝试从 workflowDetails 中查找
            for (const key in workflowDetails) {{
                const wf = workflowDetails[key];
                const cleanLabel = nodeLabel.replace(/\\.yml/g, '');
                if (key.includes(cleanLabel) || wf.name.includes(cleanLabel) || cleanLabel.includes(wf.name.replace(/\\.yml/g, ''))) {{
                    detail = wf;
                    break;
                }}
            }}
            
            // 3. 如果找到详情，滚动到对应位置
            if (anchor) {{
                const targetAnchor = toAnchor(anchor);
                const target = document.getElementById(targetAnchor);
                if (target) {{
                    target.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
                    target.classList.add('highlight');
                    setTimeout(() => target.classList.remove('highlight'), 2000);
                    return;
                }}
            }}
            
            // 4. 如果找到工作流详情，滚动到该卡片
            if (detail) {{
                const detailAnchor = toAnchor(detail.name);
                const target = document.getElementById(detailAnchor);
                if (target) {{
                    target.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
                    target.classList.add('highlight');
                    setTimeout(() => target.classList.remove('highlight'), 2000);
                    return;
                }}
            }}
            
            // 5. 尝试直接用 label 查找
            const labelAnchor = toAnchor(nodeLabel);
            const labelTarget = document.getElementById(labelAnchor);
            if (labelTarget) {{
                labelTarget.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
                labelTarget.classList.add('highlight');
                setTimeout(() => labelTarget.classList.remove('highlight'), 2000);
            }}
        }}
        
        function toAnchor(text) {{
            return text.replace(/[^\\w\\u4e00-\\u9fff-]/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '').toLowerCase();
        }}
        
        document.querySelectorAll('.nav-link').forEach(link => {{
            link.addEventListener('click', function() {{
                document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
                this.classList.add('active');
            }});
        }});
    </script>
</body>
</html>'''
        return html
    
    def _generate_architecture_graphic(self, architecture_data: dict) -> str:
        """根据 JSON 数据生成图形化架构图"""
        layers = architecture_data.get("layers", [])
        
        if not layers:
            return '''
        <div class="architecture-container">
            <p style="color: #a0a0a0;">📊 架构图数据未生成</p>
        </div>'''
        
        layer_html = []
        for layer in layers:
            layer_id = layer.get("id", "")
            layer_name = layer.get("name", "未命名层")
            nodes = layer.get("nodes", [])
            
            nodes_html = []
            for node in nodes:
                node_id = node.get("id", "")
                label = node.get("label", "未命名")
                description = node.get("description", "")
                detail_section = node.get("detail_section", "")
                
                nodes_html.append(f'''
                <div class="arch-node" onclick="showDetail('{node_id}', '{label}')">
                    <div class="arch-node-title">{label}</div>
                    <div class="arch-node-desc">{description}</div>
                </div>''')
            
            layer_html.append(f'''
            <div class="arch-layer">
                <div class="arch-layer-title">{layer_name}</div>
                <div class="arch-nodes">
                    {''.join(nodes_html)}
                </div>
            </div>''')
            
            layer_html.append('<div class="arch-connector">↓</div>')
        
        result = ''.join(layer_html)
        if result.endswith('<div class="arch-connector">↓</div>'):
            result = result[:-len('<div class="arch-connector">↓</div>')]
        
        return f'''
        <div class="architecture-container">
            {result}
        </div>
        <p style="color: #666; font-size: 14px; margin-top: 15px;">
            💡 点击架构图中的节点可跳转到详细内容
        </p>'''
    
    def _generate_stage_contents(self, architecture_data: dict, workflow_details: dict) -> str:
        """根据架构图层生成各阶段内容"""
        layers = architecture_data.get("layers", [])
        sections = []
        
        for i, layer in enumerate(layers):
            layer_name = layer.get("name", f"阶段{i+1}")
            layer_id = f"stage-{i+1}"
            nodes = layer.get("nodes", [])
            
            # 生成该阶段的工作流卡片
            workflow_cards = []
            for node in nodes:
                node_label = node.get("label", "")
                node_desc = node.get("description", "")
                detail_section = node.get("detail_section", "")
                
                # 查找对应的工作流详情
                detail = None
                clean_label = node_label.replace(".yml", "")
                
                for key, wf in workflow_details.items():
                    if clean_label in key or clean_label in wf.get("name", ""):
                        detail = wf
                        break
                
                if detail:
                    card_html = f'''
                <div class="workflow-card" id="{self._to_anchor(detail['name'])}">
                    <h4>{detail['name']} - {detail['desc']}</h4>
                    <div class="meta">
                        <span class="meta-item">编号: {detail['num']}</span>
                    </div>
                    <div class="content">
                        {self._md_to_html(detail['content'])}
                    </div>
                </div>'''
                    workflow_cards.append(card_html)
                else:
                    # 没有找到详情，生成简单卡片
                    card_html = f'''
                <div class="workflow-card" id="{self._to_anchor(node_label)}">
                    <h4>{node_label}</h4>
                    <p>{node_desc}</p>
                </div>'''
                    workflow_cards.append(card_html)
            
            section_html = f'''
        <section id="{layer_id}" class="section">
            <h2>{layer_name}</h2>
            {''.join(workflow_cards) if workflow_cards else '<p>暂无工作流详情</p>'}
        </section>'''
            sections.append(section_html)
        
        return '\n'.join(sections)
    
    def _md_to_html(self, md_content: str) -> str:
        """将 Markdown 内容转为 HTML"""
        if not md_content:
            return ""
        
        html = md_content
        
        # 代码块
        html = re.sub(r'```\n?', '<pre>', html)
        html = re.sub(r'```', '</pre>', html)
        html = re.sub(r'`([^`]+)`', r'<code>\1</code>', html)
        
        # 表格
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
        
        # 标题
        html = re.sub(r'^####\s+(.+)$', r'<h4>\1</h4>', html, flags=re.MULTILINE)
        html = re.sub(r'^###\s+(.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        
        # 粗体和斜体
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
        
        # 列表
        lines = html.split('\n')
        result = []
        in_list = False
        
        for line in lines:
            if re.match(r'^\s*[-*]\s+', line):
                if not in_list:
                    result.append('<ul>')
                    in_list = True
                result.append('<li>' + line.lstrip('-* ').strip() + '</li>')
            elif re.match(r'^\s*\d+\.\s+', line):
                if not in_list:
                    result.append('<ol>')
                    in_list = True
                result.append('<li>' + re.sub(r'^\s*\d+\.\s+', '', line) + '</li>')
            else:
                if in_list:
                    result.append('</ul>')
                    in_list = False
                result.append(line)
        
        if in_list:
            result.append('</ul>')
        
        html = '\n'.join(result)
        html = re.sub(r'^---$', '<hr>', html, flags=re.MULTILINE)
        
        return html
    
    def _open_browser(self, html_path: Path):
        import webbrowser
        import urllib.parse
        
        try:
            url = f"file:///{urllib.parse.quote(str(html_path.absolute()))}"
            webbrowser.open(url)
            print(f"  已在浏览器中打开报告")
        except Exception as e:
            print(f"  无法自动打开浏览器: {e}")