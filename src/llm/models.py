"""Модели данных для работы с LLM"""

from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


class Message(BaseModel):
    """Сообщение в диалоге"""
    role: Literal["system", "user", "assistant", "tool"]
    content: Optional[str] = None
    tool_calls: Optional[List["ToolCall"]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None


class ToolCall(BaseModel):
    """Вызов инструмента"""
    id: str
    type: Literal["function"] = "function"
    function: "FunctionCall"


class FunctionCall(BaseModel):
    """Функция для вызова"""
    name: str
    arguments: str  # JSON строка


class ToolDefinition(BaseModel):
    """Определение инструмента для LLM"""
    type: Literal["function"] = "function"
    function: "FunctionDefinition"


class FunctionDefinition(BaseModel):
    """Описание функции"""
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema


class ConversationHistory(BaseModel):
    """История диалога"""
    messages: List[Message] = Field(default_factory=list)
    max_tokens: Optional[int] = None
    current_tokens: int = 0

    def add_message(self, message: Message):
        """Добавить сообщение в историю"""
        self.messages.append(message)
    
    def get_messages_for_llm(self) -> List[Dict[str, Any]]:
        """Получить сообщения в формате для LLM API"""
        result = []
        for msg in self.messages:
            msg_dict = {"role": msg.role}
            if msg.content:
                msg_dict["content"] = msg.content
            if msg.tool_calls:
                msg_dict["tool_calls"] = [tc.dict() for tc in msg.tool_calls]
            if msg.tool_call_id:
                msg_dict["tool_call_id"] = msg.tool_call_id
            if msg.name:
                msg_dict["name"] = msg.name
            result.append(msg_dict)
        return result


# Обновляем ссылки для forward references
Message.model_rebuild()
ToolCall.model_rebuild()

