"""URL 解析 Skill"""
import re
from urllib.parse import urlparse


class UrlParser:
    """URL 解析"""

    # 支持的代码托管平台
    PLATFORMS = {
        "github.com": "github",
        "gitlab.com": "gitlab",
        "gitee.com": "gitee",
        "bitbucket.org": "bitbucket",
    }

    @staticmethod
    def is_url(text: str) -> bool:
        """判断是否为 URL"""
        return text.startswith(("http://", "https://", "git@"))

    @staticmethod
    def parse(text: str) -> dict:
        """
        解析代码平台 URL

        支持格式：
        - https://github.com/owner/repo
        - https://github.com/owner/repo.git
        - git@github.com:owner/repo.git
        - https://gitlab.com/owner/repo
        - https://gitee.com/owner/repo

        返回: {
            "platform": "github",
            "owner": "owner",
            "repo": "repo",
            "original_url": "https://..."
        }
        """
        text = text.strip().rstrip("/")

        # 处理 SSH 格式: git@github.com:owner/repo.git
        ssh_match = re.match(r"git@([^:]+):(.+)", text)
        if ssh_match:
            host = ssh_match.group(1)
            path = ssh_match.group(2)
        else:
            parsed = urlparse(text)
            host = parsed.hostname or ""
            path = parsed.path.lstrip("/")

        # 移除 .git 后缀
        path = path.rstrip(".git")

        # 拆分 owner/repo
        parts = path.split("/")
        if len(parts) >= 2:
            owner = parts[0]
            repo = parts[1]
        elif len(parts) == 1:
            owner = parts[0]
            repo = parts[0]
        else:
            owner = ""
            repo = ""

        # 识别平台
        platform = UrlParser.PLATFORMS.get(host, "unknown")

        return {
            "platform": platform,
            "host": host,
            "owner": owner,
            "repo": repo,
            "original_url": text,
        }

    @staticmethod
    def to_git_url(parsed: dict) -> str:
        """转换为 git clone 地址（HTTPS 格式）"""
        host = parsed.get("host", "")
        owner = parsed.get("owner", "")
        repo = parsed.get("repo", "")
        return f"https://{host}/{owner}/{repo}.git"

    @staticmethod
    def get_project_name(parsed: dict) -> str:
        """从解析结果获取项目名称"""
        return parsed.get("repo", "unknown-project")
