"""MCP клиент для взаимодействия с MCP серверами"""

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

from .protocol import MCPRequest, MCPResponse, deserialize_response, serialize_request

logger = logging.getLogger(__name__)


class MCPClient:
    """Клиент для взаимодействия с MCP серверами"""

    def __init__(self):
        self.servers: Dict[str, Dict[str, Any]] = {}
        self.request_id_counter = 0

    async def connect_server(self, name: str, config: Dict[str, Any]) -> None:
        """
        Подключение к MCP серверу

        Args:
            name: Имя сервера
            config: Конфигурация сервера:
                {
                    "command": ["python", "-m", "server"],
                    "args": [],
                    "env": {},
                    "transport": "stdio"  # или "http", "websocket"
                }
        """
        transport = config.get("transport", "stdio")

        if transport == "stdio":
            await self._connect_stdio(name, config)
        elif transport == "http":
            await self._connect_http(name, config)
        else:
            raise ValueError(f"Неподдерживаемый транспорт: {transport}")

        # Инициализация MCP соединения
        await self._initialize(name)

    async def _connect_stdio(self, name: str, config: Dict[str, Any]) -> None:
        """Подключение через stdio"""
        command = config["command"]
        # Поддержка как списка, так и строки
        if isinstance(command, str):
            command = [command]
        args = config.get("args", [])
        env = config.get("env", {})

        # Подготовка окружения
        process_env = os.environ.copy()
        process_env.update(env)

        # Запуск процесса
        process = await asyncio.create_subprocess_exec(
            *command,
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=process_env,
        )

        self.servers[name] = {
            "process": process,
            "transport": "stdio",
            "tools": [],
        }

    async def _connect_http(self, name: str, config: Dict[str, Any]) -> None:
        """Подключение через HTTP (заглушка для будущей реализации)"""
        raise NotImplementedError("HTTP транспорт пока не реализован")

    async def _initialize(self, name: str) -> None:
        """Инициализация MCP соединения"""
        request = MCPRequest(
            id=self._next_id(),
            method="initialize",
            params={
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "ai-agent", "version": "0.1.0"},
            },
        )

        response = await self._send_request(name, request)

        if response.error:
            raise RuntimeError(
                f"Ошибка инициализации MCP сервера {name}: {response.error.message}"
            )

        # Загрузка списка инструментов
        await self._load_tools(name)

    async def _load_tools(self, name: str) -> None:
        """Загрузка списка инструментов с сервера"""
        request = MCPRequest(id=self._next_id(), method="tools/list", params={})

        response = await self._send_request(name, request)

        if response.error:
            logger.warning(
                f"Ошибка при загрузке инструментов с {name}: {response.error.message}"
            )
            return

        tools = response.result.get("tools", [])
        self.servers[name]["tools"] = tools
        logger.info(f"Загружено {len(tools)} инструментов с MCP сервера {name}")

    async def _send_request(self, name: str, request: MCPRequest) -> MCPResponse:
        """Отправка запроса к серверу"""
        server = self.servers.get(name)
        if not server:
            raise ValueError(f"Сервер {name} не подключен")

        if server["transport"] == "stdio":
            return await self._send_stdio_request(server, request)
        else:
            raise ValueError(f"Неподдерживаемый транспорт: {server['transport']}")

    async def _send_stdio_request(
        self, server: Dict[str, Any], request: MCPRequest
    ) -> MCPResponse:
        """Отправка запроса через stdio"""
        process = server["process"]

        try:
            # Отправка запроса
            request_json = serialize_request(request)
            process.stdin.write(request_json.encode("utf-8"))
            await process.stdin.drain()

            # Чтение ответа
            line = await process.stdout.readline()
            if not line:
                raise RuntimeError("Сервер закрыл соединение")

            response_str = line.decode("utf-8")
            response = deserialize_response(response_str)
            return response
        except Exception as e:
            logger.error(f"Ошибка при отправке запроса: {e}")
            raise

    def _next_id(self) -> int:
        """Генерация следующего ID запроса"""
        self.request_id_counter += 1
        return self.request_id_counter

    async def list_tools(
        self, server_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Получить список всех инструментов

        Args:
            server_name: Имя сервера (если None - все серверы)

        Returns:
            Список инструментов в формате OpenAI tools
        """
        all_tools = []

        servers = [server_name] if server_name else self.servers.keys()

        for name in servers:
            if name not in self.servers:
                continue

            tools = self.servers[name]["tools"]
            for tool in tools:
                # Конвертация в формат OpenAI tools
                openai_tool = self._convert_mcp_tool_to_openai(tool, name)
                all_tools.append(openai_tool)

        return all_tools

    def _convert_mcp_tool_to_openai(
        self, mcp_tool: Dict[str, Any], server_name: str
    ) -> Dict[str, Any]:
        """Конвертация MCP инструмента в формат OpenAI tools"""
        tool_name = f"{server_name}.{mcp_tool['name']}"

        return {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": mcp_tool.get("description", ""),
                "parameters": mcp_tool.get("inputSchema", {}),
            },
        }

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Вызов инструмента MCP сервера

        Args:
            tool_name: Имя инструмента (формат: server_name.tool_name)
            arguments: Аргументы инструмента

        Returns:
            Результат выполнения инструмента
        """
        # Парсинг имени инструмента
        if "." not in tool_name:
            raise ValueError(
                f"Неверный формат имени инструмента: {tool_name}. Ожидается: server.tool"
            )

        server_name, actual_tool_name = tool_name.split(".", 1)

        if server_name not in self.servers:
            raise ValueError(f"Сервер {server_name} не подключен")

        # Отправка запроса
        request = MCPRequest(
            id=self._next_id(),
            method="tools/call",
            params={"name": actual_tool_name, "arguments": arguments},
        )

        response = await self._send_request(server_name, request)

        if response.error:
            raise RuntimeError(
                f"Ошибка при вызове инструмента: {response.error.message}"
            )

        # Извлечение контента
        result_content = response.result.get("content", [])

        # Преобразование контента в строку
        if result_content:
            texts = []
            for item in result_content:
                if item.get("type") == "text":
                    texts.append(item.get("text", ""))
            return "\n".join(texts) if texts else result_content

        return response.result

    async def disconnect_server(self, name: str) -> None:
        """Отключение от сервера"""
        if name not in self.servers:
            return

        server = self.servers[name]
        if server["transport"] == "stdio" and server["process"]:
            process = server["process"]
            process.terminate()
            await process.wait()

        del self.servers[name]
        logger.info(f"Отключен от MCP сервера {name}")

    async def disconnect_all(self) -> None:
        """Отключение от всех серверов"""
        for name in list(self.servers.keys()):
            await self.disconnect_server(name)
