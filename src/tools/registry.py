"""Регистр инструментов"""

from typing import Dict, Any, List, Optional
import json
import logging

from .base import BaseTool
from ..llm.models import ToolDefinition

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Централизованный регистр инструментов"""
    
    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}
    
    def register(self, tool: BaseTool) -> None:
        """
        Регистрация инструмента
        
        Args:
            tool: Экземпляр инструмента (BaseTool)
        """
        if tool.name in self.tools:
            logger.warning(f"Инструмент {tool.name} уже зарегистрирован, перезаписываем")
        
        self.tools[tool.name] = tool
        logger.debug(f"Зарегистрирован инструмент: {tool.name}")
    
    def register_function(
        self,
        name: str,
        func: callable,
        description: str,
        parameters_schema: Dict[str, Any],
    ) -> None:
        """
        Регистрация функции как инструмента
        
        Args:
            name: Имя инструмента
            func: Функция для вызова
            description: Описание инструмента
            parameters_schema: JSON Schema параметров
        """
        from .base import BaseTool
        
        class FunctionTool(BaseTool):
            def __init__(self):
                super().__init__(name, description, parameters_schema)
                self.func = func
            
            async def execute(self, **kwargs):
                import asyncio
                import inspect
                
                if inspect.iscoroutinefunction(func):
                    return await self.func(**kwargs)
                else:
                    # Запускаем синхронную функцию в executor
                    loop = asyncio.get_event_loop()
                    return await loop.run_in_executor(None, lambda: self.func(**kwargs))
        
        self.register(FunctionTool())
    
    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Получить инструмент по имени"""
        return self.tools.get(name)
    
    def get_all_tools(self) -> List[BaseTool]:
        """Получить все зарегистрированные инструменты"""
        return list(self.tools.values())
    
    def get_all_tool_definitions(self) -> List[ToolDefinition]:
        """Получить определения всех инструментов в формате для LLM"""
        definitions = []
        for tool in self.tools.values():
            schema = tool.get_schema()
            definitions.append(ToolDefinition(**schema))
        return definitions
    
    def get_tools_as_dict(self) -> List[Dict[str, Any]]:
        """Получить все инструменты в формате OpenAI tools"""
        return [tool.get_schema() for tool in self.tools.values()]
    
    async def call_tool(
        self,
        name: str,
        arguments: Dict[str, Any],
    ) -> Any:
        """
        Вызвать инструмент
        
        Args:
            name: Имя инструмента
            arguments: Аргументы для инструмента
        
        Returns:
            Результат выполнения инструмента
        
        Raises:
            ValueError: Если инструмент не найден
            ValueError: Если аргументы невалидны
        """
        tool = self.get_tool(name)
        if not tool:
            raise ValueError(f"Инструмент '{name}' не найден в регистре")
        
        # Валидация аргументов
        if not tool.validate_arguments(arguments):
            raise ValueError(f"Невалидные аргументы для инструмента '{name}'")
        
        try:
            # Выполнение инструмента
            result = await tool.execute(**arguments)
            return result
        except Exception as e:
            logger.error(f"Ошибка при выполнении инструмента '{name}': {str(e)}", exc_info=True)
            raise
    
    async def call_tool_from_llm(
        self,
        tool_call: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Вызвать инструмент из формата LLM tool_call
        
        Args:
            tool_call: Вызов инструмента от LLM в формате:
                {
                    "id": "...",
                    "type": "function",
                    "function": {
                        "name": "...",
                        "arguments": "{\"key\": \"value\"}"  # JSON строка
                    }
                }
        
        Returns:
            Результат в формате для добавления в историю:
            {
                "tool_call_id": "...",
                "name": "...",
                "result": ...
            }
        """
        tool_name = tool_call["function"]["name"]
        arguments_str = tool_call["function"]["arguments"]
        
        try:
            arguments = json.loads(arguments_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Невалидный JSON в аргументах инструмента '{tool_name}': {str(e)}")
        
        try:
            result = await self.call_tool(tool_name, arguments)
            return {
                "tool_call_id": tool_call["id"],
                "name": tool_name,
                "result": result,
            }
        except Exception as e:
            # Возвращаем ошибку как результат
            return {
                "tool_call_id": tool_call["id"],
                "name": tool_name,
                "result": f"Ошибка: {str(e)}",
            }
    
    def unregister(self, name: str) -> bool:
        """
        Отменить регистрацию инструмента
        
        Args:
            name: Имя инструмента
        
        Returns:
            True если инструмент был удален, False если не найден
        """
        if name in self.tools:
            del self.tools[name]
            logger.debug(f"Инструмент {name} удален из регистра")
            return True
        return False
    
    def clear(self) -> None:
        """Очистить все инструменты"""
        self.tools.clear()
        logger.debug("Регистр инструментов очищен")

