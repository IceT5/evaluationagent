"""Git 操作 Skill"""
import subprocess
from pathlib import Path


class GitOperations:
    """Git 相关操作"""

    @staticmethod
    def clone(url: str, target_dir: str, branch: str = None) -> dict:
        """
        克隆仓库

        Args:
            url: Git 仓库地址
            target_dir: 目标目录（包含仓库名的完整路径）
            branch: 指定分支（可选）

        Returns:
            {
                "success": bool,
                "path": str,      # 克隆到的路径
                "error": str      # 失败原因（如果 success=False）
            }
        """
        target_path = Path(target_dir)

        # 如果目录已存在，直接返回
        if target_path.exists() and (target_path / ".git").exists():
            return {
                "success": True,
                "path": str(target_path),
                "error": None,
                "skipped": True,
                "message": "目录已存在，跳过克隆",
            }

        # 创建父目录
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # 构建命令
        cmd = ["git", "clone", "--depth", "1"]
        if branch:
            cmd.extend(["--branch", branch])
        cmd.extend([url, str(target_path)])

        try:
            print(f"正在克隆: {url}")
            print(f"目标目录: {target_path}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5分钟超时
            )

            if result.returncode == 0:
                return {
                    "success": True,
                    "path": str(target_path),
                    "error": None,
                    "skipped": False,
                    "message": "克隆成功",
                }
            else:
                error_msg = result.stderr.strip() or result.stdout.strip()
                return {
                    "success": False,
                    "path": None,
                    "error": error_msg,
                    "skipped": False,
                    "message": f"克隆失败: {error_msg}",
                }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "path": None,
                "error": "克隆超时（5分钟）",
                "skipped": False,
                "message": "克隆超时",
            }
        except FileNotFoundError:
            return {
                "success": False,
                "path": None,
                "error": "未找到 git 命令，请确保已安装 Git",
                "skipped": False,
                "message": "Git 未安装",
            }
        except Exception as e:
            return {
                "success": False,
                "path": None,
                "error": str(e),
                "skipped": False,
                "message": f"未知错误: {e}",
            }

    @staticmethod
    def is_git_repo(path: str) -> bool:
        """判断是否为 Git 仓库"""
        return (Path(path) / ".git").exists()

    @staticmethod
    def get_remote_url(path: str) -> str | None:
        """获取远程仓库地址"""
        try:
            result = subprocess.run(
                ["git", "-C", path, "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None
