"""HelpHandlerAgent - 处理 help 命令"""
from typing import Dict, Any

from evaluator.agents.base_agent import BaseAgent, AgentMeta


HELP_CONTENT = """
╭──────────────────────────────────────────────────────────────╮
│  eval-agent v1.0.0 - CI/CD 架构评估工具                        │
╰──────────────────────────────────────────────────────────────╯

支持自然语言输入，例如：
  - "分析 cccl 项目"
  - "对比 cccl 和 TensorRT-LLM"
  - "有哪些已分析的项目"
输入 / 查看传统命令

╭──────────────────────────────────────────────────────────────╮
│  命令列表                                                    │
╰──────────────────────────────────────────────────────────────╯

  /analyze [type] <path|url>
      分析项目的 CI/CD 架构
      示例: /analyze ./my-project
            /analyze cicd https://github.com/owner/repo

  /compare <project_a> <project_b> [--dim dims]
      对比两个项目的 CI/CD 架构
      示例: /compare project-a project-b
            /compare project-a project-b --dim complexity,best_practices

  /list [--all]
      列出已保存的项目

  /show <name> [--version version_id]
      显示项目详情

  /delete <name> [--version version_id]
      删除项目

  /analyzers
      列出可用的分析器

  /help [topic]
      显示帮助
      示例: /help analyze
            /help compare

  /version
      显示版本信息

  /clear
      清除屏幕

  /quit, /exit
      退出程序
"""


class HelpHandlerAgent(BaseAgent):
    """处理 help 命令的 Agent
    
    显示帮助信息。
    """
    
    @classmethod
    def describe(cls) -> AgentMeta:
        return AgentMeta(
            name="HelpHandlerAgent",
            description="显示帮助信息",
            category="handler",
            inputs=["params"],
            outputs=["help_result"],
            dependencies=[],
        )
    
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行 help 命令
        
        Args:
            state: 当前状态，包含 params.topic
        
        Returns:
            更新后的状态，包含 help_result
        """
        params = state.get("params", {})
        topic = params.get("topic")
        
        help_content = HELP_CONTENT
        
        if topic == "analyze":
            help_content = """
╭──────────────────────────────────────────────────────────────╮
│  /analyze 命令                                               │
╰──────────────────────────────────────────────────────────────╯

用法: /analyze [type] <path|url>

参数:
  type    - 分析类型 (默认: cicd)
  path    - 本地项目路径
  url     - GitHub/GitLab 仓库地址

示例:
  /analyze ./my-project
  /analyze cicd ./my-project
  /analyze https://github.com/owner/repo
"""
        elif topic == "compare":
            help_content = """
╭──────────────────────────────────────────────────────────────╮
│  /compare 命令                                                │
╰──────────────────────────────────────────────────────────────╯

用法: /compare <project_a> <project_b> [--dim dims]

参数:
  project_a - 第一个项目名称
  project_b - 第二个项目名称
  dims      - 对比维度 (可选)

维度选项:
  complexity        - 复杂度分析
  best_practices    - 最佳实践
  maintainability   - 可维护性

示例:
  /compare project-a project-b
  /compare project-a project-b --dim complexity,best_practices
"""
        
        return {
            **state,
            "help_result": {
                "content": help_content,
                "topic": topic,
            },
            "completed_steps": state.get("completed_steps", []) + ["help_handler"],
        }
