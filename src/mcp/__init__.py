"""Модуль для работы с MCP (Model Context Protocol)"""

from .client import MCPClient
from .protocol import MCPRequest, MCPResponse, MCPError

__all__ = ["MCPClient", "MCPRequest", "MCPResponse", "MCPError"]

