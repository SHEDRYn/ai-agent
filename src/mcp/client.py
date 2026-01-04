"""MCP клиент для взаимодействия с MCP серверами"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

import aiohttp
from aiohttp import ClientSession

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
        """Подключение через HTTP"""
        url = config.get("url")
        if not url:
            raise ValueError(f"URL обязателен для HTTP транспорта сервера {name}")

        # Извлечение опциональных параметров
        api_key = config.get("api_key") or config.get("token")
        custom_headers = config.get("headers", {})
        timeout_seconds = config.get("timeout", 30)

        # Подготовка заголовков
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

        # Добавление аутентификации
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        # Добавление кастомных заголовков
        headers.update(custom_headers)

        # Создание сессии с таймаутом
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        session = ClientSession(headers=headers, timeout=timeout)

        self.servers[name] = {
            "session": session,
            "url": url,
            "transport": "http",
            "tools": [],
            "timeout": timeout_seconds,
        }

    async def _initialize(self, name: str) -> None:
        """Инициализация MCP соединения"""
        request = MCPRequest(
            id=self._next_id(),
            method="initialize",
            params={
                "protocolVersion": "2026-01-04",
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
        elif server["transport"] == "http":
            return await self._send_http_request(server, request)
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

    async def _send_http_request(
        self, server: Dict[str, Any], request: MCPRequest
    ) -> MCPResponse:
        """Отправка запроса через HTTP"""
        session = server["session"]
        url = server["url"]

        try:
            # Отправка POST запроса (сериализация в JSON происходит автоматически через json параметр)
            async with session.post(url, json=request.dict(exclude_none=True)) as resp:
                # Проверка статус-кода
                if resp.status >= 400:
                    error_text = await resp.text()
                    logger.error(
                        f"HTTP ошибка {resp.status} от MCP сервера: {error_text}"
                    )
                    raise RuntimeError(
                        f"HTTP ошибка {resp.status} от MCP сервера: {error_text}"
                    )

                # Чтение и десериализация ответа
                response_data = await resp.json()
                response = MCPResponse(**response_data)
                return response

        except asyncio.TimeoutError as e:
            logger.error(f"Таймаут при отправке HTTP запроса: {e}")
            raise RuntimeError(f"Таймаут при отправке HTTP запроса к MCP серверу")
        except aiohttp.ClientError as e:
            logger.error(f"Сетевая ошибка при отправке HTTP запроса: {e}")
            raise RuntimeError(f"Сетевая ошибка при отправке HTTP запроса: {e}")
        except Exception as e:
            logger.error(f"Ошибка при отправке HTTP запроса: {e}")
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

        # Форматирование результата
        if result_content:
            texts = []
            for item in result_content:
                if item.get("type") == "text":
                    texts.append(item.get("text", ""))

            if texts:
                text_content = "\n".join(texts).strip()
                if not text_content:
                    logger.warning(f"Пустой ответ от инструмента {tool_name}")
                    return result_content

                try:
                    # Пытаемся распарсить как JSON
                    return json.loads(text_content)
                except json.JSONDecodeError as e:
                    # Если не JSON, возвращаем как строку
                    logger.debug(
                        f"Ответ инструмента {tool_name} не является JSON: {e}, "
                        f"возвращаем как строку. Содержимое: {text_content[:100]}"
                    )
                    return text_content
            else:
                return result_content

        return response.result

    async def disconnect_server(self, name: str) -> None:
        """Отключение от сервера"""
        if name not in self.servers:
            return

        server = self.servers[name]

        if server["transport"] == "stdio" and server.get("process"):
            process = server["process"]
            process.terminate()
            await process.wait()
        elif server["transport"] == "http" and "session" in server:
            session = server["session"]
            try:
                if not session.closed:
                    await session.close()
                # Ждем завершения всех операций
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.warning(f"Ошибка при закрытии HTTP сессии для {name}: {e}")

        del self.servers[name]
        logger.info(f"Отключен от MCP сервера {name}")

    async def disconnect_all(self) -> None:
        """Отключение от всех серверов"""
        for name in list(self.servers.keys()):
            try:
                await self.disconnect_server(name)
            except Exception as e:
                logger.warning(f"Ошибка при отключении от сервера {name}: {e}")
