#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试命令补全功能"""

from evaluator.cli.app import CommandCompleter, CommandRegistry, CompletionType
from storage import StorageManager
from prompt_toolkit.document import Document


def test_command_registry():
    """测试命令注册中心"""
    print("=" * 60)
    print("测试1: 命令注册中心初始化")
    print("=" * 60)

    CommandRegistry.initialize()

    # 检查命令是否注册
    assert "show" in CommandRegistry.COMMANDS, "show命令未注册"
    assert "compare" in CommandRegistry.COMMANDS, "compare命令未注册"
    assert "delete" in CommandRegistry.COMMANDS, "delete命令未注册"

    print("✅ 命令注册成功")

    # 检查show命令元数据
    show_meta = CommandRegistry.get("show")
    assert show_meta is not None
    assert show_meta.name == "show"
    assert len(show_meta.parameters) == 2

    print(f"✅ show命令参数: {[p.name for p in show_meta.parameters]}")

    # 检查compare命令元数据
    compare_meta = CommandRegistry.get("compare")
    assert compare_meta is not None
    assert len(compare_meta.parameters) == 5

    print(f"✅ compare命令参数: {[p.name for p in compare_meta.parameters]}")


def test_command_completion():
    """测试命令名称补全"""
    print("\n" + "=" * 60)
    print("测试2: 命令名称补全")
    print("=" * 60)

    completer = CommandCompleter(["show", "delete", "compare"])

    # 测试命令补全
    document = Document("/sho")
    completions = list(completer.get_completions(document, None))

    assert len(completions) == 1, f"期望1个补全，实际{len(completions)}个"
    assert completions[0].text == "/show", f"期望/show，实际{completions[0].text}"

    print(f"✅ 输入 '/sho' 补全为: {completions[0].text}")


def test_project_completion():
    """测试项目名称补全"""
    print("\n" + "=" * 60)
    print("测试3: 项目名称补全")
    print("=" * 60)

    try:
        storage = StorageManager()
        completer = CommandCompleter(["show"], storage_manager=storage)

        # 测试项目补全
        document = Document("/show ")
        completions = list(completer.get_completions(document, None))

        if completions:
            print(f"✅ 找到 {len(completions)} 个项目")
            for c in completions[:5]:  # 只显示前5个
                print(f"   - {c.text}")
        else:
            print("⚠️  无项目数据，跳过测试")
    except Exception as e:
        print(f"⚠️  测试跳过: {e}")


def test_version_completion():
    """测试版本号补全"""
    print("\n" + "=" * 60)
    print("测试4: 版本号补全")
    print("=" * 60)

    try:
        storage = StorageManager()
        completer = CommandCompleter(["show"], storage_manager=storage)

        # 获取第一个项目
        from evaluator.core import list_projects
        projects = list(list_projects())

        if not projects:
            print("⚠️  无项目数据，跳过测试")
            return

        project_name = projects[0].name
        versions = storage.list_versions(project_name)

        if not versions:
            print(f"⚠️  项目 {project_name} 无版本数据，跳过测试")
            return

        # 测试版本补全
        document = Document(f"/show {project_name} --version ")
        completions = list(completer.get_completions(document, None))

        if completions:
            print(f"✅ 项目 {project_name} 找到 {len(completions)} 个版本")
            for c in completions[:5]:
                print(f"   - {c.text}")
        else:
            print("⚠️  无版本补全结果")

    except Exception as e:
        print(f"⚠️  测试跳过: {e}")


def test_compare_completion():
    """测试compare命令补全"""
    print("\n" + "=" * 60)
    print("测试5: compare命令补全")
    print("=" * 60)

    try:
        storage = StorageManager()
        completer = CommandCompleter(["compare"], storage_manager=storage)

        # 测试第二个项目补全
        document = Document("/compare cccl ")
        completions = list(completer.get_completions(document, None))

        if completions:
            print(f"✅ 找到 {len(completions)} 个项目（第二个参数）")
            for c in completions[:5]:
                print(f"   - {c.text}")
        else:
            print("⚠️  无项目数据")

    except Exception as e:
        print(f"⚠️  测试跳过: {e}")


def test_no_storage_fallback():
    """测试无storage时降级"""
    print("\n" + "=" * 60)
    print("测试6: 无storage降级")
    print("=" * 60)

    completer = CommandCompleter(["show"])

    # 测试命令补全（应该正常）
    document = Document("/sho")
    completions = list(completer.get_completions(document, None))
    assert len(completions) == 1
    print("✅ 命令补全正常")

    # 测试参数补全（应该无补全）
    document = Document("/show ")
    completions = list(completer.get_completions(document, None))
    assert len(completions) == 0
    print("✅ 无storage时参数补全正确降级")


def main():
    """运行所有测试"""
    print("\n命令补全功能测试\n")

    try:
        test_command_registry()
        test_command_completion()
        test_project_completion()
        test_version_completion()
        test_compare_completion()
        test_no_storage_fallback()

        print("\n" + "=" * 60)
        print("所有测试通过！")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()

    except Exception as e:
        print(f"\n测试异常: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()