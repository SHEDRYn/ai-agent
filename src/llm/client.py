"""Клиент для работы с языковыми моделями через OpenAI API"""

import asyncio
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from .models import ConversationHistory, ToolDefinition


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

        # Настройка OpenAI клиента
        client_kwargs = {}
        if api_key:
            client_kwargs["api_key"] = api_key
        if base_url:
            client_kwargs["base_url"] = base_url

        self.client = AsyncOpenAI(**client_kwargs)

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
            response = await self.client.chat.completions.create(**kwargs)
            return self._parse_response(response)
        except Exception as e:
            raise RuntimeError(f"Ошибка при вызове LLM: {str(e)}")

    def _parse_response(self, response) -> Dict[str, Any]:
        """Парсинг ответа от OpenAI API в стандартный формат"""
        choice = response.choices[0]
        message = choice.message

        result = {
            "role": message.role,
            "content": message.content,
        }

        # Обработка tool_calls
        if message.tool_calls:
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


async def main():
    """Тестовая функция для проверки работы LLM клиента"""
    print("Инициализация LLM клиента...")

    # Создаем клиент (API ключ можно передать через переменную окружения)
    client = LLMClient(
        model="openrouter/openai/gpt-oss-20b",  # Используем более дешевую модель для теста
        base_url="http://litellm.dtc.tatar/",
        temperature=0.7,
    )

    print("Отправка тестового запроса...")

    # Простой тестовый запрос
    messages = [
        {"role": "user", "content": "Привет! Ответь коротко: что такое Python?"}
    ]

    try:
        response = await client.chat(messages)
        print("\n" + "=" * 50)
        print("Ответ от LLM:")
        print("=" * 50)
        print(f"Роль: {response.get('role', 'N/A')}")
        print(f"Содержание: {response.get('content', 'N/A')}")
        if response.get("tool_calls"):
            print(f"Tool calls: {response.get('tool_calls')}")
        print("=" * 50)
    except Exception as e:
        print(f"\nОшибка при выполнении запроса: {e}")
        print(
            "Убедитесь, что установлен API ключ через переменную окружения OPENAI_API_KEY"
        )


if __name__ == "__main__":
    asyncio.run(main())
