"""MiniMax provider package."""

from .provider import MiniMaxProvider
from .registration import register_minimax
from .settings import MiniMaxSettings

__all__ = ["MiniMaxProvider", "MiniMaxSettings", "register_minimax"]
