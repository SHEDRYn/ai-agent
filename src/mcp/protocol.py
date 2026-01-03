"""Реализация MCP (Model Context Protocol) протокола"""

from typing import Dict, Any, Optional, List, Union
from pydantic import BaseModel
import json


class MCPRequest(BaseModel):
    """JSON-RPC запрос для MCP"""
    jsonrpc: str = "2.0"
    id: Union[int, str]
    method: str
    params: Optional[Dict[str, Any]] = None


class MCPResponse(BaseModel):
    """JSON-RPC ответ от MCP"""
    jsonrpc: str = "2.0"
    id: Union[int, str]
    result: Optional[Dict[str, Any]] = None
    error: Optional["MCPError"] = None


class MCPError(BaseModel):
    """Ошибка MCP"""
    code: int
    message: str
    data: Optional[Dict[str, Any]] = None


MCPResponse.model_rebuild()


class MCPInitializeParams(BaseModel):
    """Параметры инициализации MCP"""
    protocolVersion: str = "2024-11-05"
    capabilities: Dict[str, Any] = {}
    clientInfo: Dict[str, Any] = {}


class MCPInitializeResult(BaseModel):
    """Результат инициализации MCP"""
    protocolVersion: str
    capabilities: Dict[str, Any]
    serverInfo: Dict[str, Any]


class MCPTool(BaseModel):
    """Определение инструмента MCP"""
    name: str
    description: str
    inputSchema: Dict[str, Any]  # JSON Schema


class MCPToolCallParams(BaseModel):
    """Параметры вызова инструмента MCP"""
    name: str
    arguments: Dict[str, Any]


class MCPToolCallResult(BaseModel):
    """Результат вызова инструмента MCP"""
    content: List[Dict[str, Any]]  # Список текстовых или изображений контента


def serialize_request(request: MCPRequest) -> str:
    """Сериализация запроса в JSON строку"""
    return json.dumps(request.dict(exclude_none=True), ensure_ascii=False) + "\n"


def deserialize_response(response_str: str) -> MCPResponse:
    """Десериализация ответа из JSON строки"""
    data = json.loads(response_str.strip())
    return MCPResponse(**data)


# Стандартные коды ошибок JSON-RPC
class RPCErrorCode:
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    # MCP специфичные ошибки
    SERVER_ERROR_START = -32000
    SERVER_ERROR_END = -32099

