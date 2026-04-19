"""测试修复后的 workflow 提取逻辑"""
import re
from pathlib import Path

def extract_workflows_new_method(content: str):
    """使用新的提取逻辑"""
    # 直接提取所有 #### workflow.yml 详情块
    wf_pattern = r'(####\s+(?:\d+\.?\d*\s+)?([\w\.-]+\.yml).*?)(?=####\s+|##\s+|$)'
    wf_matches = re.findall(wf_pattern, content, re.DOTALL)

    # 按 workflow 名称去重
    seen_workflows = {}
    for wf_full, wf_name in wf_matches:
        if wf_name and ('.yml' in wf_name or '.yaml' in wf_name):
            if wf_name not in seen_workflows:
                seen_workflows[wf_name] = wf_full.strip()

    return seen_workflows

# 读取 llm_response.md
response_path = Path(r"F:\eval-agent\data\projects\pytorch\v11_20260415_000156\llm_response.md")
content = response_path.read_text(encoding='utf-8')

print("测试新的 workflow 提取逻辑")
print("=" * 60)

workflows = extract_workflows_new_method(content)

print(f"提取到的唯一 workflow 数量: {len(workflows)}")
print(f"\n前 20 个 workflow:")
for i, wf_name in enumerate(sorted(workflows.keys())[:20], 1):
    print(f"  {i}. {wf_name}")

if len(workflows) > 20:
    print(f"  ... 还有 {len(workflows) - 20} 个")

# 检查是否达到预期的 139 个
print(f"\n预期: 139 个")
print(f"实际: {len(workflows)} 个")
if len(workflows) == 139:
    print("✅ 提取完整！")
elif len(workflows) > 130:
    print(f"⚠️ 接近完整，差 {139 - len(workflows)} 个")
else:
    print(f"❌ 仍有遗漏，差 {139 - len(workflows)} 个")
