"""完整性验证工具 - 检查 CI/CD 分析的完整工作流覆盖率

该工具会验证从原始 CI 数据到最终报告的整个流程中，
是否有工作流在过程中丢失。

使用方法：
1. 在分析之前，记录原始工作流列表
2. 在分析之后，检查最终报告中的工作流覆盖率
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Set


def load_ci_data(ci_data_path: str) -> Dict:
    """加载 CI 数据文件"""
    with open(ci_data_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def extract_workflows_from_ci_data(ci_data: Dict) -> Set[str]:
    """从 CI 数据中提取所有工作流名称"""
    return set(ci_data.get("workflows", {}).keys())


def extract_workflows_from_report(report_path: str) -> Set[str]:
    """从报告中提取工作流详情名称"""
    with open(report_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 匹配 #### [数字.] workflow-name.yml 格式
    pattern = r'####\s+(?:\d+\.?\d*\s+)?([\w\.-]+\.yml)'
    matches = re.findall(pattern, content)

    return set(matches)


def extract_workflows_from_prompts(prompt_dir: str) -> Dict[str, Set[str]]:
    """从 prompt 文件中提取包含的工作流"""
    prompt_path = Path(prompt_dir)
    workflow_batches = {}

    for prompt_file in prompt_path.glob("prompt_workflow_*.txt"):
        content = prompt_file.read_text(encoding='utf-8')

        # 提取工作流名称
        pattern = r'###\s+([\w.-]+\.yml)'
        matches = re.findall(pattern, content)

        workflow_batches[prompt_file.name] = set(matches)

    return workflow_batches


def check_integrity(ci_data_path: str, report_path: str, prompt_dir: str = None):
    """检查完整性的主函数"""
    print("=" * 60)
    print("CI/CD 分析完整性检查")
    print("=" * 60)

    # 1. 加载原始 CI 数据
    ci_data = load_ci_data(ci_data_path)
    original_workflows = extract_workflows_from_ci_data(ci_data)

    print(f"原始 CI 数据中的工作流: {len(original_workflows)} 个")
    if len(original_workflows) <= 20:
        for wf in sorted(original_workflows):
            print(f"  - {wf}")
    else:
        for wf in sorted(list(original_workflows)[:20]):
            print(f"  - {wf}")
        print(f"  ... 还有 {len(original_workflows) - 20} 个")

    print()

    # 2. 检查 prompt 分批情况（如果提供了目录）
    if prompt_dir:
        workflow_batches = extract_workflows_from_prompts(prompt_dir)
        print(f"Prompt 分批情况: {len(workflow_batches)} 个批次")

        covered_in_prompts = set()
        for batch_name, workflows in workflow_batches.items():
            print(f"  {batch_name}: {len(workflows)} 个")
            covered_in_prompts.update(workflows)

        print(f"  所有批次覆盖: {len(covered_in_prompts)} 个")

        # 检查是否所有原始工作流都在 prompt 中
        uncovered_prompts = original_workflows - covered_in_prompts
        if uncovered_prompts:
            print(f"  ❌ Prompt 阶段遗漏: {len(uncovered_prompts)} 个")
            for wf in sorted(uncovered_prompts):
                print(f"    - {wf}")
        else:
            print(f"  ✅ Prompt 阶段无遗漏")

        print()

    # 3. 检查最终报告
    report_workflows = extract_workflows_from_report(report_path)
    print(f"最终报告中的工作流: {len(report_workflows)} 个")

    if len(report_workflows) <= 20:
        for wf in sorted(report_workflows):
            print(f"  - {wf}")
    else:
        for wf in sorted(list(report_workflows)[:20]):
            print(f"  - {wf}")
        print(f"  ... 还有 {len(report_workflows) - 20} 个")

    print()

    # 4. 完整性对比
    if prompt_dir:
        uncovered_reports = covered_in_prompts - report_workflows
    else:
        uncovered_reports = original_workflows - report_workflows

    print("完整性分析:")
    coverage_rate = len(report_workflows) / len(original_workflows) * 100 if original_workflows else 0
    print(f"  最终覆盖率: {len(report_workflows)}/{len(original_workflows)} ({coverage_rate:.1f}%)")

    if uncovered_reports:
        print(f"  ❌ 最终报告遗漏: {len(uncovered_reports)} 个")
        for wf in sorted(list(uncovered_reports)[:20]):
            print(f"    - {wf}")
        if len(uncovered_reports) > 20:
            print(f"    ... 还有 {len(uncovered_reports) - 20} 个")
    else:
        print(f"  ✅ 无工作流遗漏")

    print()
    print("=" * 60)
    print("完整性检查完成")
    print("=" * 60)


def main():
    import sys

    if len(sys.argv) < 3:
        print("用法: python integrity_checker.py <ci_data.json> <report.md> [prompt_directory]")
        print()
        print("示例:")
        print("  python integrity_checker.py .eval_data/my_project/ci_data.json .eval_data/my_project/CI_ARCHITECTURE.md .eval_data/my_project/")
        return

    ci_data_path = sys.argv[1]
    report_path = sys.argv[2]
    prompt_dir = sys.argv[3] if len(sys.argv) > 3 else None

    if not Path(ci_data_path).exists():
        print(f"错误: CI 数据文件不存在 - {ci_data_path}")
        return

    if not Path(report_path).exists():
        print(f"错误: 报告文件不存在 - {report_path}")
        return

    if prompt_dir and not Path(prompt_dir).exists():
        print(f"警告: Prompt 目录不存在 - {prompt_dir}")
        prompt_dir = None

    check_integrity(ci_data_path, report_path, prompt_dir)


if __name__ == "__main__":
    main()