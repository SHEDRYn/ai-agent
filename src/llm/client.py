"""Клиент для работы с языковыми моделями через litellm"""

import os
from typing import Any, Dict, List, Optional

import litellm
from litellm import completion

from .models import ConversationHistory, Message, ToolDefinition


class LLMClient:
    """Клиент для взаимодействия с LLM через OpenAI-совместимый API"""

    def __init__(
        self,
        model: str = "gpt-4",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ):
        """
        Инициализация клиента

        Args:
            model: Название модели (например, "gpt-4", "gpt-3.5-turbo", "claude-3-opus")
            api_key: API ключ (можно также через переменную окружения)
            base_url: Базовый URL API (для совместимых провайдеров)
            temperature: Температура генерации
            max_tokens: Максимальное количество токенов в ответе
        """
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

        # Настройка litellm
        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key

        if base_url:
            # Для кастомных провайдеров через litellm
            litellm.api_base = base_url

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto",
    ) -> Dict[str, Any]:
        """
        Отправка запроса к LLM

        Args:
            messages: Список сообщений в формате OpenAI
            tools: Список доступных инструментов (OpenAI tools format)
            tool_choice: "auto", "none", или {"type": "function", "function": {"name": "..."}}

        Returns:
            Ответ модели в формате OpenAI
        """
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }

        if self.max_tokens:
            kwargs["max_tokens"] = self.max_tokens

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        try:
            response = await litellm.acompletion(**kwargs)
            return self._parse_response(response)
        except Exception as e:
            raise RuntimeError(f"Ошибка при вызове LLM: {str(e)}")

    def _parse_response(self, response) -> Dict[str, Any]:
        """Парсинг ответа от litellm в стандартный формат"""
        choice = response.choices[0]
        message = choice.message

        result = {
            "role": message.role,
            "content": message.content,
        }

        # Обработка tool_calls
        if hasattr(message, "tool_calls") and message.tool_calls:
            result["tool_calls"] = []
            for tc in message.tool_calls:
                result["tool_calls"].append(
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                )

        return result

    async def chat_with_tools(
        self,
        conversation: ConversationHistory,
        tools: Optional[List[ToolDefinition]] = None,
        tool_choice: str = "auto",
    ) -> Dict[str, Any]:
        """
        Удобный метод для чата с инструментами

        Args:
            conversation: История диалога
            tools: Список доступных инструментов
            tool_choice: Стратегия выбора инструментов

        Returns:
            Ответ модели
        """
        messages = conversation.get_messages_for_llm()

        tools_dict = None
        if tools:
            tools_dict = [tool.dict() for tool in tools]

        return await self.chat(messages, tools_dict, tool_choice)
