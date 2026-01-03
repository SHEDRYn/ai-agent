"""Управление историей диалога"""

from typing import List, Dict, Any, Optional
from ..llm.models import Message, ConversationHistory
import logging

logger = logging.getLogger(__name__)


class ConversationManager:
    """Менеджер для управления историей диалога"""
    
    def __init__(self, max_tokens: Optional[int] = None):
        """
        Инициализация менеджера
        
        Args:
            max_tokens: Максимальное количество токенов в истории
        """
        self.history = ConversationHistory(max_tokens=max_tokens)
        self.max_tokens = max_tokens
    
    def add_user_message(self, content: str) -> None:
        """Добавить сообщение пользователя"""
        message = Message(role="user", content=content)
        self.history.add_message(message)
    
    def add_assistant_message(self, content: str, tool_calls: Optional[List[Dict[str, Any]]] = None) -> None:
        """Добавить сообщение ассистента"""
        tool_calls_list = None
        if tool_calls:
            from ..llm.models import ToolCall, FunctionCall
            tool_calls_list = []
            for tc in tool_calls:
                tool_calls_list.append(ToolCall(
                    id=tc["id"],
                    function=FunctionCall(
                        name=tc["function"]["name"],
                        arguments=tc["function"]["arguments"]
                    )
                ))
        
        message = Message(
            role="assistant",
            content=content,
            tool_calls=tool_calls_list
        )
        self.history.add_message(message)
    
    def add_tool_message(self, tool_call_id: str, name: str, content: Any) -> None:
        """Добавить сообщение с результатом инструмента"""
        # Конвертация результата в строку
        if isinstance(content, (dict, list)):
            import json
            content_str = json.dumps(content, ensure_ascii=False, indent=2)
        else:
            content_str = str(content)
        
        message = Message(
            role="tool",
            content=content_str,
            tool_call_id=tool_call_id,
            name=name
        )
        self.history.add_message(message)
    
    def get_messages(self) -> List[Dict[str, Any]]:
        """Получить сообщения в формате для LLM"""
        return self.history.get_messages_for_llm()
    
    def clear(self) -> None:
        """Очистить историю"""
        self.history.messages.clear()
        logger.debug("История диалога очищена")
    
    def get_message_count(self) -> int:
        """Получить количество сообщений"""
        return len(self.history.messages)

