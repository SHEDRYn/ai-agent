"""Оркестратор агента - основной цикл работы"""

import json
import logging
from typing import Any, Dict, Optional

from ..llm.client import LLMClient
from ..llm.models import Message
from ..mcp.client import MCPClient
from ..tools.registry import ToolRegistry
from .conversation import ConversationManager

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Оркестратор для управления агентом"""

    def __init__(
        self,
        llm_client: LLMClient,
        tool_registry: ToolRegistry,
        mcp_client: Optional[MCPClient] = None,
        max_iterations: int = 20,
    ):
        """
        Инициализация оркестратора

        Args:
            llm_client: Клиент для LLM
            tool_registry: Регистр инструментов
            mcp_client: MCP клиент (опционально)
            max_iterations: Максимальное количество итераций цикла
        """
        self.llm_client = llm_client
        self.tool_registry = tool_registry
        self.mcp_client = mcp_client
        self.max_iterations = max_iterations
        self.conversation = ConversationManager()

    async def process_user_request(self, user_message: str) -> str:
        """
        Обработка запроса пользователя

        Args:
            user_message: Сообщение пользователя

        Returns:
            Финальный ответ агента
        """
        # Добавляем системное сообщение если история пуста
        if self.conversation.get_message_count() == 0:
            system_message = {
                "role": "system",
                "content": "Ты ИИ-агент программист. Ты можешь использовать различные инструменты для работы с кодом, файлами, поиска информации и выполнения задач. Всегда думай шаг за шагом и используй доступные инструменты для выполнения задач пользователя.",
            }
            self.conversation.history.add_message(Message(**system_message))

        # Добавляем запрос пользователя
        self.conversation.add_user_message(user_message)

        iteration = 0

        while iteration < self.max_iterations:
            iteration += 1
            logger.debug(f"Итерация {iteration}/{self.max_iterations}")

            # Получаем доступные инструменты
            tools = await self._get_available_tools(iteration == 1)

            # Запрашиваем ответ от LLM
            try:
                messages = self.conversation.get_messages()
                response = await self.llm_client.chat(
                    messages=messages, tools=tools, tool_choice="auto"
                )
            except Exception as e:
                logger.error(f"Ошибка при запросе к LLM: {e}")
                return f"Ошибка при обработке запроса: {str(e)}"

            # Проверяем наличие вызовов инструментов
            tool_calls = response.get("tool_calls")

            if tool_calls:
                # Выполняем инструменты
                tool_results = []
                for tool_call in tool_calls:
                    try:
                        result = await self._execute_tool_call(tool_call)
                        tool_results.append(result)
                    except Exception as e:
                        logger.error(f"Ошибка при выполнении инструмента: {e}")
                        tool_results.append(
                            {
                                "tool_call_id": tool_call.get("id", ""),
                                "name": tool_call["function"]["name"],
                                "result": f"Ошибка: {str(e)}",
                            }
                        )

                # Добавляем ответ ассистента с вызовами инструментов
                self.conversation.add_assistant_message(
                    content=response.get("content"), tool_calls=tool_calls
                )

                # Добавляем результаты инструментов
                for result in tool_results:
                    self.conversation.add_tool_message(
                        tool_call_id=result["tool_call_id"],
                        name=result["name"],
                        content=result["result"],
                    )

                # Продолжаем цикл
                continue
            else:
                # Финальный ответ без инструментов
                content = response.get("content", "")
                self.conversation.add_assistant_message(content=content)
                return content

        # Достигнут лимит итераций
        return "Достигнут максимальный лимит итераций. Попробуйте упростить запрос."

    async def _get_available_tools(self, logs: bool = False) -> list[Dict[str, Any]]:
        """Получить список доступных инструментов"""
        tools = self.tool_registry.get_tools_as_dict()

        # Добавляем инструменты из MCP
        if self.mcp_client:
            try:
                mcp_tools = await self.mcp_client.list_tools()
                tools.extend(mcp_tools)
            except Exception as e:
                logger.warning(f"Ошибка при получении MCP инструментов: {e}")

        # Выводим список доступных инструментов
        if logs:
            print("> List tools")
            tool_names = [tool["function"]["name"] for tool in tools]
            for tool_name in sorted(tool_names):
                print(f"\t- {tool_name}")
            print("")
        return tools

    async def _execute_tool_call(
        self, tool_call: Dict[str, Any], logs: bool = True
    ) -> Dict[str, Any]:
        """Выполнить вызов инструмента"""
        tool_name = tool_call["function"]["name"]
        arguments_str = tool_call["function"]["arguments"]

        try:
            arguments = json.loads(arguments_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Невалидный JSON в аргументах: {e}")

        if logs:
            # Выводим информацию о вызове инструмента
            print(f"> {tool_name}")
            print("```Request")
            print(json.dumps(arguments, indent=2, ensure_ascii=False))
            print("```")
            print("✓ Approved")

        # Проверяем, локальный это инструмент или MCP
        if self.tool_registry.get_tool(tool_name):
            # Локальный инструмент
            result = await self.tool_registry.call_tool(tool_name, arguments)
        elif self.mcp_client and "." in tool_name:
            # MCP инструмент
            result = await self.mcp_client.call_tool(tool_name, arguments)
        else:
            raise ValueError(f"Инструмент не найден: {tool_name}")

        if logs:
            # Выводим результат работы инструмента
            print("```Response")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            print("```")
            print("")

        return {"tool_call_id": tool_call["id"], "name": tool_name, "result": result}

    def reset_conversation(self) -> None:
        """Сбросить историю диалога"""
        self.conversation.clear()
