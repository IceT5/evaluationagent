"""简单命令处理 Agent"""
from .list_handler import ListHandlerAgent
from .info_handler import InfoHandlerAgent
from .delete_handler import DeleteHandlerAgent
from .help_handler import HelpHandlerAgent
from .insights_handler import InsightsHandlerAgent
from .recommend_handler import RecommendHandlerAgent
from .similar_handler import SimilarHandlerAgent
from .analyzers_handler import AnalyzersHandlerAgent
from .version_handler import VersionHandlerAgent
from .clear_handler import ClearHandlerAgent
from .quit_handler import QuitHandlerAgent

__all__ = [
    "ListHandlerAgent",
    "InfoHandlerAgent",
    "DeleteHandlerAgent",
    "HelpHandlerAgent",
    "InsightsHandlerAgent",
    "RecommendHandlerAgent",
    "SimilarHandlerAgent",
    "AnalyzersHandlerAgent",
    "VersionHandlerAgent",
    "ClearHandlerAgent",
    "QuitHandlerAgent",
]
