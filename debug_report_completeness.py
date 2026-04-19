"""调试脚本：追踪报告生成的完整性

用于诊断为什么初始报告只覆盖了 47% 的 workflows。

使用方法：
    python debug_report_completeness.py <storage_dir>

示例：
    python debug_report_completeness.py .eval_data/pytorch_pytorch_20250407_164354
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Set


def load_ci_data(storage_dir: Path) -> Dict:
    """加载 CI 数据"""
    ci_data_path = storage_dir / "ci_data.json"
    if not ci_data_path.exists():
        print(f"❌ CI 数据文件不存在: {ci_data_path}")
        sys.exit(1)

    with open(ci_data_path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_batch_files(storage_dir: Path) -> List[Path]:
    """检查生成的 batch 文件"""
    batch_files = list(storage_dir.glob("prompt_workflow_*.txt"))
    script_files = list(storage_dir.glob("prompt_script_*.txt"))

    print(f"\n{'='*60}")
    print("1. Batch 文件生成检查")
    print(f"{'='*60}")
    print(f"  Workflow batch 文件: {len(batch_files)} 个")
    print(f"  Script batch 文件: {len(script_files)} 个")

    for f in sorted(batch_files):
        size = f.stat().st_size
        print(f"    - {f.name}: {size:,} 字节")

    return batch_files


def extract_workflows_from_batch(batch_file: Path) -> Set[str]:
    """从 batch 文件中提取 workflow 名称"""
    import re

    content = batch_file.read_text(encoding="utf-8")

    # 匹配 ### workflow-name.yml
    pattern = r'###\s+([\w.-]+\.yml)'
    matches = re.findall(pattern, content)

    return set(matches)


def check_batch_coverage(ci_data: Dict, batch_files: List[Path]) -> Dict:
    """检查 batch 文件覆盖的 workflows"""
    all_workflows = set(ci_data.get("workflows", {}).keys())

    print(f"\n{'='*60}")
    print("2. Batch 覆盖率检查")
    print(f"{'='*60}")
    print(f"  总 workflows: {len(all_workflows)} 个")

    covered_workflows = set()
    batch_coverage = {}

    for batch_file in sorted(batch_files):
        workflows = extract_workflows_from_batch(batch_file)
        covered_workflows.update(workflows)
        batch_coverage[batch_file.name] = workflows
        print(f"    - {batch_file.name}: {len(workflows)} 个 workflows")

    missing_workflows = all_workflows - covered_workflows

    print(f"\n  ✅ 已覆盖: {len(covered_workflows)}/{len(all_workflows)} ({len(covered_workflows)/len(all_workflows)*100:.1f}%)")

    if missing_workflows:
        print(f"  ❌ 未覆盖: {len(missing_workflows)} 个")
        print(f"\n  未覆盖的 workflows:")
        for wf in sorted(list(missing_workflows)[:20]):
            print(f"    - {wf}")
        if len(missing_workflows) > 20:
            print(f"    ... 还有 {len(missing_workflows) - 20} 个")

    return {
        "all_workflows": all_workflows,
        "covered_workflows": covered_workflows,
        "missing_workflows": missing_workflows,
        "batch_coverage": batch_coverage,
    }


def check_llm_responses(storage_dir: Path) -> Dict:
    """检查 LLM 响应文件"""
    response_file = storage_dir / "llm_response.md"

    print(f"\n{'='*60}")
    print("3. LLM 响应检查")
    print(f"{'='*60}")

    if not response_file.exists():
        print(f"  ❌ 响应文件不存在: {response_file}")
        return {"exists": False}

    content = response_file.read_text(encoding="utf-8")
    size = len(content)

    print(f"  ✅ 响应文件存在: {size:,} 字符")

    # 提取响应中的 workflow 详情
    import re
    pattern = r'####\s+\d+\.\d+\s+([\w.-]+\.yml)'
    workflows_in_response = set(re.findall(pattern, content))

    print(f"  包含 workflow 详情: {len(workflows_in_response)} 个")

    return {
        "exists": True,
        "size": size,
        "workflows_in_response": workflows_in_response,
    }


def check_final_report(storage_dir: Path, ci_data: Dict) -> Dict:
    """检查最终报告"""
    report_file = storage_dir / "CI_ARCHITECTURE.md"

    print(f"\n{'='*60}")
    print("4. 最终报告检查")
    print(f"{'='*60}")

    if not report_file.exists():
        print(f"  ❌ 报告文件不存在: {report_file}")
        return {"exists": False}

    content = report_file.read_text(encoding="utf-8")
    size = len(content)

    print(f"  ✅ 报告文件存在: {size:,} 字符")

    # 提取报告中的 workflow 详情
    import re
    pattern = r'####\s+\d+\.\d+\s+([\w.-]+\.yml)'
    workflows_in_report = set(re.findall(pattern, content))

    all_workflows = set(ci_data.get("workflows", {}).keys())
    coverage = len(workflows_in_report) / len(all_workflows) * 100 if all_workflows else 0

    print(f"  包含 workflow 详情: {len(workflows_in_report)}/{len(all_workflows)} ({coverage:.1f}%)")

    missing = all_workflows - workflows_in_report
    if missing:
        print(f"\n  ❌ 报告中缺失的 workflows ({len(missing)} 个):")
        for wf in sorted(list(missing)[:20]):
            print(f"    - {wf}")
        if len(missing) > 20:
            print(f"    ... 还有 {len(missing) - 20} 个")

    return {
        "exists": True,
        "size": size,
        "workflows_in_report": workflows_in_report,
        "coverage": coverage,
        "missing": missing,
    }


def main():
    if len(sys.argv) < 2:
        print("用法: python debug_report_completeness.py <storage_dir>")
        print("\n示例:")
        print("  python debug_report_completeness.py .eval_data/pytorch_pytorch_20250407_164354")
        sys.exit(1)

    storage_dir = Path(sys.argv[1])

    if not storage_dir.exists():
        print(f"❌ 目录不存在: {storage_dir}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"调试报告完整性")
    print(f"{'='*60}")
    print(f"存储目录: {storage_dir}")

    # 1. 加载 CI 数据
    ci_data = load_ci_data(storage_dir)

    # 2. 检查 batch 文件
    batch_files = check_batch_files(storage_dir)

    # 3. 检查 batch 覆盖率
    coverage_info = check_batch_coverage(ci_data, batch_files)

    # 4. 检查 LLM 响应
    response_info = check_llm_responses(storage_dir)

    # 5. 检查最终报告
    report_info = check_final_report(storage_dir, ci_data)

    # 6. 总结
    print(f"\n{'='*60}")
    print("总结")
    print(f"{'='*60}")

    all_workflows = coverage_info["all_workflows"]
    covered_in_batch = coverage_info["covered_workflows"]
    workflows_in_response = response_info.get("workflows_in_response", set())
    workflows_in_report = report_info.get("workflows_in_report", set())

    print(f"\n数据流失追踪:")
    print(f"  1. CI 数据中的 workflows: {len(all_workflows)} 个")
    print(f"  2. Batch 文件覆盖: {len(covered_in_batch)} 个 ({len(covered_in_batch)/len(all_workflows)*100:.1f}%)")

    if response_info.get("exists"):
        print(f"  3. LLM 响应包含: {len(workflows_in_response)} 个 ({len(workflows_in_response)/len(all_workflows)*100:.1f}%)")
        loss_in_llm = len(covered_in_batch) - len(workflows_in_response)
        if loss_in_llm > 0:
            print(f"     ⚠️ LLM 调用阶段丢失: {loss_in_llm} 个")

    if report_info.get("exists"):
        print(f"  4. 最终报告包含: {len(workflows_in_report)} 个 ({report_info['coverage']:.1f}%)")
        if response_info.get("exists"):
            loss_in_merge = len(workflows_in_response) - len(workflows_in_report)
            if loss_in_merge > 0:
                print(f"     ⚠️ 合并阶段丢失: {loss_in_merge} 个")

    # 7. 诊断建议
    print(f"\n{'='*60}")
    print("诊断建议")
    print(f"{'='*60}")

    if coverage_info["missing_workflows"]:
        print("\n❌ 问题 1: Batch 文件未覆盖所有 workflows")
        print("   原因: 分批逻辑可能有问题")
        print("   建议: 检查 generate_multi_round_prompts() 的分批逻辑")

    if response_info.get("exists") and len(workflows_in_response) < len(covered_in_batch):
        print("\n❌ 问题 2: LLM 响应丢失了部分 workflows")
        print("   原因: 某些 batch 文件可能没有被调用，或 LLM 调用失败")
        print("   建议: 检查 _parallel_calls() 的文件读取和错误处理")

    if report_info.get("exists") and len(workflows_in_report) < len(workflows_in_response):
        print("\n❌ 问题 3: 合并阶段丢失了部分 workflows")
        print("   原因: ResultMergingAgent 可能没有正确提取所有 workflow 详情")
        print("   建议: 检查 _extract_and_organize_stages() 的提取逻辑")

    if not coverage_info["missing_workflows"] and report_info.get("coverage", 0) < 100:
        print("\n❌ 问题 4: Batch 覆盖完整，但最终报告不完整")
        print("   原因: LLM 响应可能不完整，或合并逻辑有问题")
        print("   建议: 检查 LLM 响应的完整性和 ResultMergingAgent 的合并逻辑")


if __name__ == "__main__":
    main()
