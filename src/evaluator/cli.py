"""CLI 命令 - list, compare"""
import sys
import io
import argparse
from pathlib import Path
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

from storage import StorageManager
from evaluator.agents.compare_agent import CompareAgent, CompareInput


def cmd_list(args):
    storage = StorageManager()
    
    if args.all:
        info = storage.get_storage_info()
        print("\n" + "=" * 50)
        print("  存储概览")
        print("=" * 50)
        print(f"  数据目录: {info['data_dir']}")
        print(f"  项目数量: {info['project_count']}")
        print(f"  对比数量: {info['comparison_count']}")
        print(f"  总大小:   {info['total_size_mb']} MB")
        print()
    
    projects = storage.list_projects()
    if not projects:
        print("\n暂无已保存的项目")
        return
    
    print("\n" + "=" * 50)
    print("  已保存的项目")
    print("=" * 50)
    print(f"{'项目名称':<30} {'版本数':<10} {'最新版本':<20}")
    print("-" * 60)
    
    for project_name in projects:
        versions = storage.list_versions(project_name)
        metadata = storage.get_project_metadata(project_name)
        display_name = metadata.display_name if metadata and metadata.display_name else project_name
        latest = versions[-1] if versions else "N/A"
        print(f"{display_name:<30} {len(versions):<10} {latest:<20}")
    
    if args.show_versions:
        for project_name in projects:
            versions = storage.list_versions(project_name)
            if versions:
                print(f"\n{project_name} 的版本:")
                for v in versions:
                    try:
                        data = storage.load_project(project_name, v)
                        if data:
                            meta = data.get("metadata", {})
                            analyzed = meta.get("analyzed_at", "N/A")
                            source = meta.get("source_url", meta.get("source_path", "N/A"))
                            print(f"  - {v}")
                            print(f"    分析时间: {analyzed[:19] if len(analyzed) > 19 else analyzed}")
                            print(f"    来源: {source}")
                    except Exception:
                        pass


def cmd_compare(args):
    storage = StorageManager()
    
    if args.list_comparisons:
        comparisons = storage.list_comparisons()
        if not comparisons:
            print("\n暂无对比记录")
            return
        
        print("\n" + "=" * 50)
        print("  历史对比记录")
        print("=" * 50)
        for comp in comparisons:
            created = comp.get("created_at", "N/A")
            if len(created) > 19:
                created = created[:19]
            print(f"\n{comp.get('comparison_id')}")
            print(f"  项目A: {comp.get('project_a')}")
            print(f"  项目B: {comp.get('project_b')}")
            print(f"  时间:  {created}")
        return
    
    if not args.project_a or not args.project_b:
        print("\n错误: 请指定要对比的两个项目 (--project-a 和 --project-b)")
        print("或使用 --list 查看历史对比记录")
        return
    
    input_data: CompareInput = {
        "project_a": args.project_a,
        "project_b": args.project_b,
        "version_a": args.version_a,
        "version_b": args.version_b,
        "dimensions": None,
    }
    
    agent = CompareAgent(storage)
    result = agent.run(input_data)
    
    if "error" in result:
        print(f"\n错误: {result['error']}")
        return
    
    print("\n" + "=" * 50)
    print("  对比完成")
    print("=" * 50)
    print(f"  项目 A: {result['project_a']} ({result['version_a']})")
    print(f"  项目 B: {result['project_b']} ({result['version_b']})")
    print(f"  对比 ID: {result['comparison_id']}")
    
    print("\n维度得分:")
    for dim in result.get("dimension_results", []):
        winner = dim.get("winner", "N/A")
        winner_name = result["project_a"] if winner == "A" else (result["project_b"] if winner == "B" else "平手")
        print(f"  {dim['name']}: {result['project_a']}={dim['score_a']} | {result['project_b']}={dim['score_b']} | 胜出: {winner_name}")
    
    if args.show_summary:
        print("\n总结:")
        print(result.get("summary", ""))
    
    if args.show_recommendations:
        print("\n改进建议:")
        for i, rec in enumerate(result.get("recommendations", []), 1):
            print(f"  {i}. {rec}")
    
    if args.open:
        try:
            import webbrowser
            html_path = storage.data_dir / "comparisons" / result["comparison_id"] / "compare.html"
            webbrowser.open(f"file:///{html_path}")
            print(f"\n已在浏览器中打开对比报告")
        except Exception as e:
            print(f"\n打开浏览器失败: {e}")
    
    if args.save_markdown:
        try:
            import json
            md_path = storage.data_dir / "comparisons" / result["comparison_id"] / "compare.md"
            print(f"\nMarkdown 报告: {md_path}")
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="CI/CD 架构评估工具")
    subparsers = parser.add_subparsers(dest="command", help="子命令")
    
    list_parser = subparsers.add_parser("list", help="列出已保存的项目")
    list_parser.add_argument("-a", "--all", action="store_true", help="显示存储概览")
    list_parser.add_argument("-v", "--show-versions", action="store_true", help="显示各项目的版本详情")
    
    compare_parser = subparsers.add_parser("compare", help="对比两个项目")
    compare_parser.add_argument("-l", "--list-comparisons", action="store_true", help="列出历史对比记录")
    compare_parser.add_argument("--project-a", type=str, help="项目A名称")
    compare_parser.add_argument("--project-b", type=str, help="项目B名称")
    compare_parser.add_argument("--version-a", type=str, help="项目A版本 (默认最新)")
    compare_parser.add_argument("--version-b", type=str, help="项目B版本 (默认最新)")
    compare_parser.add_argument("-s", "--show-summary", action="store_true", help="显示对比总结")
    compare_parser.add_argument("-r", "--show-recommendations", action="store_true", help="显示改进建议")
    compare_parser.add_argument("-o", "--open", action="store_true", help="在浏览器中打开对比报告")
    compare_parser.add_argument("--save-markdown", action="store_true", help="显示Markdown保存路径")
    
    args = parser.parse_args()
    
    if args.command == "list":
        cmd_list(args)
    elif args.command == "compare":
        cmd_compare(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
